"""Local chat page that exercises the remote dental API without exposing its key."""
from __future__ import annotations

import argparse
import base64
import binascii
from io import BytesIO
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError


MODEL = "medgemma-dental-lora-1.5"
PAGE = Path(__file__).resolve().parent.parent / "chat_test" / "index.html"
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_DATA_URL = re.compile(r"\Adata:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]+={0,2})\Z")


def validate_messages(messages: object) -> list[dict]:
    if not isinstance(messages, list) or not 1 <= len(messages) <= 12:
        raise ValueError("Histórico inválido")
    if not isinstance(messages[-1], dict) or messages[-1].get("role") != "user":
        raise ValueError("A última mensagem deve ser sua")
    text_total = 0
    image_count = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            raise ValueError("Mensagem inválida")
        content = message.get("content")
        if isinstance(content, str):
            if not content.strip() or len(content) > 2000:
                raise ValueError("Texto inválido")
            text_total += len(content)
            continue
        if message["role"] != "user" or not isinstance(content, list) or len(content) != 2:
            raise ValueError("Conteúdo inválido")
        text_part, image_part = content
        if (not isinstance(text_part, dict) or text_part.get("type") != "text"
                or not isinstance(text_part.get("text"), str) or not text_part["text"].strip()
                or len(text_part["text"]) > 2000
                or not isinstance(image_part, dict) or image_part.get("type") != "image_url"
                or not isinstance(image_part.get("image_url"), dict)
                or not isinstance(image_part["image_url"].get("url"), str)):
            raise ValueError("Imagem ou texto inválido")
        text_total += len(text_part["text"])
        image_count += 1
        if image_count > 1:
            raise ValueError("Use uma imagem por conversa")
        match = IMAGE_DATA_URL.fullmatch(image_part["image_url"]["url"])
        if not match or len(match[2]) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 4:
            raise ValueError("Imagem inválida ou acima de 5 MB")
        try:
            raw = base64.b64decode(match[2], validate=True)
            if len(raw) > MAX_IMAGE_BYTES:
                raise ValueError("Imagem acima de 5 MB")
            with Image.open(BytesIO(raw)) as image:
                if image.format != {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[match[1]]:
                    raise ValueError("Formato da imagem não corresponde ao arquivo")
                if image.width * image.height > 20_000_000:
                    raise ValueError("Imagem com dimensões excessivas")
                image.verify()
            if match[1] == "image/webp":
                with Image.open(BytesIO(raw)) as image:
                    converted = BytesIO()
                    image.convert("RGB").save(converted, format="PNG")
                if converted.tell() > MAX_IMAGE_BYTES:
                    raise ValueError("Imagem convertida acima de 5 MB")
                image_part["image_url"]["url"] = "data:image/png;base64," + base64.b64encode(converted.getvalue()).decode("ascii")
        except (binascii.Error, UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
            raise ValueError("Arquivo de imagem inválido") from error
    if text_total > 8000:
        raise ValueError("Conversa acima do limite")
    return messages


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
            headers = {"Authorization": "Bearer " + api_key, "User-Agent": "LM-Odonto-Chat-Test/1.0"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            request = Request(
                base_url + path,
                data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="GET" if payload is None else "POST",
            )
            with urlopen(request, timeout=260) as response:
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
            if not 0 < length <= MAX_BODY_BYTES:
                self.json_response(413, {"error": "Mensagem acima do limite"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self.json_response(400, {"error": "JSON inválido"})
                return
            try:
                messages = validate_messages(payload.get("messages") if isinstance(payload, dict) else None)
            except ValueError as error:
                self.json_response(400, {"error": str(error)})
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
