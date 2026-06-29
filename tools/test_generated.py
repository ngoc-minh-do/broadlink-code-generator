#!/usr/bin/env python3
"""
Interactive tester for generated IR codes.

Picks generated codes from the SmartIR JSON, prompts you to press the
matching button on the physical remote, captures via Broadlink, and
compares the captured signal against the generated one.

Usage:
  uv run python tools/test_generated.py
  uv run python tools/test_generated.py --mode cool --fan auto --temps 20,25,30
  uv run python tools/test_generated.py --all --shuffle
"""

import base64
import json
import os
import random
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import broadlink
from broadlink.remote import data_to_pulses

from tools.generate_smartir import (
    classify_pulses,
    pulses_to_bits,
    bits_to_bytes,
    generate_code,
    generate_off_code,
    CLIMATE_MODES,
    FAN_SPEEDS,
    TEMP_RANGE,
)

DEVICE_IP = os.environ["BROADLINK_IP"]
TIMEOUT = 30
JSON_PATH = Path("captures/generated_smartir.json")


def find_device():
    print(f"Discovering Broadlink device at {DEVICE_IP}...")
    dev = broadlink.discover(discover_ip_address=DEVICE_IP, timeout=5)
    if not dev:
        print("No device found.")
        sys.exit(1)
    dev = dev[0]
    dev.auth()
    return dev


def capture(dev, timeout=TIMEOUT):
    """Enter learning mode and capture one IR packet. Returns base64 string."""
    dev.enter_learning()
    print("  Press the button on the remote...", end="", flush=True)
    for _ in range(timeout):
        time.sleep(1)
        try:
            packet = dev.check_data()
            if packet:
                print(" captured!")
                return base64.b64encode(packet).decode()
        except Exception:
            pass
    print(" timeout!")
    return None


def compare_signals(gen_b64, cap_b64):
    """Decode both base64 and return (match, gen_bytes, cap_bytes, detail, gen_pulses, cap_pulses)."""
    try:
        gen_raw = base64.b64decode(gen_b64)
        gen_pulses = data_to_pulses(gen_raw)
        gen_ctx = classify_pulses(gen_pulses)
        gen_bits, _ = pulses_to_bits(gen_pulses, gen_ctx)
        gen_bytes = bits_to_bytes(gen_bits)
    except Exception as e:
        return False, None, None, None, f"gen decode: {e}", None

    try:
        cap_raw = base64.b64decode(cap_b64)
        cap_pulses = data_to_pulses(cap_raw)
        cap_ctx = classify_pulses(cap_pulses)
        cap_bits, _ = pulses_to_bits(cap_pulses, cap_ctx)
        cap_bytes = bits_to_bytes(cap_bits)
    except Exception as e:
        return False, gen_bytes, None, gen_pulses, f"cap decode: {e}", None

    byte_match = gen_bytes == cap_bytes
    pulse_match = len(gen_pulses) == len(cap_pulses)

    parts = []
    if not byte_match and gen_bytes and cap_bytes:
        diffs = []
        for i in range(min(len(gen_bytes), len(cap_bytes))):
            if gen_bytes[i] != cap_bytes[i]:
                diffs.append(f"B{i}:{gen_bytes[i]:02X}h≠{cap_bytes[i]:02X}h")
        if diffs:
            parts.append(" ".join(diffs[:5]))
        if len(gen_bytes) != len(cap_bytes):
            parts.append(f"len:{len(gen_bytes)}≠{len(cap_bytes)}")
    if not pulse_match:
        parts.append(f"pulses:{len(gen_pulses)}≠{len(cap_pulses)}")

    detail = " ".join(parts) if parts else ""
    return byte_match, gen_bytes, cap_bytes, detail, gen_pulses, cap_pulses


def load_test_list(args):
    """Build list of (mode, temp, fan) tuples to test."""
    tests = []

    if args.all:
        for mode in CLIMATE_MODES[1:]:  # skip "off"
            fans = FAN_SPEEDS
            for temp in TEMP_RANGE:
                for fan in fans:
                    # Skip fan-only non-auto temps (all same code anyway)
                    if mode == "fan_only" and fan != "auto" and temp != 25:
                        continue
                    tests.append((mode, temp, fan))
    elif args.temps:
        for mode in (args.mode or ["cool", "heat", "fan_only", "dry", "heat_cool"]):
            fans = args.fan or FAN_SPEEDS
            for temp in args.temps:
                for fan in fans:
                    tests.append((mode, temp, fan))
    else:
        modes = args.mode or ["cool", "heat", "fan_only", "dry", "heat_cool"]
        mode_defaults = {
            "cool": [("cool", 25, "auto"), ("cool", 20, "auto")],
            "heat": [("heat", 25, "auto")],
            "dry": [("dry", 25, "auto")],
            "fan_only": [("fan_only", 0, "auto")],
            "heat_cool": [("heat_cool", 25, "auto")],
        }
        tests = []
        for mode in modes:
            tests.extend(mode_defaults.get(mode, [(mode, 25, "auto")]))

    if args.shuffle:
        random.shuffle(tests)

    return tests


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Test generated IR codes against physical remote"
    )
    parser.add_argument("--all", action="store_true", help="Test all generated combinations")
    parser.add_argument("--mode", nargs="+", help="Mode(s) to test: cool, heat, fan_only, dry")
    parser.add_argument("--fan", nargs="+", help="Fan speed(s) to test: auto, quiet, low, medium, high, powerful")
    parser.add_argument("--temps", nargs="+", type=int, help="Temperatures to test, e.g. 20 25 30")
    parser.add_argument("--shuffle", action="store_true", help="Randomize test order")
    parser.add_argument("--count", type=int, default=0, help="Limit number of tests")
    parser.add_argument("--skip-off", action="store_true", help="Skip OFF test")
    args = parser.parse_args()

    if args.mode:
        args.mode = [m.replace("fan", "fan_only") if m == "fan" else m for m in args.mode]

    tests = load_test_list(args)
    if args.count and args.count < len(tests):
        tests = tests[: args.count]

    if not tests:
        print("No tests selected.")
        return

    # Add off test if not skipped
    if not args.skip_off:
        tests.insert(0, ("off", 0, ""))

    print(f"\n{'='*60}")
    print(f"Testing {len(tests)} code(s) against physical remote")
    print(f"Device IP: {DEVICE_IP}")
    print(f"{'='*60}\n")

    dev = find_device()

    passed = 0
    failed = 0
    skipped = 0

    for i, test in enumerate(tests):
        mode, temp, fan = test

        if mode == "off":
            label = "OFF"
            gen_b64 = generate_off_code()
        else:
            label = f"{temp} {mode} {fan}"
            gen_b64 = generate_code(mode, temp, fan)

        print(f"[{i+1}/{len(tests)}] {label}")
        cap_b64 = capture(dev)

        if cap_b64 is None:
            print("  ⚠  No signal captured — skipped")
            skipped += 1
            continue

        match, gen_b, cap_b, detail, gen_p, cap_p = compare_signals(gen_b64, cap_b64)

        pulse_info = ""
        if gen_p is not None:
            pulse_info = f"  gen pulses={len(gen_p)}"
            if cap_p is not None:
                pulse_info += f"  cap pulses={len(cap_p)}"
                if len(gen_p) != len(cap_p):
                    pulse_info += "  ✗"
                else:
                    pulse_info += "  ✓"

        if match:
            print(f"  ✓ MATCH{pulse_info}")
            passed += 1
        else:
            print(f"  ✗ MISMATCH{pulse_info} {detail}")
            if gen_b:
                gen_hex = " ".join(f"{x:02X}" for x in gen_b[:6])
                print(f"    gen:  [{gen_hex}...]")
            if cap_b:
                cap_hex = " ".join(f"{x:02X}" for x in cap_b[:6])
                print(f"    cap:  [{cap_hex}...]")
            failed += 1

        print()

    print(f"{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
