# AGENTS.md

## Setup
- Python >=3.13, managed with `uv`
- Install deps: `uv sync`
- The project depends on `broadlink>=0.19.0` and `python-dotenv>=1.2.2`
- Set `BROADLINK_IP` in `.env` to your Broadlink device's IP address

## Commands
- Capture a single IR code: `uv run python tools/capture.py`
- Reverse-engineer IR protocol & generate SmartIR JSON: `uv run python tools/generate_smartir.py captures/Toshiba-JP.txt`
  - Decodes Broadlink base64 into byte-level protocol analysis, identifies the message structure (payload fields, complementary pairs, checksum), and exports a SmartIR-compatible JSON ready for Home Assistant.
  - Options: `--json` (print JSON), `--missing` (show gaps + suggested captures), `--generate` (produce inferred codes for all temp/mode/fan combos), `--save FILE.json` (write to file).
- Send an IR code: `uv run python tools/send_code.py '<base64>'`
  - Options: `--key '25 cool auto'`, `--mode cool --temp 25 --fan auto`, `--off`
- Interactive test generated codes against physical remote: `uv run python tools/test_generated.py`
- Guided capture of missing IR codes: `uv run python tools/capture_missing.py`
  - Reads existing captures, shows what's missing, interactively guides through each capture.
  - Options: `--mode heat cool` (filter modes), `--dry-run` (show missing only), `--fan-variants` (also capture fan variants for already-captured temps).
  - Options: `--all` (every combination), `--mode cool heat --temps 20 25 30` (specific), `--shuffle`, `--count 5`.
- Start the IR Learner & SmartIR Builder web app: `uv run python web/server.py`
  - Opens at `http://localhost:8080`. The app helps visualize/analyze IR timings and build SmartIR JSON files.

## Architecture
- `src/boardlink_local/` — shared library package
  - `device.py` — Broadlink device discovery & authentication
  - `capture.py` — IR learning mode helpers
  - `protocol.py` — protocol constants, field encoders, and code generators (TEMP_NIB, FAN_B2, generate_code, etc.)
  - `decoder.py` — pulse→bit→byte decoding, capture file I/O, label parsing
  - `smartir.py` — SmartIR JSON builder
- `tools/` — CLI scripts
  - `capture.py` — single IR code capture
  - `generate_smartir.py` — protocol analysis & SmartIR JSON export
  - `send_code.py` — send IR codes to Broadlink device
  - `capture_missing.py` — guided interactive capture of missing codes
  - `test_generated.py` — test generated codes against physical remote
- `captures/` — saved IR captures. `Toshiba-JP.txt` is the primary capture file (label+base64 pairs).
- `web/` — single-page HTML app + HTTP server for visualizing IR timings and building SmartIR JSON manually.
- `uv.lock` is committed — treat this as the lockfile source of truth.

## Protocol notes (from captured AC remote)
- The AC remote uses an 18-byte (144-bit) protocol: 6-byte payload repeated twice + 6-byte footer. The OFF command is 12 bytes (payload ×2, no footer).
- Byte 0-1: fixed identifier `C2 3D`. Byte pairs (2,3) and (4,5) are complementary: B3 = 0xFF − B2, B5 = 0xFF − B4.
- Byte 2 encodes fan speed: auto→0xBF, quiet→0xFF, low→0x9F, medium→0x5F, high→0x3F, powerful→0x3F. dry/heat_cool always use 0x1F (fan not independently controllable).
- Byte 4 encodes temperature+mode: upper nibble = temperature, lower nibble = mode (0=cool, 4=fan_only/dry, 8=heat_cool, C=heat). fan_only mode always uses B4=0xE4 (temp not applicable).
- Temperature encoding (upper nibble of B4) is mode-independent lookup table. 16/17°C share the same code; all other temps (18–30°C) have unique nibbles: 16→0x0, 17→0x0, 18→0x1, 19→0x3, 20→0x2, 21→0x6, 22→0x7, 23→0x5, 24→0x4, 25→0xC, 26→0xD, 27→0x9, 28→0x8, 29→0xA, 30→0xB.
- Footer: B12=0xD5 fixed, B13 encodes fan speed % (quiet=1, low=40, medium=60, high=80, powerful=100, auto=102, dry/heat_cool always=101). B17 = sum(B12..B16) mod 256 (checksum).
- To add captures, edit `captures/Toshiba-JP.txt` with `<label>\n<base64>` pairs. Label format: `<temp> <mode> <fan>` (use `x` for temp when not applicable, e.g. `x fan_only auto`). Re-run `generate_smartir.py --generate --save` to update the JSON.

## Gotchas
- The Broadlink device must be reachable on the local network for any tool to work.
- `Toshiba-JP.txt` captures use Broadlink base64 format (output of `capture.py`).
