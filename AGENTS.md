# AGENTS.md

## Setup
- Python >=3.13, managed with `uv`
- Install deps: `uv sync`
- The project depends only on `broadlink>=0.19.0`

## Commands
- Run the main capture script: `uv run python main.py`
- Analyze captured IR timing data: `uv run python tools/auto_analyse_raw_data.py /path/to/capture.txt`
  - The tool is a standalone utility ported from IRremoteESP8266; it parses raw timing arrays and prints protocol analysis. Use `--help` for CLI options.
- Reverse-engineer IR protocol & generate SmartIR JSON: `uv run python tools/generate_smartir.py captures/Toshiba_RAS-K281X.txt`
  - Decodes Broadlink base64 into byte-level protocol analysis, identifies the message structure (payload fields, complementary pairs, checksum), and exports a SmartIR-compatible JSON ready for Home Assistant.
  - Options: `--json` (print JSON), `--missing` (show gaps + suggested captures), `--generate` (produce inferred codes for all temp/mode/fan combos), `--save FILE.json` (write to file).
- Start the IR Learner & SmartIR Builder web app: `uv run python web/server.py`
  - Opens at `http://localhost:8080`. The app helps visualize/analyze IR timings and build SmartIR JSON files.
- No tests, no linter, no type checker, no CI configured.

## Architecture
- `main.py` — discovers a Broadlink device on the local network at hardcoded IP `192.168.0.120`, enters IR learning mode, waits up to 30s for a button press, then prints the captured packet as hex and base64.
- `tools/auto_analyse_raw_data.py` — standalone CLI for analyzing raw IR timing data (not an importable library). Takes a C++ rawData declaration string or a file containing one, identifies mark/space candidates, and decodes the bit pattern.
- `tools/generate_smartir.py` — protocol reverse-engineering tool. Decodes Broadlink base64 to raw pulses via `broadlink.remote.data_to_pulses()`, classifies marks/spaces, converts to bits/bytes, compares patterns across captures to identify which bytes encode temperature/mode/fan, and produces SmartIR JSON.
- `captures/` — saved IR captures. `Toshiba_RAS-K281X.txt` is the primary capture file (label+base64 pairs). `*.txt` are raw IRremoteESP8266-format timing arrays.
- `web/` — single-page HTML app for visualizing IR timings and building SmartIR JSON manually.
- `uv.lock` is committed — treat this as the lockfile source of truth.

## Protocol notes (from captured AC remote)
- The AC remote uses an 18-byte (144-bit) protocol: 6-byte payload repeated twice + 6-byte footer. The OFF command is 12 bytes (payload ×2, no footer).
- Byte 0-1: fixed identifier `C2 3D`. Byte pairs (2,3) and (4,5) are complementary: B3 = 0xFF − B2, B5 = 0xFF − B4.
- Byte 2 encodes fan speed: auto→0xBF, 1→0xFF, 2→0x9F, 3→0x5F, 4→0x3F, 5→0x3F. Dry mode auto→0x1F.
- Byte 4 encodes temperature+mode: upper nibble = temperature (see formula below), lower nibble = mode (0=cool, 4=fan_only/dry, C=heat). fan_only mode always uses B4=0xE4 (temp not applicable).
- Temperature formula (t-16 as 4-bit b3b2b1b0): bit7=1 if t≥25, bit6=b3&~b2, bit5=b2, bit4=b1. Some adjacent temps share codes.
- Footer: B12=0xD5 fixed, B13 encodes fan speed % (1,40,60,80,100,102=auto). B17 = sum(B12..B16) mod 256 (checksum).
- To add captures, edit `captures/Toshiba_RAS-K281X.txt` with `<label>\n<base64>` pairs. Label format: `<temp> <mode> <fan>` (use `x` for temp when not applicable, e.g. `x fan_only auto`). Re-run `generate_smartir.py --generate --save` to update the JSON.

## Gotchas
- `main.py` has a hardcoded device IP. The Broadlink device must be reachable on the local network for the script to work.
- The capture files in `captures/` use the IRremoteESP8266 rawData format; they are not in the same format as what `main.py` outputs.
- `Toshiba_RAS-K281X.txt` captures use Broadlink base64 format (output of `main.py`).
