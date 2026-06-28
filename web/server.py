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

    def handle_analyze(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        filepath = qs.get("file", ["captures/Toshiba_RAS-K281X.txt"])[0]
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
        print(f"  API      : http://localhost:{PORT}/api/analyze?file=captures/Toshiba_RAS-K281X.txt")
        print(f"  Captures : {CAPTURES}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
            httpd.shutdown()


if __name__ == "__main__":
    main()
