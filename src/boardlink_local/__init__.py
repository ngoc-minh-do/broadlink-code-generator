"""Shared library for Broadlink IR capture, decoding, and SmartIR generation."""

from boardlink_local.device import find_device
from boardlink_local.capture import capture
from boardlink_local.protocol import (
    CLIMATE_MODES,
    FAN_SPEEDS,
    TEMP_RANGE,
    generate_code,
    generate_off_code,
)
from boardlink_local.decoder import (
    classify_pulses,
    pulses_to_bits,
    bits_to_bytes,
    read_captures,
    analyze_signals,
    parse_label,
)

__all__ = [
    "find_device",
    "capture",
    "CLIMATE_MODES",
    "FAN_SPEEDS",
    "TEMP_RANGE",
    "generate_code",
    "generate_off_code",
    "classify_pulses",
    "pulses_to_bits",
    "bits_to_bytes",
    "read_captures",
    "analyze_signals",
    "parse_label",
]
