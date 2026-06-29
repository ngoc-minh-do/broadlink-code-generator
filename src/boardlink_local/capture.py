"""IR capture helpers for Broadlink learning mode."""

from __future__ import annotations

import base64
import time

TIMEOUT = 30


def capture(dev, timeout=TIMEOUT):
    """Enter learning mode and capture one IR packet.

    Returns base64-encoded string on success, None on timeout.
    """
    dev.enter_learning()
    for _ in range(timeout):
        time.sleep(1)
        try:
            packet = dev.check_data()
            if packet:
                return base64.b64encode(packet).decode()
        except Exception:
            pass
    return None
