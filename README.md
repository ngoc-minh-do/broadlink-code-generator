# boardlink-local

Capture, reverse-engineer, and generate IR codes for AC remotes using a Broadlink device. Produces SmartIR-compatible JSON for Home Assistant.

## Setup

```bash
# Python >=3.13 required, managed with uv
uv sync

cp .env.example .env
# Edit .env and set your Broadlink device IP
```

## Usage

### Capture an IR code
```bash
uv run python tools/capture.py
```
Points the Broadlink into learning mode, waits 30s for an IR signal, and prints the captured code as hex + base64.

### Send an IR code
```bash
uv run python tools/send_code.py '<base64>'
uv run python tools/send_code.py --mode cool --temp 25 --fan auto
uv run python tools/send_code.py --key '25 cool auto'
uv run python tools/send_code.py --off
```

### Reverse-engineer protocol & generate SmartIR JSON
```bash
uv run python tools/generate_smartir.py captures/Toshiba-JP.txt
uv run python tools/generate_smartir.py captures/Toshiba-JP.txt --json
uv run python tools/generate_smartir.py captures/Toshiba-JP.txt --missing
uv run python tools/generate_smartir.py captures/Toshiba-JP.txt --generate --save smartir.json
```

### Guided capture of missing codes
```bash
uv run python tools/capture_missing.py
uv run python tools/capture_missing.py --mode heat --dry-run
uv run python tools/capture_missing.py --mode cool heat --fan auto
uv run python tools/capture_missing.py --fan-variants
```

### Test generated codes against physical remote
```bash
uv run python tools/test_generated.py
uv run python tools/test_generated.py --mode cool --fan auto --temps 20 25 30
uv run python tools/test_generated.py --all --shuffle --count 5
```

### Web app
```bash
uv run python web/server.py
```
Opens at `http://localhost:8080`. Visualize IR timings, decode captures, compare signals, and build SmartIR JSON interactively.

## Project Structure

```
boardlink-local/
├── src/boardlink_local/    # Shared library
│   ├── device.py           # Broadlink discovery & auth
│   ├── capture.py          # IR learning mode helpers
│   ├── protocol.py         # Protocol constants & code generators
│   ├── decoder.py          # Pulse → bit → byte decoding
│   └── smartir.py          # SmartIR JSON builder
├── tools/                  # CLI scripts
│   ├── capture.py
│   ├── generate_smartir.py
│   ├── send_code.py
│   ├── capture_missing.py
│   └── test_generated.py
├── captures/               # IR capture data
├── web/                    # Web app
└── pyproject.toml
```

## Supported Protocol (Toshiba JP)

18-byte (144-bit) IR protocol for Toshiba AC remotes:
- Modes: cool, heat, dry, fan_only, heat_cool
- Temperature: 16–30°C
- Fan speeds: auto, quiet, low, medium, high, powerful

See `AGENTS.md` for full protocol byte-level documentation.
