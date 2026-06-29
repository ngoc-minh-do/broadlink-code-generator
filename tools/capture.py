#!/usr/bin/env python3
"""Capture an IR code from the Broadlink device.

Usage:
  uv run python tools/capture.py
"""

from __future__ import annotations

import base64
import time

from boardlink_local.device import find_device
from boardlink_local.capture import capture, TIMEOUT

device = find_device()
print(f"Connected to {device.host[0]}")
print("Entering learning mode...")

print(f"Press a button on the AC remote within {TIMEOUT} seconds")
b64 = capture(device)
if b64:
    raw = base64.b64decode(b64)
    print("Received!")
    print("Raw bytes:", raw.hex())
    print("Base64:")
    print(b64)
else:
    print("Timeout — no IR signal captured.")
