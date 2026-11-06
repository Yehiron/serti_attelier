"""Wompi local. Sin puertos publicados ni dependencias; nunca desplegar en producción."""

import hashlib
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

transactions = {}
lock = threading.Lock()
unavailable = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No referencias, tokens ni datos de pedidos en stdout.

    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path)
        with lock:
            if unavailable:
                return self.reply(503, {})
            if path.path == "/v1/transactions":
                reference = parse_qs(path.query).get("reference", [""])[0]
                data = [
                    tx.copy()
                    for tx in transactions.values()
                    if tx["reference"] == reference
                ]
            elif path.path.startswith("/v1/transactions/"):
                data = transactions.get(
                    unquote(path.path.removeprefix("/v1/transactions/"))
                )
                if data is None:
                    return self.reply(404, {})
            else:
                return self.reply(404, {})
        self.reply(200, {"data": data})

    def do_POST(self):
        global unavailable
        if self.path != "/control":
            return self.reply(404, {})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                return self.reply(400, {})
            body = json.loads(self.rfile.read(size))
            tx = body.get("transaction")
            with lock:
                if tx:
                    if (
                        tx["status"]
                        not in {"PENDING", "APPROVED", "DECLINED", "VOIDED", "ERROR"}
                        or type(tx["amount_in_cents"]) is not int
                        or not all(
                            isinstance(tx[k], str) and tx[k]
                            for k in ("id", "reference", "currency")
                        )
                    ):
                        return self.reply(400, {})
                    transactions[tx["id"]] = tx.copy()
                unavailable = bool(body.get("unavailable", False))
            if body.get("emit"):
                event = {
                    "event": "transaction.updated",
                    "data": {"transaction": tx},
                    "timestamp": int(time.time()),
                    "signature": {
                        "properties": [
                            "transaction.id",
                            "transaction.status",
                            "transaction.amount_in_cents",
                        ]
                    },
                }
                value = f"{tx['id']}{tx['status']}{tx['amount_in_cents']}{event['timestamp']}"
                event["signature"]["checksum"] = hashlib.sha256(
                    (value + os.environ["WOMPI_EVENTS_SECRET"]).encode()
                ).hexdigest()
                # Fixed destination: control cannot turn the fake into an arbitrary HTTP proxy.
                request = Request(
                    "http://backend:8000/api/v1/payments/wompi/events",
                    data=json.dumps(event).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request, timeout=15) as response:
                    return self.reply(200, {"webhook_status": response.status})
            self.reply(200, {})
        except (KeyError, TypeError, ValueError):
            self.reply(400, {})
        except OSError:
            self.reply(502, {})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
