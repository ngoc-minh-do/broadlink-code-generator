#!/usr/bin/env python3
"""
IR protocol reverse-engineering & SmartIR JSON generator for Broadlink captures.

Decodes Broadlink base64 captures into byte-level protocol analysis, identifies
which bytes encode temperature/mode/fan, and generates SmartIR-compatible JSON.

Usage:
  uv run python tools/generate_smartir.py captures/Toshiba_RAS-K281X.txt
  uv run python tools/generate_smartir.py captures/Toshiba_RAS-K281X.txt --json --save out.json

Protocol (18 bytes = 144 bits):
  B0-B1  : fixed header  C2 3D
  B2     : fan speed      B3 = 0xFF − B2 (complementary pair)
  B4     : mode + temp    B5 = 0xFF − B4 (complementary pair)
  B6-B11 : repeat of B0-B5
  B12-B16: footer         B12 = 0xD5 fixed, B13 = fan speed %
  B17    : checksum       sum(B12..B16) % 256

  OFF signal: 12 bytes (96 bits) — 6-byte payload ×2, no footer.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from broadlink.remote import data_to_pulses, pulses_to_data

# ── Pulse-level decoding ────────────────────────────────

def reduce_list(items, margin=150):
    result = []
    for item in sorted(set(items), reverse=True):
        if not result or item < result[-1] - margin:
            result.append(item)
    return result

def within_margin(seen, expected, margin=150):
    return abs(seen - expected) <= margin

def classify_pulses(pulses, margin=150):
    marks = pulses[::2]
    spaces = pulses[1::2]
    mark_c = reduce_list(marks, margin)
    space_c = reduce_list(spaces, margin)
    bit_mark = mark_c[-1] if mark_c else 0
    hdr_mark = mark_c[0] if len(mark_c) > 1 else bit_mark
    zero = one = hdr_space = None
    gaps = []
    for v in space_c:
        if 300 <= v <= 900 and zero is None:
            zero = v
        elif 1300 <= v <= 2200 and one is None:
            one = v
        elif 3800 <= v <= 5200 and hdr_space is None:
            hdr_space = v
        elif v > 5200:
            gaps.append(v)
    return {
        "bit_mark": bit_mark, "hdr_mark": hdr_mark,
        "zero_space": zero, "one_space": one, "hdr_space": hdr_space,
        "gaps": gaps, "margin": margin,
    }

def pulses_to_bits(pulses, ctx):
    if not ctx or ctx.get("one_space") is None or ctx.get("zero_space") is None:
        return "", []
    bits = ""
    for i in range(1, len(pulses), 2):
        v = pulses[i]
        if within_margin(v, ctx["one_space"], ctx["margin"]):
            bits += "1"
        elif within_margin(v, ctx["zero_space"], ctx["margin"]):
            bits += "0"
    return bits, []

def bits_to_bytes(bits):
    n = len(bits) // 8
    return [int(bits[i : i + 8], 2) for i in range(0, n * 8, 8)]

# ── Capture file I/O ────────────────────────────────────

def read_captures(path) -> Dict[str, dict]:
    lines = Path(path).read_text().strip().splitlines()
    lines = [l.strip() for l in lines if l.strip()]
    sigs = {}
    for i in range(0, len(lines), 2):
        label = lines[i]
        b64 = lines[i + 1]
        raw = base64.b64decode(b64)
        pulses = data_to_pulses(raw)
        sigs[label] = {"b64": b64, "raw": raw, "pulses": pulses}
    return sigs

def analyze_signals(signals) -> Dict[str, dict]:
    decoded = {}
    for label, d in signals.items():
        ctx = classify_pulses(d["pulses"])
        bits, _ = pulses_to_bits(d["pulses"], ctx)
        b = bits_to_bytes(bits)
        decoded[label] = {
            "b64": d["b64"], "raw": d["raw"],
            "pulses": d["pulses"], "bits": bits, "bytes": b, "ctx": ctx,
        }
    return decoded

def parse_label(label: str) -> dict:
    label = label.strip()
    if label.lower() == "off":
        return {"mode": "off", "temp": None, "fan": None}
    parts = label.split()
    if len(parts) == 3:
        try:
            temp = int(parts[0]) if parts[0].lower() != "x" else None
            mode = parts[1]
            return {"mode": mode, "temp": temp, "fan": parts[2]}
        except ValueError:
            pass
    return {"mode": label, "temp": None, "fan": None}

# ── Protocol field encoders ─────────────────────────────

# Temperature encoding for B4 upper nibble (verified with 16/24/25/26/30°C).
# Derived formulas (t-16 as 4-bit value b3 b2 b1 b0):
#   B4[4] = b1
#   B4[5] = b2 & b1
#   B4[6] = b3 ^ b2
#   B4[7] = 1 if t >= 25 (i.e. t-16 >= 9)
# Some adjacent temperatures produce the same B4 value (common in AC remotes).

def encode_temp_b4(temp: int, mode: str) -> int:
    """Return the B4 byte value (upper nibble = temperature, lower = mode).

    Each mode has its own temperature encoding formula (t-16 as 4-bit b3b2b1b0):
      cool:  bit4=b1, bit5=b2,        bit6=b3&~b2,  bit7=1 if t≥25
      heat:  bit4=b1, bit5=b2&b3,     bit6=b3⊕b2,   bit7=1 if t≥25
      dry:   bit4=b1, bit5=b2&~b1,    bit6=b3,      bit7=1 if t≥25
    Some adjacent temperatures produce the same code.

    fan_only mode always sends B4=0xE4 (temp is not applicable).
    """
    if mode == "fan_only":
        return 0xE4

    td = temp - 16
    b3, b2, b1 = (td >> 3) & 1, (td >> 2) & 1, (td >> 1) & 1
    bit7 = 1 if td >= 9 else 0

    if mode == "cool":
        bit4 = b1
        bit5 = b2
        bit6 = b3 & (1 - b2)
    elif mode == "heat":
        bit4 = b1
        bit5 = b2 & b3
        bit6 = b3 ^ b2
    elif mode == "dry":
        bit4 = b1
        bit5 = b2 & (1 - b1)
        bit6 = b3
    else:
        return 0xE4

    temp_nib = (bit7 << 3) | (bit6 << 2) | (bit5 << 1) | bit4

    mode_nibs = {"cool": 0x0, "fan_only": 0x4, "heat": 0xC, "dry": 0x4}
    mode_nib = mode_nibs.get(mode, 0x0)

    return (temp_nib << 4) | mode_nib


# Fan speed encoding for B2 (verified with all 5 speeds + auto).
#   auto = 0xBF, quiet=0xFF, low=0x9F, medium=0x5F, high=0x3F, powerful=0x3F
#   For dry mode auto: B2 = 0x1F (not 0xBF)

FAN_B2 = {"auto": 0xBF, "quiet": 0xFF, "low": 0x9F, "medium": 0x5F, "high": 0x3F, "powerful": 0x3F}

def encode_fan_b2(fan: str, mode: str) -> int:
    if mode == "dry" and fan == "auto":
        return 0x1F
    return FAN_B2.get(fan, 0xBF)


# Footer B13: fan speed percentage (verified).
#   quiet→1, low→40, medium→60, high→80, powerful→100, auto→102 (dry auto→101)
FAN_B13 = {"auto": 102, "quiet": 1, "low": 40, "medium": 60, "high": 80, "powerful": 100}

def encode_footer_b13(fan: str, mode: str) -> int:
    if mode == "dry" and fan == "auto":
        return 101
    return FAN_B13.get(fan, 102)


# ── Code generator ──────────────────────────────────────

# IR timing constants — chosen so int(pulse / 32.84) hits the correct
# raw-byte tick values from captured signals (0x8c,0x8d,0x12,0x34).
# The real remote has natural ±1-tick jitter; these values produce the
# "center" encoding that the AC device accepts.
_HDR_MARK = 4598      # → raw byte 0x8c  (140 ticks)
_HDR_SPACE = 4631     # → raw byte 0x8d  (141 ticks)
_BIT_MARK = 592       # → raw byte 0x12  (18 ticks)
_ZERO_SPACE = 592     # → raw byte 0x12  (18 ticks)
_ONE_SPACE = 1708     # → raw byte 0x34  (52 ticks)
_SEG_GAP = 5485       # inter-segment gap (~5.5ms, from captures)
_GAP = 109455         # final inter-message gap


def _segment_to_pulses(bits_48: str, gap: int) -> list:
    """Build pulse sequence for one 6-byte (48-bit) segment."""
    pulses = [_HDR_MARK, _HDR_SPACE]
    for bit in bits_48:
        pulses.append(_BIT_MARK)
        pulses.append(_ONE_SPACE if bit == "1" else _ZERO_SPACE)
    pulses.append(_BIT_MARK)  # trailing mark
    pulses.append(gap)        # inter-segment or final gap
    return pulses


def _bytes_to_ir_packet(msg_bytes: bytes) -> bytes:
    """Convert logical protocol bytes to a Broadlink IR packet (base64-ready).

    The remote sends the 18-byte message as three 6-byte segments, each
    prefixed with a header and separated by a 5.5ms gap. This produces
    300 pulses (3 × 100) matching captured signals exactly.
    """
    bits = "".join(f"{b:08b}" for b in msg_bytes)

    pulses = []
    pulses += _segment_to_pulses(bits[:48], _SEG_GAP)
    pulses += _segment_to_pulses(bits[48:96], _SEG_GAP)
    pulses += _segment_to_pulses(bits[96:144], _GAP)

    return pulses_to_data(pulses)


def generate_code(mode: str, temp: int, fan: str) -> str:
    """Generate a Broadlink base64 IR code for the given parameters.

    Builds the 18-byte protocol message and encodes it to a
    Broadlink IR packet ready for base64 transmission.
    """
    b2 = encode_fan_b2(fan, mode)
    b3 = 0xFF - b2
    b4 = encode_temp_b4(temp, mode)
    b5 = 0xFF - b4

    payload = bytes([0xC2, 0x3D, b2, b3, b4, b5])

    b13 = encode_footer_b13(fan, mode)
    b14 = b16 = 0x00
    b15 = 0x00
    if temp == 16:
        b15 = 0x10  # disambiguation for minimum temperature
    if fan == "powerful":
        b15 = 0x02  # fan speed powerful footer marker (all modes)
    ck = sum([0xD5, b13, b14, b15, b16]) % 256
    footer = bytes([0xD5, b13, b14, b15, b16, ck])

    msg_bytes = payload + payload + footer  # 18 bytes
    ir_packet = _bytes_to_ir_packet(msg_bytes)
    return base64.b64encode(ir_packet).decode()


def generate_off_code() -> str:
    """Generate the OFF code."""
    payload = bytes([0xC2, 0x3D, 0x7B, 0x84, 0xE0, 0x1F])
    msg_bytes = payload + payload  # 12 bytes, no footer
    ir_packet = _bytes_to_ir_packet(msg_bytes)
    return base64.b64encode(ir_packet).decode()


# ── Climate lookup tables (SmartIR convention) ──────────

CLIMATE_MODES = ["off", "cool", "heat", "fan_only", "dry"]
FAN_SPEEDS = ["auto", "quiet", "low", "medium", "high", "powerful"]
TEMP_RANGE = list(range(16, 31))


# ── SmartIR JSON builder ────────────────────────────────

def build_smartir(decoded, generate_all=False) -> dict:
    """Build SmartIR-compatible JSON.

    If generate_all=True, generates codes for all temp/mode/fan combinations
    using the derived protocol formulas. Known captures take priority.
    """
    commands: dict = {"off": None}

    # Off code
    for label, d in decoded.items():
        if parse_label(label).get("mode") == "off":
            commands["off"] = d["b64"]
            break
    if commands["off"] is None:
        commands["off"] = generate_off_code()

    # Collect verified codes from captures
    verified = set()
    for label, d in decoded.items():
        p = parse_label(label)
        if p["mode"] in CLIMATE_MODES[1:] and p["temp"] is not None:
            verified.add((p["mode"], p["temp"], p["fan"]))

    for mode in CLIMATE_MODES[1:]:  # skip "off"
        commands[mode] = {}
        fans = FAN_SPEEDS
        for fan in fans:
            commands[mode][fan] = {}
            for temp in TEMP_RANGE:
                temp_key = str(temp)
                key = (mode, temp, fan)
                if key in verified:
                    # Use the actual captured code
                    for label, d in decoded.items():
                        p = parse_label(label)
                        if (p.get("mode"), p.get("temp"), p.get("fan")) == key:
                            commands[mode][fan][temp_key] = d["b64"]
                            break
                elif generate_all:
                    # Generate from formulas
                    code = generate_code(mode, temp, fan)
                    commands[mode][fan][temp_key] = code

    return {
        "manufacturer": "Toshiba",
        "supportedModels": ["Toshiba AC"],
        "supportedController": "Broadlink",
        "commandsEncoding": "Base64",
        "minTemperature": 16.0,
        "maxTemperature": 30.0,
        "precision": 1.0,
        "operationModes": ["heat", "cool", "dry", "fan_only"],
        "fanModes": ["auto", "quiet", "low", "medium", "high", "powerful"],
        "commands": commands,
    }


# ── Display helpers ────────────────────────────────────

def print_protocol_analysis(decoded):
    print("\n═══ Protocol Byte Breakdown ═══")
    print(f"{'Label':<16s} {'Bits':>4s}  Bytes")
    print("-" * 70)
    for label, d in decoded.items():
        b = d["bytes"]
        hex_str = " ".join(f"{x:02X}" for x in b)
        parts = []
        # Check structure
        if len(b) >= 6:
            if b[2] + b[3] == 0xFF:
                parts.append("B2+B3=FF")
            if b[4] + b[5] == 0xFF:
                parts.append("B4+B5=FF")
        if len(b) >= 18:
            ck = sum(b[12:17]) % 256
            if ck == b[17]:
                parts.append("CK=OK")
        flags = "  " + ", ".join(parts) if parts else ""
        print(f"{label:<16s} {len(b)*8:>4d}  {hex_str}{flags}")
    print()

def print_field_mapping(decoded):
    print("═══ Field Mapping ═══")
    print(f"{'Label':<16s} {'B2':>4s} {'B3':>4s} {'B4':>4s} {'B5':>4s} {'B13':>4s}  Temp  Mode  Fan")
    print("-" * 75)
    for label, d in decoded.items():
        b = d["bytes"]
        if len(b) < 6:
            continue
        p = parse_label(label)
        b13 = b[13] if len(b) >= 14 else 0
        print(f"{label:<16s} {b[2]:02X}h  {b[3]:02X}h  {b[4]:02X}h  {b[5]:02X}h  {b13:>4d}  "
              f"{str(p.get('temp') or ''):>4s}  {p.get('mode') or '':>4s}  {p.get('fan') or '':>4s}")
    print()

# ── Main ────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze Broadlink IR captures & generate SmartIR JSON"
    )
    parser.add_argument(
        "capture_file", nargs="?", default="captures/Toshiba_RAS-K281X.txt",
        help="Capture file (label + base64 pairs)",
    )
    parser.add_argument("--json", action="store_true", help="Output SmartIR JSON to stdout")
    parser.add_argument("--missing", action="store_true", help="Show missing combinations")
    parser.add_argument("--save", metavar="FILE", help="Save SmartIR JSON to FILE")
    parser.add_argument(
        "--generate", action="store_true",
        help="Generate inferred codes for ALL temp/mode/fan combos (formulas)",
    )
    args = parser.parse_args()

    signals = read_captures(args.capture_file)
    decoded = analyze_signals(signals)

    print(f"Loaded {len(decoded)} captured signals")
    print_protocol_analysis(decoded)
    print_field_mapping(decoded)

    sj = build_smartir(decoded, generate_all=args.generate)

    # Count verified vs inferred
    verified_count = 0
    inferred_count = 0
    for label, d in decoded.items():
        p = parse_label(label)
        if p["mode"] and p["mode"] != "off":
            verified_count += 1
    for mode in CLIMATE_MODES[1:]:
        if mode in sj["commands"]:
            verified_count += len(sj["commands"][mode])
    # Quick count
    total = sum(
        len(sj["commands"].get(m, {}))
        for m in CLIMATE_MODES[1:]
    ) + (1 if sj["commands"].get("off") else 0)

    if args.generate:
        print(f"\n═══ Generated Codes ═══")
        print(f"  Verified:     {verified_count}")
        print(f"  Total codes:  {total}")
        print(f"  Inferred:     {total - verified_count}")
        print(f"  (codes generated from protocol formulas)")
    else:
        print(f"\n═══ Coverage ═══")
        print(f"  Verified codes: {verified_count}")
        print(f"  Use --generate to produce inferred codes for all combinations")

    if args.missing:
        all_temps = list(range(16, 31))
        all_modes = ["cool", "heat", "fan_only", "dry"]
        missing = []
        have = set()
        for label in decoded:
            p = parse_label(label)
            if p.get("mode") in all_modes and p.get("temp") is not None:
                have.add((p["mode"], p["temp"], p["fan"]))
        for mode in all_modes:
            for temp in all_temps:
                for fan in FAN_SPEEDS:
                    if (mode, temp, fan) not in have:
                        missing.append(f"  {temp} {mode} {fan}")
        if missing:
            print(f"\n  Missing captures ({len(missing)}):")
            for m in missing[:20]:
                print(m)
            if len(missing) > 20:
                print(f"  ... and {len(missing) - 20} more")

    if args.json:
        print("\n═══ SmartIR JSON ═══")
        print(json.dumps(sj, indent=2, ensure_ascii=False))

    if args.save:
        Path(args.save).write_text(
            json.dumps(sj, indent=2, ensure_ascii=False) + "\n"
        )
        print(f"\nSaved to {args.save}")


if __name__ == "__main__":
    main()
