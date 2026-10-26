"""Token-protected, OpenAI-compatible gateway for the local dental GGUF.

Bind only to loopback. A tunnel may point at this gateway, never at LM Studio.
The sole exposed model is experimental and its predictions are not validated.
"""
from __future__ import annotations

import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL = "medgemma-dental-lora-1.5"
MAX_BODY_BYTES = 16 * 1024 * 1024
MAX_COMPLETION_TOKENS = 1024


def make_handler(secret: str, upstream: str):
    semaphore = BoundedSemaphore(1)

    class Handler(BaseHTTPRequestHandler):
        server_version = "DentalModelGateway/1"

        def log_message(self, format_string, *args):
            # Do not log image bodies, prompts or bearer tokens.
            pass

        def respond(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self) -> bool:
            value = self.headers.get("Authorization", "")
            return hmac.compare_digest(value, "Bearer " + secret)

        def do_GET(self) -> None:
            if not self.authorized():
                self.respond(401, {"error": {"message": "API key obrigatória", "type": "authentication_error"}})
            elif self.path == "/v1/models":
                self.respond(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "local"}]})
            else:
                self.respond(404, {"error": {"message": "Endpoint não disponível", "type": "invalid_request_error"}})

        def do_POST(self) -> None:
            if not self.authorized():
                self.respond(401, {"error": {"message": "API key obrigatória", "type": "authentication_error"}})
                return
            if self.path != "/v1/chat/completions":
                self.respond(404, {"error": {"message": "Endpoint não disponível", "type": "invalid_request_error"}})
                return
            if "application/json" not in self.headers.get("Content-Type", "").lower():
                self.respond(415, {"error": {"message": "Envie application/json", "type": "invalid_request_error"}})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = 0
            if not 0 < length <= MAX_BODY_BYTES:
                self.respond(413, {"error": {"message": "Corpo ausente ou acima do limite", "type": "invalid_request_error"}})
                return
            try:
                data = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self.respond(400, {"error": {"message": "JSON inválido", "type": "invalid_request_error"}})
                return
            if not isinstance(data, dict) or data.get("model") != MODEL or not isinstance(data.get("messages"), list):
                self.respond(400, {"error": {"message": "Modelo ou mensagens inválidos", "type": "invalid_request_error"}})
                return
            if data.get("stream") is True:
                self.respond(400, {"error": {"message": "Esta URL temporária não suporta streaming", "type": "invalid_request_error"}})
                return
            requested = data.get("max_tokens", MAX_COMPLETION_TOKENS)
            if not isinstance(requested, int) or isinstance(requested, bool) or not 1 <= requested <= MAX_COMPLETION_TOKENS:
                self.respond(400, {"error": {"message": "max_tokens fora do limite", "type": "invalid_request_error"}})
                return
            if not semaphore.acquire(blocking=False):
                self.respond(429, {"error": {"message": "Modelo ocupado; tente novamente", "type": "rate_limit_error"}})
                return
            try:
                data["stream"] = False
                request = Request(
                    upstream.rstrip("/") + "/v1/chat/completions",
                    data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=240) as response:
                        answer = response.read(8 * 1024 * 1024 + 1)
                        status = response.status
                except HTTPError as error:
                    answer = error.read(8 * 1024 * 1024 + 1)
                    status = error.code
                if len(answer) > 8 * 1024 * 1024:
                    self.respond(502, {"error": {"message": "Resposta acima do limite", "type": "upstream_error"}})
                    return
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)
            except (URLError, TimeoutError):
                self.respond(502, {"error": {"message": "LM Studio indisponível", "type": "upstream_error"}})
            finally:
                semaphore.release()

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--upstream", default="http://127.0.0.1:1234")
    args = parser.parse_args()
    if not args.upstream.startswith("http://127.0.0.1:"):
        raise ValueError("O upstream deve permanecer em 127.0.0.1")
    secret = args.key_file.read_text(encoding="utf-8").strip()
    if len(secret) < 40:
        raise ValueError("A chave deve ter no mínimo 40 caracteres")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(secret, args.upstream))
    print(f"Gateway local em http://127.0.0.1:{args.port}; modelo {MODEL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
