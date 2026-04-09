#!/usr/bin/env python3
"""
Leads dashboard server — serves data/leads.csv as a JSON API.
Run: python server.py
Open: http://localhost:5050
"""

import csv
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from config import config

PORT = 5050
LEADS_PATH = Path(config.leads_csv)
FRONTEND_PATH = Path(__file__).parent / "frontend" / "index.html"


def read_leads() -> list[dict]:
    if not LEADS_PATH.exists():
        return []
    with open(LEADS_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Only log errors
        if "404" in (args[1] if len(args) > 1 else ""):
            super().log_message(fmt, *args)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/leads":
            leads = read_leads()
            # Optional filter
            qs = parse_qs(parsed.query)
            query = qs.get("q", [""])[0].lower()
            if query:
                leads = [
                    l for l in leads
                    if query in l.get("company", "").lower()
                    or query in l.get("contact_name", "").lower()
                    or query in l.get("reason_to_reach_out", "").lower()
                ]
            body = json.dumps({"leads": leads, "total": len(leads)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        elif parsed.path in ("/", "/index.html"):
            if FRONTEND_PATH.exists():
                content = FRONTEND_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Frontend not found — run from project root")

        else:
            self.send_error(404)


if __name__ == "__main__":
    print(f"Outreach Leads Dashboard → http://localhost:{PORT}")
    print(f"Leads file: {LEADS_PATH.resolve()}")
    print("Press Ctrl+C to stop.\n")
    HTTPServer(("", PORT), Handler).serve_forever()
