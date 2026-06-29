"""SmartIR JSON builder from decoded captures and protocol formulas."""

from __future__ import annotations

from boardlink_local.protocol import (
    CLIMATE_MODES,
    FAN_SPEEDS,
    TEMP_RANGE,
    generate_code,
    generate_off_code,
)
from boardlink_local.decoder import parse_label


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

    for mode in CLIMATE_MODES[1:]:
        commands[mode] = {}
        for fan in FAN_SPEEDS:
            commands[mode][fan] = {}
            for temp in TEMP_RANGE:
                temp_key = str(temp)
                key = (mode, temp, fan)
                if key in verified:
                    for label, d in decoded.items():
                        p = parse_label(label)
                        if (p.get("mode"), p.get("temp"), p.get("fan")) == key:
                            commands[mode][fan][temp_key] = d["b64"]
                            break
                elif generate_all:
                    code = generate_code(mode, temp, fan)
                    commands[mode][fan][temp_key] = code

    return {
        "manufacturer": "Toshiba JP",
        "supportedModels": ["RAS‒G221M", "RAS-K281X"],
        "supportedController": "Broadlink",
        "commandsEncoding": "Base64",
        "minTemperature": 16.0,
        "maxTemperature": 30.0,
        "precision": 1.0,
        "operationModes": ["heat", "cool", "dry", "fan_only", "heat_cool"],
        "fanModes": ["auto", "quiet", "low", "medium", "high", "powerful"],
        "commands": commands,
    }
