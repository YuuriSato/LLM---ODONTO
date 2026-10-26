"""Local chat page that exercises the remote dental API without exposing its key."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


MODEL = "medgemma-dental-lora-1.5"
PAGE = Path(__file__).resolve().parent.parent / "chat_test" / "index.html"


def make_handler(base_url: str, api_key: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DentalChatTest/1"

        def log_message(self, *_args):
            # Prompts and the API key must not appear in local logs.
            pass

        def json_response(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def remote(self, path: str, payload: dict | None = None) -> dict:
            headers = {"Authorization": "Bearer " + api_key}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            request = Request(
                base_url + path,
                data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="GET" if payload is None else "POST",
            )
            with urlopen(request, timeout=180) as response:
                return json.load(response)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                page = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
            elif self.path == "/status":
                try:
                    models = self.remote("/models")
                    available = MODEL in {entry.get("id") for entry in models.get("data", [])}
                    self.json_response(200 if available else 503, {"connected": available, "model": MODEL})
                except (HTTPError, URLError, TimeoutError, ValueError):
                    self.json_response(503, {"connected": False, "model": MODEL})
            else:
                self.json_response(404, {"error": "Página não encontrada"})

        def do_POST(self) -> None:
            if self.path != "/chat":
                self.json_response(404, {"error": "Endpoint não disponível"})
                return
            if "application/json" not in self.headers.get("Content-Type", "").lower():
                self.json_response(415, {"error": "Envie JSON"})
                return
            origin = self.headers.get("Origin")
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if origin and origin != expected_origin:
                self.json_response(403, {"error": "Origem não permitida"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = 0
            if not 0 < length <= 12_000:
                self.json_response(413, {"error": "Mensagem acima do limite"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self.json_response(400, {"error": "JSON inválido"})
                return
            messages = payload.get("messages") if isinstance(payload, dict) else None
            if not isinstance(messages, list) or not 1 <= len(messages) <= 12:
                self.json_response(400, {"error": "Histórico inválido"})
                return
            if any(not isinstance(item, dict) or item.get("role") not in ("user", "assistant")
                   or not isinstance(item.get("content"), str) or not item["content"].strip()
                   or len(item["content"]) > 2000 for item in messages) or messages[-1]["role"] != "user":
                self.json_response(400, {"error": "Mensagem inválida"})
                return
            if sum(len(item["content"]) for item in messages) > 8000:
                self.json_response(400, {"error": "Conversa acima do limite"})
                return
            try:
                result = self.remote("/chat/completions", {
                    "model": MODEL, "messages": messages, "temperature": 0.2,
                    "max_tokens": 256, "stream": False,
                })
                content = result["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Empty response")
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError):
                self.json_response(502, {"error": "A API remota não respondeu. Confira se o túnel e o modelo continuam ligados."})
                return
            self.json_response(200, {"content": content, "model": MODEL})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="URL HTTPS do Quick Tunnel terminada em /v1")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path != "/v1" or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("Use uma Base URL HTTPS terminada em /v1")
    api_key = args.key_file.read_text(encoding="utf-8").strip()
    if len(api_key) < 40:
        raise ValueError("Chave de API inválida")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.base_url, api_key))
    print(f"Chat de teste em http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
