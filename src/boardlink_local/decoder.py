"""Pulse-level decoding, capture file I/O, and label parsing."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Dict

from broadlink.remote import data_to_pulses


def reduce_list(items, margin=150):
    result = []
    for item in sorted(set(items), reverse=True):
        if not result or item < result[-1] - margin:
            result.append(item)
    return result


def within_margin(seen, expected, margin=150):
    return abs(seen - expected) <= margin


def classify_pulses(pulses, margin=150):
    marks = pulses[::2]
    spaces = pulses[1::2]
    mark_c = reduce_list(marks, margin)
    space_c = reduce_list(spaces, margin)
    bit_mark = mark_c[-1] if mark_c else 0
    hdr_mark = mark_c[0] if len(mark_c) > 1 else bit_mark
    zero = one = hdr_space = None
    gaps = []
    for v in space_c:
        if 300 <= v <= 900 and zero is None:
            zero = v
        elif 1300 <= v <= 2200 and one is None:
            one = v
        elif 3800 <= v <= 5200 and hdr_space is None:
            hdr_space = v
        elif v > 5200:
            gaps.append(v)
    return {
        "bit_mark": bit_mark, "hdr_mark": hdr_mark,
        "zero_space": zero, "one_space": one, "hdr_space": hdr_space,
        "gaps": gaps, "margin": margin,
    }


def pulses_to_bits(pulses, ctx):
    if not ctx or ctx.get("one_space") is None or ctx.get("zero_space") is None:
        return "", []
    bits = ""
    for i in range(1, len(pulses), 2):
        v = pulses[i]
        if within_margin(v, ctx["one_space"], ctx["margin"]):
            bits += "1"
        elif within_margin(v, ctx["zero_space"], ctx["margin"]):
            bits += "0"
    return bits, []


def bits_to_bytes(bits):
    n = len(bits) // 8
    return [int(bits[i : i + 8], 2) for i in range(0, n * 8, 8)]


def read_captures(path) -> Dict[str, dict]:
    lines = Path(path).read_text().strip().splitlines()
    lines = [l.strip() for l in lines if l.strip()]
    sigs = {}
    for i in range(0, len(lines), 2):
        label = lines[i]
        b64 = lines[i + 1]
        raw = base64.b64decode(b64)
        pulses = data_to_pulses(raw)
        sigs[label] = {"b64": b64, "raw": raw, "pulses": pulses}
    return sigs


def analyze_signals(signals) -> Dict[str, dict]:
    decoded = {}
    for label, d in signals.items():
        ctx = classify_pulses(d["pulses"])
        bits, _ = pulses_to_bits(d["pulses"], ctx)
        b = bits_to_bytes(bits)
        decoded[label] = {
            "b64": d["b64"], "raw": d["raw"],
            "pulses": d["pulses"], "bits": bits, "bytes": b, "ctx": ctx,
        }
    return decoded


def parse_label(label: str) -> dict:
    label = label.strip()
    if label.lower() == "off":
        return {"mode": "off", "temp": None, "fan": None}
    parts = label.split()
    if len(parts) == 3:
        try:
            temp = int(parts[0]) if parts[0].lower() != "x" else None
            mode = parts[1]
            return {"mode": mode, "temp": temp, "fan": parts[2]}
        except ValueError:
            pass
    return {"mode": label, "temp": None, "fan": None}
