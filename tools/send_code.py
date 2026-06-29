#!/usr/bin/env python3
"""Send an IR code to the Broadlink device.

Usage:
  uv run python tools/send_code.py '<base64>'
  uv run python tools/send_code.py --key '25 cool auto'
  uv run python tools/send_code.py --mode cool --temp 25 --fan auto
"""

import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import broadlink
from broadlink.remote import data_to_pulses

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.generate_smartir import generate_code, generate_off_code

DEVICE_IP = os.environ["BROADLINK_IP"]


def find_device():
    dev = broadlink.discover(discover_ip_address=DEVICE_IP, timeout=5)
    if not dev:
        print("No Broadlink device found at", DEVICE_IP)
        sys.exit(1)
    dev = dev[0]
    dev.auth()
    return dev


def send(dev, b64: str):
    raw = base64.b64decode(b64)
    dev.send_data(raw)
    print("Sent")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send IR code to Broadlink device")
    parser.add_argument("b64", nargs="?", help="Base64 code to send")
    parser.add_argument("--key", help="Send a captured code by label")
    parser.add_argument("--mode", help="Mode: cool, heat, fan_only, dry")
    parser.add_argument("--temp", type=int, help="Temperature (16-30)")
    parser.add_argument("--fan", default="auto", help="Fan speed")
    parser.add_argument("--off", action="store_true", help="Send OFF code")
    args = parser.parse_args()

    dev = find_device()

    if args.off:
        b64 = generate_off_code()
        print("Sending: OFF")
    elif args.key:
        from tools.generate_smartir import read_captures

        capture_path = (
            Path(__file__).resolve().parent.parent / "captures" / "Toshiba-JP.txt"
        )
        signals = read_captures(str(capture_path))
        found = None
        for label, d in signals.items():
            if args.key.lower() in label.lower():
                found = d["b64"]
                print(f"Sending: {label}")
                break
        if not found:
            print(f"No capture matching '{args.key}'")
            sys.exit(1)
        b64 = found
    elif args.mode and args.temp:
        b64 = generate_code(args.mode, args.temp, args.fan)
        print(f"Sending: {args.temp} {args.mode} {args.fan}")
    elif args.b64:
        b64 = args.b64
        print("Sending code")
    else:
        parser.print_help()
        sys.exit(1)

    send(dev, b64)


if __name__ == "__main__":
    main()
