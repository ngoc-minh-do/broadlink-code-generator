#!/usr/bin/env python3
"""HTTP server for the IR Learner & SmartIR Builder web app.

Serves:
    /                    -> web/index.html
    /captures/*          -> captures/*.txt
    /api/analyze?file=X  -> runs protocol analysis, returns JSON
    /*                   -> web/* (static assets)
"""

import http.server
import json
import os
import socketserver
import sys
import urllib.parse
from pathlib import Path

PORT = int(os.environ.get("PORT", "8080"))
ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CAPTURES = ROOT / "captures"

sys.path.insert(0, str(ROOT))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def translate_path(self, path):
        p = super().translate_path(path)
        if path.startswith("/captures/"):
            rel = path[len("/captures/"):]
            return str(CAPTURES / rel)
        return p

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/analyze":
            self.handle_analyze(parsed)
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/decode":
            self.handle_decode()
            return
        if parsed.path == "/api/compare":
            self.handle_compare()
            return
        self.send_json({"error": "Not found"}, 404)

    def handle_decode(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        base64_list = payload.get("codes", [])
        if not base64_list:
            self.send_json({"error": "No codes provided"}, 400)
            return

        try:
            from tools.generate_smartir import classify_pulses, pulses_to_bits, bits_to_bytes
            from broadlink.remote import data_to_pulses
            import base64
        except ImportError as e:
            self.send_json({"error": f"Import failed: {e}"}, 500)
            return

        results = []
        for item in base64_list:
            label = item.get("label", "")
            b64 = item.get("b64", "")
            if not b64:
                continue
            try:
                raw = base64.b64decode(b64)
                pulses = data_to_pulses(raw)
                ctx = classify_pulses(pulses)
                bits, _ = pulses_to_bits(pulses, ctx)
                b = bits_to_bytes(bits)
            except Exception as e:
                results.append({"label": label, "b64": b64, "error": str(e)})
                continue

            entry = {
                "label": label,
                "nbits": len(bits),
                "nbytes": len(b),
                "bytes_hex": [f"{x:02X}" for x in b],
                "pulse_count": len(pulses),
                "has_footer": len(b) >= 18,
                "is_off": len(b) == 12,
            }
            # Protocol checks
            if len(b) >= 6:
                entry["complement_b2b3"] = b[2] + b[3] == 0xFF
                entry["complement_b4b5"] = b[4] + b[5] == 0xFF
            if len(b) >= 18:
                entry["checksum_ok"] = sum(b[12:17]) % 256 == b[17]
                entry["b13_value"] = b[13]
            results.append(entry)

        self.send_json({"results": results})

    def handle_compare(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        b64_a = payload.get("code_a", "")
        b64_b = payload.get("code_b", "")
        if not b64_a or not b64_b:
            self.send_json({"error": "Both code_a and code_b required"}, 400)
            return

        try:
            from tools.generate_smartir import classify_pulses, pulses_to_bits, bits_to_bytes
            from broadlink.remote import data_to_pulses
            import base64
        except ImportError as e:
            self.send_json({"error": f"Import failed: {e}"}, 500)
            return

        def decode_one(b64):
            raw = base64.b64decode(b64)
            pulses = data_to_pulses(raw)
            ctx = classify_pulses(pulses)
            bits, _ = pulses_to_bits(pulses, ctx)
            b = bits_to_bytes(bits)
            # Extract timing values from ctx
            timing = {
                "hdr_mark": ctx.get("hdr_mark"),
                "hdr_space": ctx.get("hdr_space"),
                "bit_mark": ctx.get("bit_mark"),
                "zero_space": ctx.get("zero_space"),
                "one_space": ctx.get("one_space"),
            }
            return {
                "pulses": pulses,
                "nbits": len(bits),
                "bits": bits,
                "nbytes": len(b),
                "bytes_hex": [f"{x:02X}" for x in b],
                "timing": timing,
                "total_time_us": sum(pulses),
            }

        try:
            a = decode_one(b64_a)
            b = decode_one(b64_b)
        except Exception as e:
            self.send_json({"error": f"Decode failed: {e}"}, 400)
            return

        # Build per-pulse diff
        max_len = max(len(a["pulses"]), len(b["pulses"]))
        pulse_diff = []
        diff_count = 0
        for i in range(max_len):
            pa = a["pulses"][i] if i < len(a["pulses"]) else None
            pb = b["pulses"][i] if i < len(b["pulses"]) else None
            same = pa == pb
            if not same and pa is not None and pb is not None:
                diff_count += 1
            pulse_type = "mark" if i % 2 == 0 else "space"
            pulse_diff.append({
                "index": i,
                "type": pulse_type,
                "pulse_a": pa,
                "pulse_b": pb,
                "same": same,
                "delta": (pb - pa) if (pa is not None and pb is not None) else None,
            })

        # Bit-level diff
        bit_diff = None
        if len(a["bits"]) == len(b["bits"]):
            bit_diffs = []
            for i in range(len(a["bits"])):
                if a["bits"][i] != b["bits"][i]:
                    bit_diffs.append({"index": i, "a": a["bits"][i], "b": b["bits"][i]})
            bit_diff = {
                "len_a": len(a["bits"]),
                "len_b": len(b["bits"]),
                "diff_count": len(bit_diffs),
                "diffs": bit_diffs[:50],  # limit for display
            }

        self.send_json({
            "a": {
                "pulse_count": len(a["pulses"]),
                "total_time_us": a["total_time_us"],
                "nbits": a["nbits"],
                "nbytes": a["nbytes"],
                "bytes_hex": a["bytes_hex"],
                "timing": a["timing"],
            },
            "b": {
                "pulse_count": len(b["pulses"]),
                "total_time_us": b["total_time_us"],
                "nbits": b["nbits"],
                "nbytes": b["nbytes"],
                "bytes_hex": b["bytes_hex"],
                "timing": b["timing"],
            },
            "pulses_a": a["pulses"],
            "pulses_b": b["pulses"],
            "pulse_diff": pulse_diff,
            "diff_count": diff_count,
            "bit_diff": bit_diff,
        })

    def handle_analyze(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        filepath = qs.get("file", ["captures/Toshiba-JP_RAS‒G221M.txt"])[0]
        fullpath = ROOT / filepath

        try:
            from tools.generate_smartir import (
                read_captures,
                analyze_signals,
                generate_smartir,
                find_missing,
                classify_pulses,
                pulses_to_bits,
                bits_to_bytes,
            )
        except ImportError as e:
            self.send_json({"error": f"Import failed: {e}"}, 500)
            return

        if not fullpath.exists():
            self.send_json({"error": f"File not found: {filepath}"}, 404)
            return

        signals = read_captures(str(fullpath))
        decoded = analyze_signals(signals)

        # Build byte-level summary
        entries = []
        for label, d in decoded.items():
            b = d["bytes"]
            entries.append({
                "label": label,
                "nbits": len(d["bits"]),
                "nbytes": len(b),
                "pulse_count": len(d["pulses"]),
                "bytes_hex": [f"{x:02X}" for x in b],
                "b64": d["b64"],
                "has_footer": len(b) >= 18,
                "complement_b2b3": len(b) >= 6 and b[2] + b[3] == 0xFF,
                "complement_b4b5": len(b) >= 6 and b[4] + b[5] == 0xFF,
                "checksum_ok": (
                    len(b) >= 18 and sum(b[12:17]) % 256 == b[17]
                ),
            })

        sj = generate_smartir(decoded)
        missing, suggestions = find_missing(decoded)

        self.send_json({
            "captures": len(decoded),
            "entries": entries,
            "smartir": sj,
            "missing_count": len(missing),
            "suggestions": suggestions,
        })

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.address_string()}] {args[0]}\n")


def main():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving at http://localhost:{PORT}")
        print(f"  App      : http://localhost:{PORT}/")
        print(f"  API      : http://localhost:{PORT}/api/analyze?file=captures/Toshiba-JP_RAS‒G221M.txt")
        print(f"  Captures : {CAPTURES}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
            httpd.shutdown()


if __name__ == "__main__":
    main()
