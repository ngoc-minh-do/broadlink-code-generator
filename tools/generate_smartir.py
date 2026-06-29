#!/usr/bin/env python3
"""
IR protocol reverse-engineering & SmartIR JSON generator for Broadlink captures.

Decodes Broadlink base64 captures into byte-level protocol analysis, identifies
which bytes encode temperature/mode/fan, and generates SmartIR-compatible JSON.

Usage:
  uv run python tools/generate_smartir.py captures/Toshiba-JP.txt
  uv run python tools/generate_smartir.py captures/Toshiba-JP.txt --json --save out.json

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

import json
from pathlib import Path

from boardlink_local.protocol import CLIMATE_MODES, FAN_SPEEDS, TEMP_RANGE
from boardlink_local.decoder import read_captures, analyze_signals, parse_label
from boardlink_local.smartir import build_smartir


def print_protocol_analysis(decoded):
    print("\n═══ Protocol Byte Breakdown ═══")
    print(f"{'Label':<16s} {'Bits':>4s}  Bytes")
    print("-" * 70)
    for label, d in decoded.items():
        b = d["bytes"]
        hex_str = " ".join(f"{x:02X}" for x in b)
        parts = []
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


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze Broadlink IR captures & generate SmartIR JSON"
    )
    parser.add_argument(
        "capture_file", nargs="?", default="captures/Toshiba-JP.txt",
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

    verified = set()
    for label in decoded:
        p = parse_label(label)
        if p["mode"] != "off" and p["temp"] is not None:
            verified.add((p["mode"], p["temp"], p["fan"]))
    verified_count = len(verified)

    total = 1 if sj["commands"].get("off") else 0
    for mode in CLIMATE_MODES[1:]:
        if mode in sj["commands"]:
            for fan in sj["commands"][mode]:
                total += len(sj["commands"][mode][fan])

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
        all_modes = ["cool", "heat", "fan_only", "dry", "heat_cool"]
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
