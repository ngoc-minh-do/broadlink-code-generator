#!/usr/bin/env python3
"""Guided interactive tool to capture missing IR codes.

Reads existing captures, computes missing (temp, mode, fan) combos,
and guides you through capturing them with a Broadlink device.
Auto-saves after each capture so progress is never lost.

Usage:
  uv run python tools/capture_missing.py
  uv run python tools/capture_missing.py --mode heat
  uv run python tools/capture_missing.py --mode cool heat --fan auto
  uv run python tools/capture_missing.py --dry-run
  uv run python tools/capture_missing.py --fan-variants
"""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import broadlink

from tools.generate_smartir import parse_label

DEVICE_IP = os.environ["BROADLINK_IP"]
TIMEOUT = 30
CAPTURE_PATH = Path("captures/Toshiba-JP_RAS‒G221M.txt")

CLIMATE_MODES = ["cool", "heat", "dry", "fan_only"]
FAN_SPEEDS = ["auto", "quiet", "low", "medium", "high", "powerful"]
TEMP_RANGE = list(range(16, 31))


def read_existing_labels(path: Path) -> set[tuple[str | None, int | None, str | None]]:
    lines = path.read_text().strip().splitlines()
    lines = [l.strip() for l in lines if l.strip()]
    existing = set()
    for i in range(0, len(lines), 2):
        label = lines[i]
        p = parse_label(label)
        existing.add((p["mode"], p["temp"], p["fan"]))
    return existing


def compute_missing(
    existing: set,
    modes: list[str] | None = None,
    fans: list[str] | None = None,
    fan_variants: bool = False,
) -> list[tuple[str, int | None, str]]:
    target_modes = [m for m in CLIMATE_MODES if modes is None or m in modes]
    target_fans = FAN_SPEEDS if fans is None else fans

    stage1: list = []
    stage2: list = []

    for mode in target_modes:
        if mode == "fan_only":
            for fan in target_fans:
                key = (mode, None, fan)
                if key not in existing:
                    stage1.append(key)
            continue

        for temp in TEMP_RANGE:
            base_fan = target_fans[0]
            key = (mode, temp, base_fan)
            if key not in existing:
                stage1.append(key)
            elif fan_variants:
                for fan in target_fans[1:]:
                    fkey = (mode, temp, fan)
                    if fkey not in existing:
                        stage2.append(fkey)

    return stage1 + stage2


def find_device():
    print(f"Discovering Broadlink at {DEVICE_IP}...", end=" ", flush=True)
    dev = broadlink.discover(discover_ip_address=DEVICE_IP, timeout=5)
    if not dev:
        print("FAILED")
        sys.exit(1)
    dev = dev[0]
    dev.auth()
    print("connected.")
    return dev


def capture(dev, timeout=TIMEOUT) -> str | None:
    dev.enter_learning()
    print("  Press button on remote...", end="", flush=True)
    for _ in range(timeout):
        time.sleep(1)
        try:
            packet = dev.check_data()
            if packet:
                b64 = base64.b64encode(packet).decode()
                print(f" captured! ({len(packet)} bytes)")
                return b64
        except Exception:
            pass
    print(" timeout!")
    return None


def format_label(mode: str, temp: int | None, fan: str) -> str:
    if mode == "off":
        return "off"
    if temp is None:
        return f"x {mode} {fan}"
    return f"{temp} {mode} {fan}"


def append_capture(path: Path, label: str, b64: str):
    with open(path, "a") as f:
        if path.stat().st_size > 0:
            f.write("\n")
        f.write(f"{label}\n{b64}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Capture missing IR codes interactively")
    parser.add_argument("--mode", nargs="+", help="Mode(s): cool, heat, dry, fan_only")
    parser.add_argument("--fan", nargs="+", help="Fan(s): auto, quiet, low, medium, high, powerful")
    parser.add_argument("--dry-run", action="store_true", help="Show missing combos without capturing")
    parser.add_argument("--fan-variants", action="store_true", help="Also capture non-primary fan variants")
    parser.add_argument("--path", default=str(CAPTURE_PATH), help="Capture file path")
    args = parser.parse_args()

    if args.mode:
        args.mode = [m.replace("fan", "fan_only") for m in args.mode]

    path = Path(args.path)
    if not path.exists():
        print(f"Capture file not found: {path}")
        sys.exit(1)

    existing = read_existing_labels(path)
    missing = compute_missing(existing, args.mode, args.fan, args.fan_variants)

    print(f"\n{'='*60}")
    print(f"Capture file: {path}")
    print(f"Already captured: {len(existing)} combos")
    print(f"Missing: {len(missing)} combos")
    if missing:
        mode_counts = {}
        for m, _, _ in missing:
            mode_counts[m] = mode_counts.get(m, 0) + 1
        for mode, count in sorted(mode_counts.items()):
            print(f"  {mode}: {count}")
    print(f"{'='*60}")

    if args.dry_run:
        if missing:
            print("\nMissing combinations:")
            for mode, temp, fan in missing:
                print(f"  {format_label(mode, temp, fan)}")
        else:
            print("\nAll combinations captured.")
        return

    if not missing:
        print("\nAll combinations captured.")
        return

    try:
        dev = find_device()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return

    captured_count = 0
    skipped_count = 0
    interrupted = False

    for i, (mode, temp, fan) in enumerate(missing):
        label = format_label(mode, temp, fan)
        print(f"\n[{i+1}/{len(missing)}] Set remote to: {label}")
        print("  (Ctrl+C to quit)")

        try:
            b64 = capture(dev)
        except KeyboardInterrupt:
            interrupted = True
            print()
            break

        if b64 is not None:
            append_capture(path, label, b64)
            print(f"  Saved to {path}")
            captured_count += 1
        else:
            print("  Skipped.")
            skipped_count += 1

    print(f"\n{'='*60}")
    print(f"Session results: {captured_count} captured, {skipped_count} skipped")
    if interrupted:
        print("(interrupted — progress saved)")
    print(f"Remaining: {len(missing) - captured_count - skipped_count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
