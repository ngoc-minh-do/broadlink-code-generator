"""IR protocol constants, field encoders, and code generators."""

from __future__ import annotations

import base64

from broadlink.remote import pulses_to_data

# ── Climate lookup tables ─────────────────────────────────

CLIMATE_MODES = ["off", "cool", "heat", "fan_only", "dry", "heat_cool"]
FAN_SPEEDS = ["auto", "quiet", "low", "medium", "high", "powerful"]
TEMP_RANGE = list(range(16, 31))

# ── Temperature → B4 upper nibble ─────────────────────────
# Verified from all 15 heat captures.
# Same encoding across all modes (cool, heat, dry).
# 16 and 17°C share the B4 nibble; footer B15=0x10 disambiguates 16°C.

TEMP_NIB = {
    16: 0x0, 17: 0x0,
    18: 0x1, 19: 0x3,
    20: 0x2, 21: 0x6,
    22: 0x7, 23: 0x5,
    24: 0x4, 25: 0xC,
    26: 0xD, 27: 0x9,
    28: 0x8, 29: 0xA,
    30: 0xB,
}

# ── Fan speed to B2 encoding ──────────────────────────────
# auto=0xBF, quiet=0xFF, low=0x9F, medium=0x5F, high=0x3F, powerful=0x3F
# dry/heat_cool always auto fan: B2 = 0x1F (not 0xBF)

FAN_B2 = {
    "auto": 0xBF,
    "quiet": 0xFF,
    "low": 0x9F,
    "medium": 0x5F,
    "high": 0x3F,
    "powerful": 0x3F,
}

# Footer B13: fan speed percentage
# quiet→1, low→40, medium→60, high→80, powerful→100, auto→102 (dry auto→101)

FAN_B13 = {
    "auto": 102,
    "quiet": 1,
    "low": 40,
    "medium": 60,
    "high": 80,
    "powerful": 100,
}


def encode_temp_b4(temp: int, mode: str) -> int:
    """Return the B4 byte value (upper nibble = temperature, lower = mode)."""
    if mode == "fan_only":
        return 0xE4

    temp_nib = TEMP_NIB.get(temp, 0x0)
    mode_nibs = {
        "cool": 0x0, "fan_only": 0x4, "heat": 0xC,
        "dry": 0x4, "heat_cool": 0x8,
    }
    mode_nib = mode_nibs.get(mode, 0x0)
    return (temp_nib << 4) | mode_nib


def encode_fan_b2(fan: str, mode: str) -> int:
    if mode in ("dry", "heat_cool"):
        return 0x1F
    return FAN_B2.get(fan, 0xBF)


def encode_footer_b13(fan: str, mode: str) -> int:
    if mode in ("dry", "heat_cool"):
        return 101
    return FAN_B13.get(fan, 102)


# ── IR timing constants ───────────────────────────────────
# Chosen so int(pulse / 32.84) hits the correct raw-byte tick
# values from captured signals (0x8c,0x8d,0x12,0x34).

_HDR_MARK = 4598
_HDR_SPACE = 4631
_BIT_MARK = 592
_ZERO_SPACE = 592
_ONE_SPACE = 1708
_SEG_GAP = 5485
_GAP = 109455


def _segment_to_pulses(bits_48: str, gap: int) -> list:
    """Build pulse sequence for one 6-byte (48-bit) segment."""
    pulses = [_HDR_MARK, _HDR_SPACE]
    for bit in bits_48:
        pulses.append(_BIT_MARK)
        pulses.append(_ONE_SPACE if bit == "1" else _ZERO_SPACE)
    pulses.append(_BIT_MARK)
    pulses.append(gap)
    return pulses


def _bytes_to_ir_packet(msg_bytes: bytes) -> bytes:
    """Convert logical protocol bytes to a Broadlink IR packet (base64-ready).

    The remote sends the 18-byte message as three 6-byte segments.
    OFF (12 bytes) → 2 segments (200 pulses), normal (18 bytes) → 3 segments (300 pulses).
    """
    bits = "".join(f"{b:08b}" for b in msg_bytes)
    total_bits = len(bits)

    pulses: list = []
    for offset in range(0, total_bits, 48):
        segment_bits = bits[offset : offset + 48]
        gap = _GAP if offset + 48 >= total_bits else _SEG_GAP
        pulses += _segment_to_pulses(segment_bits, gap)

    return pulses_to_data(pulses)


def generate_code(mode: str, temp: int, fan: str) -> str:
    """Generate a Broadlink base64 IR code for the given parameters."""
    b2 = encode_fan_b2(fan, mode)
    b3 = 0xFF - b2
    b4 = encode_temp_b4(temp, mode)
    b5 = 0xFF - b4

    payload = bytes([0xC2, 0x3D, b2, b3, b4, b5])
    b13 = encode_footer_b13(fan, mode)
    b14 = b16 = 0x00
    b15 = 0x00
    if temp == 16:
        b15 = 0x10
    if fan == "powerful":
        b15 = 0x02
    ck = sum([0xD5, b13, b14, b15, b16]) % 256
    footer = bytes([0xD5, b13, b14, b15, b16, ck])

    msg_bytes = payload + payload + footer
    ir_packet = _bytes_to_ir_packet(msg_bytes)
    return base64.b64encode(ir_packet).decode()


def generate_off_code() -> str:
    """Generate the OFF code."""
    payload = bytes([0xC2, 0x3D, 0x7B, 0x84, 0xE0, 0x1F])
    msg_bytes = payload + payload
    ir_packet = _bytes_to_ir_packet(msg_bytes)
    return base64.b64encode(ir_packet).decode()
