# AGENTS.md

## Setup
- Python >=3.13, managed with `uv`
- Install deps: `uv sync`
- The project depends only on `broadlink>=0.19.0`

## Commands
- Run the main capture script: `uv run python main.py`
- Reverse-engineer IR protocol & generate SmartIR JSON: `uv run python tools/generate_smartir.py captures/Toshiba_RAS-K281X.txt`
  - Decodes Broadlink base64 into byte-level protocol analysis, identifies the message structure (payload fields, complementary pairs, checksum), and exports a SmartIR-compatible JSON ready for Home Assistant.
  - Options: `--json` (print JSON), `--missing` (show gaps + suggested captures), `--generate` (produce inferred codes for all temp/mode/fan combos), `--save FILE.json` (write to file).
- Interactive test generated codes against physical remote: `uv run python tools/test_generated.py`
- Guided capture of missing IR codes: `uv run python tools/capture_missing.py`
  - Reads existing captures, shows what's missing, interactively guides through each capture.
  - Options: `--mode heat cool` (filter modes), `--dry-run` (show missing only), `--fan-variants` (also capture fan variants for already-captured temps).
  - Picks generated codes, prompts you to press the matching button on the remote, captures via Broadlink, compares byte-level match.
  - Options: `--all` (every combination), `--mode cool heat --temps 20 25 30` (specific), `--shuffle`, `--count 5`.
- Start the IR Learner & SmartIR Builder web app: `uv run python web/server.py`
  - Opens at `http://localhost:8080`. The app helps visualize/analyze IR timings and build SmartIR JSON files.
## Architecture
- `main.py` — discovers a Broadlink device on the local network at hardcoded IP `192.168.0.120`, enters IR learning mode, waits up to 30s for a button press, then prints the captured packet as hex and base64.
- `tools/generate_smartir.py` — protocol reverse-engineering tool. Decodes Broadlink base64 to raw pulses via `broadlink.remote.data_to_pulses()`, classifies marks/spaces, converts to bits/bytes, compares patterns across captures to identify which bytes encode temperature/mode/fan, and produces SmartIR JSON.
- `captures/` — saved IR captures. `Toshiba_RAS-K281X.txt` is the primary capture file (label+base64 pairs). `*.txt` are raw IRremoteESP8266-format timing arrays.
- `web/` — single-page HTML app for visualizing IR timings and building SmartIR JSON manually.
- `uv.lock` is committed — treat this as the lockfile source of truth.

## Protocol notes (from captured AC remote)
- The AC remote uses an 18-byte (144-bit) protocol: 6-byte payload repeated twice + 6-byte footer. The OFF command is 12 bytes (payload ×2, no footer).
- Byte 0-1: fixed identifier `C2 3D`. Byte pairs (2,3) and (4,5) are complementary: B3 = 0xFF − B2, B5 = 0xFF − B4.
- Byte 2 encodes fan speed: auto→0xBF, quiet→0xFF, low→0x9F, medium→0x5F, high→0x3F, powerful→0x3F. Dry mode auto→0x1F.
- Byte 4 encodes temperature+mode: upper nibble = temperature (see formula below), lower nibble = mode (0=cool, 4=fan_only/dry, C=heat). fan_only mode always uses B4=0xE4 (temp not applicable).
- Temperature encoding (upper nibble of B4, t-16 as 4-bit b3b2b1b0): bit7=1 if t≥25, then mode-specific — cool: bit4=b1, bit5=b2, bit6=b3&~b2; heat: bit4=b1, bit5=b2&b3, bit6=b3⊕b2; dry: bit4=b1, bit5=b2&~b1, bit6=b3. Some adjacent temps share codes. fan_only always uses B4=0xE4.
- Footer: B12=0xD5 fixed, B13 encodes fan speed % (quiet=1, low=40, medium=60, high=80, powerful=100, auto=102). B17 = sum(B12..B16) mod 256 (checksum).
- To add captures, edit `captures/Toshiba_RAS-K281X.txt` with `<label>\n<base64>` pairs. Label format: `<temp> <mode> <fan>` (use `x` for temp when not applicable, e.g. `x fan_only auto`). Re-run `generate_smartir.py --generate --save` to update the JSON.

## Gotchas
- `main.py` has a hardcoded device IP. The Broadlink device must be reachable on the local network for the script to work.
- `Toshiba_RAS-K281X.txt` captures use Broadlink base64 format (output of `main.py`).
