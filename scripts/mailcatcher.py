#!/usr/bin/env python3
"""Minimal development mail catcher with a Mailpit-compatible read API.

Docker Compose runs the real Mailpit image. This is the no-Docker fallback used
by CI images and sandboxes, so the end-to-end email flows actually run instead
of being skipped.

It accepts SMTP on :1025 and serves the two Mailpit endpoints the E2E suite
reads:

    GET /api/v1/search?query=to:<address>   -> {"messages": [{"ID": ...}]}
    GET /api/v1/message/<id>                -> {"Text": "..."}

Messages are held in memory only and are never written to disk. This is a
development tool: it performs no authentication and must never be exposed
outside a disposable environment.
"""

from __future__ import annotations

import asyncio
import email
import json
import sys
import threading
import uuid
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

SMTP_PORT = 1025
HTTP_PORT = 8025
#: Bounded so a runaway test cannot exhaust memory.
MAX_MESSAGES = 500

_messages: list[dict[str, Any]] = []
_lock = threading.Lock()


def _store(raw: bytes, recipients: list[str]) -> None:
    parsed: Message = email.message_from_bytes(raw)
    if parsed.is_multipart():
        parts = [
            part.get_payload(decode=True) or b""
            for part in parsed.walk()
            if part.get_content_type() == "text/plain"
        ]
        text = b"\n".join(parts).decode("utf-8", errors="replace")
    else:
        payload = parsed.get_payload(decode=True) or b""
        text = payload.decode("utf-8", errors="replace")

    with _lock:
        _messages.insert(
            0,
            {
                "ID": uuid.uuid4().hex,
                "To": [r.lower() for r in recipients],
                "Subject": parsed.get("Subject", ""),
                "Text": text,
            },
        )
        del _messages[MAX_MESSAGES:]


class _SmtpProtocol(asyncio.Protocol):
    """Just enough SMTP to accept a message from smtplib."""

    def __init__(self) -> None:
        self.buffer = b""
        self.in_data = False
        self.data = b""
        self.recipients: list[str] = []
        self.transport: asyncio.Transport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        self._send("220 originlens-mailcatcher")

    def _send(self, line: str) -> None:
        if self.transport:
            self.transport.write(line.encode() + b"\r\n")

    def data_received(self, data: bytes) -> None:
        self.buffer += data
        while b"\r\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\r\n", 1)
            self._handle(line)

    def _handle(self, raw: bytes) -> None:
        if self.in_data:
            if raw == b".":
                self.in_data = False
                _store(self.data, self.recipients)
                self.data = b""
                self.recipients = []
                self._send("250 OK")
            else:
                self.data += raw.rstrip(b"\r") + b"\n"
            return

        line = raw.decode("utf-8", errors="replace")
        command = line.split(" ", 1)[0].upper()

        if command in {"HELO", "EHLO"}:
            self._send("250-originlens-mailcatcher")
            self._send("250 OK")
        elif command == "MAIL":
            self._send("250 OK")
        elif command == "RCPT":
            if "<" in line and ">" in line:
                self.recipients.append(line[line.index("<") + 1 : line.rindex(">")])
            self._send("250 OK")
        elif command == "DATA":
            self.in_data = True
            self._send("354 End data with <CR><LF>.<CR><LF>")
        elif command == "RSET":
            self.data = b""
            self.recipients = []
            self._send("250 OK")
        elif command == "QUIT":
            self._send("221 Bye")
            if self.transport:
                self.transport.close()
        elif command == "NOOP":
            self._send("250 OK")
        else:
            self._send("250 OK")


class _ReadApi(BaseHTTPRequestHandler):
    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/v1/search":
            query = parse_qs(parsed.query).get("query", [""])[0]
            target = query[3:].lower() if query.startswith("to:") else ""
            with _lock:
                matches = [
                    {"ID": m["ID"], "Subject": m["Subject"]}
                    for m in _messages
                    if not target or target in m["To"]
                ]
            self._json({"messages": matches, "total": len(matches)})
            return

        if parsed.path.startswith("/api/v1/message/"):
            wanted = parsed.path.rsplit("/", 1)[-1]
            with _lock:
                found = next((m for m in _messages if m["ID"] == wanted), None)
            if found is None:
                self._json({"error": "not found"}, status=404)
            else:
                self._json({"ID": found["ID"], "Text": found["Text"], "Subject": found["Subject"]})
            return

        if parsed.path == "/api/v1/messages":
            with _lock:
                self._json({"total": len(_messages)})
            return

        self._json({"error": "not found"}, status=404)

    def do_DELETE(self) -> None:
        with _lock:
            _messages.clear()
        self._json({"deleted": True})

    def log_message(self, *_: object) -> None:
        """Silence per-request logging."""


async def _serve_smtp() -> None:
    loop = asyncio.get_running_loop()
    server = await loop.create_server(_SmtpProtocol, "127.0.0.1", SMTP_PORT)
    async with server:
        await server.serve_forever()


def main() -> int:
    http = HTTPServer(("127.0.0.1", HTTP_PORT), _ReadApi)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    print(f"mailcatcher: SMTP on :{SMTP_PORT}, read API on :{HTTP_PORT}", flush=True)
    try:
        asyncio.run(_serve_smtp())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
