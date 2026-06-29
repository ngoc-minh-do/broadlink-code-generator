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

### Supported Devices

<details>
<summary>96 supported Toshiba AC models (click to expand)</summary>

- **RAS-K** — RAS-K221M, RAS-K251M, RAS-K281M, RAS-K361M, RAS-K401M, RAS-K221X, RAS-K251X, RAS-K281X, RAS-K401X, RAS-K221XEX, RAS-K281XEX, RAS-K401XEX, RAS-K221XKS, RAS-K251XKS, RAS-K281XKS, RAS-K401XKS, RAS-K221XSY, RAS-K251XSY, RAS-K281XSY, RAS-K401XSY
- **RAS-N** — RAS-N221M, RAS-N251M, RAS-N281M, RAS-N361M, RAS-N401M, RAS-N221TE, RAS-N401TE, RAS-N221X, RAS-N251X, RAS-N281X, RAS-N401X, RAS-N221XEX, RAS-N281XEX, RAS-N401XEX, RAS-N221XKS, RAS-N251XKS, RAS-N281XKS, RAS-N401XKS, RAS-N221XSY, RAS-N251XSY, RAS-N281XSY, RAS-N401XSY
- **RAS-G** — RAS-G221M, RAS-G251M, RAS-G281M, RAS-G361M, RAS-G401M
- **RAS-H** — RAS-H221M, RAS-H251M, RAS-H281M, RAS-H361M, RAS-H401M, RAS-H562M, RAS-H221TK, RAS-H251TK, RAS-H281TK
- **RAS-J** — RAS-J221M, RAS-J251M, RAS-J281M, RAS-J361M, RAS-J401M
- **RAS-221** — RAS-2210T, RAS-2210TM, RAS-2210TS, RAS-2211T, RAS-2211TL, RAS-2211TM, RAS-2212T, RAS-2212TL, RAS-2212TM, RAS-2213T, RAS-2213TC, RAS-2213TL, RAS-2213TM, RAS-2214T, RAS-2214TC, RAS-2214TL, RAS-2214TM, RAS-221TC
- **RAS-251** — RAS-2510T, RAS-2510TM, RAS-2510TS, RAS-2511T, RAS-2511TL, RAS-2511TM, RAS-2512T, RAS-2512TL, RAS-2512TM, RAS-2513T, RAS-2513TL, RAS-2513TM, RAS-2514T, RAS-2514TL, RAS-2514TM
- **RAS-281/282** — RAS-2810T, RAS-2810TM, RAS-2810TS, RAS-2811T, RAS-2811TL, RAS-2811TM, RAS-2812T, RAS-2812TL, RAS-2812TM, RAS-2813T, RAS-2813TL, RAS-2813TM, RAS-2814T, RAS-2814TL, RAS-2814TM, RAS-2820T, RAS-2821T, RAS-2822T, RAS-2823T, RAS-2824T
- **RAS-361** — RAS-3610T, RAS-3610TS, RAS-3611T, RAS-3611TL, RAS-3612T, RAS-3612TL, RAS-3613T, RAS-3613TL, RAS-3614T, RAS-3614TL
- **RAS-401/402** — RAS-4010T, RAS-4010TM, RAS-4010TS, RAS-4011T, RAS-4011TL, RAS-4011TM, RAS-4012T, RAS-4012TL, RAS-4012TM, RAS-4013T, RAS-4013TL, RAS-4013TM, RAS-4014T, RAS-4014TL, RAS-4014TM, RAS-4020T, RAS-4021T, RAS-4022T, RAS-4023T, RAS-4024T
- **RAS-562** — RAS-5621T

</details>
