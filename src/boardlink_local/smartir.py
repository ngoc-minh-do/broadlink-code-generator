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
        "supportedModels": [
            "RAS-2210T", "RAS-2210TM", "RAS-2210TS",
            "RAS-2211T", "RAS-2211TL", "RAS-2211TM",
            "RAS-2212T", "RAS-2212TL", "RAS-2212TM",
            "RAS-2213T", "RAS-2213TC", "RAS-2213TL", "RAS-2213TM",
            "RAS-2214T", "RAS-2214TC", "RAS-2214TL", "RAS-2214TM",
            "RAS-221TC",
            "RAS-2510T", "RAS-2510TM", "RAS-2510TS",
            "RAS-2511T", "RAS-2511TL", "RAS-2511TM",
            "RAS-2512T", "RAS-2512TL", "RAS-2512TM",
            "RAS-2513T", "RAS-2513TL", "RAS-2513TM",
            "RAS-2514T", "RAS-2514TL", "RAS-2514TM",
            "RAS-2810T", "RAS-2810TM", "RAS-2810TS",
            "RAS-2811T", "RAS-2811TL", "RAS-2811TM",
            "RAS-2812T", "RAS-2812TL", "RAS-2812TM",
            "RAS-2813T", "RAS-2813TL", "RAS-2813TM",
            "RAS-2814T", "RAS-2814TL", "RAS-2814TM",
            "RAS-2820T", "RAS-2821T", "RAS-2822T", "RAS-2823T", "RAS-2824T",
            "RAS-3610T", "RAS-3610TS",
            "RAS-3611T", "RAS-3611TL",
            "RAS-3612T", "RAS-3612TL",
            "RAS-3613T", "RAS-3613TL",
            "RAS-3614T", "RAS-3614TL",
            "RAS-4010T", "RAS-4010TM", "RAS-4010TS",
            "RAS-4011T", "RAS-4011TL", "RAS-4011TM",
            "RAS-4012T", "RAS-4012TL", "RAS-4012TM",
            "RAS-4013T", "RAS-4013TL", "RAS-4013TM",
            "RAS-4014T", "RAS-4014TL", "RAS-4014TM",
            "RAS-4020T", "RAS-4021T", "RAS-4022T", "RAS-4023T", "RAS-4024T",
            "RAS-5621T",
            "RAS-G221M", "RAS-G251M", "RAS-G281M", "RAS-G361M", "RAS-G401M",
            "RAS-H221M", "RAS-H251M", "RAS-H281M", "RAS-H361M", "RAS-H401M", "RAS-H562M",
            "RAS-H221TK", "RAS-H251TK", "RAS-H281TK",
            "RAS-J221M", "RAS-J251M", "RAS-J281M", "RAS-J361M", "RAS-J401M",
            "RAS-K221M", "RAS-K251M", "RAS-K281M", "RAS-K361M", "RAS-K401M",
            "RAS-K221X", "RAS-K251X", "RAS-K281X", "RAS-K401X",
            "RAS-K221XEX", "RAS-K281XEX", "RAS-K401XEX",
            "RAS-K221XKS", "RAS-K251XKS", "RAS-K281XKS", "RAS-K401XKS",
            "RAS-K221XSY", "RAS-K251XSY", "RAS-K281XSY", "RAS-K401XSY",
            "RAS-N221M", "RAS-N251M", "RAS-N281M", "RAS-N361M", "RAS-N401M",
            "RAS-N221TE", "RAS-N401TE",
            "RAS-N221X", "RAS-N251X", "RAS-N281X", "RAS-N401X",
            "RAS-N221XEX", "RAS-N281XEX", "RAS-N401XEX",
            "RAS-N221XKS", "RAS-N251XKS", "RAS-N281XKS", "RAS-N401XKS",
            "RAS-N221XSY", "RAS-N251XSY", "RAS-N281XSY", "RAS-N401XSY",
        ],
        "supportedController": "Broadlink",
        "commandsEncoding": "Base64",
        "minTemperature": 16.0,
        "maxTemperature": 30.0,
        "precision": 1.0,
        "operationModes": ["heat", "cool", "dry", "fan_only", "heat_cool"],
        "fanModes": ["auto", "quiet", "low", "medium", "high", "powerful"],
        "commands": commands,
    }
