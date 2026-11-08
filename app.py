#!/usr/bin/env python3
"""Kakeai (掛け合い) — a dialogue AI agent that operates PayPal.

PayPal AI Hackathon 2026 entry. Python standard library only.
Run: python3 app.py  →  http://localhost:8765
"""
import json
import os
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

import llm
import mock
import paypal

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(ROOT, "config.json")
LOCK = threading.Lock()


def load_cfg():
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"mock": True}


CFG = load_cfg()


def is_mock():
    return bool(CFG.get("mock", True)) or not CFG.get("paypal_client_id")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.path.join(ROOT, "static"), **kw)

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/status":
            self._send(200, {
                "mock": is_mock(),
                "paypal_configured": bool(CFG.get("paypal_client_id")),
                "llm_configured": bool(CFG.get("gemini_api_key")),
            })
        elif p == "/api/invoices":
            try:
                with LOCK:
                    inv = mock.list_invoices() if is_mock() else paypal.list_invoices(CFG)
                self._send(200, {"invoices": inv, "mock": is_mock()})
            except Exception as e:  # noqa: BLE001
                self._send(502, {"error": str(e)})
        else:
            super().do_GET()

    def do_POST(self):
        p = urlparse(self.path).path
        if p != "/api/chat":
            self._send(404, {"error": "not found"})
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            self._send(400, {"error": "invalid json"})
            return
        msg = (req.get("message") or "").strip()
        if not msg:
            self._send(400, {"error": "empty message"})
            return
        try:
            with LOCK:
                intent = llm.parse_intent(msg, CFG)
                result = mock.execute(intent) if is_mock() else paypal.execute(intent, CFG)
                reply = llm.render_reply(msg, intent, result, CFG)
            self._send(200, {"intent": intent, "result": result, "reply": reply, "mock": is_mock()})
        except Exception as e:  # noqa: BLE001
            self._send(502, {"error": str(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    print("Kakeai running on http://localhost:%d  (mock=%s)" % (port, is_mock()))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()