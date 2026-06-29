"""Broadlink device discovery and authentication."""

from __future__ import annotations

import os
import sys

import broadlink
from dotenv import load_dotenv

load_dotenv()

DEVICE_IP = os.environ["BROADLINK_IP"]


def find_device():
    """Discover and authenticate a Broadlink device at BROADLINK_IP.

    Returns the authenticated device or exits the process on failure.
    """
    dev = broadlink.discover(discover_ip_address=DEVICE_IP, timeout=5)
    if not dev:
        print(f"No Broadlink device found at {DEVICE_IP}", file=sys.stderr)
        sys.exit(1)
    dev = dev[0]
    dev.auth()
    return dev
