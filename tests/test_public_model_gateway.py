"""Security boundaries for the local OpenAI-compatible model gateway."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from scripts.public_model_gateway import MODEL, make_handler


class PublicModelGatewayTests(unittest.TestCase):
    def setUp(self):
        self.key = "sk-test-" + "x" * 50
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.key, "http://127.0.0.1:1234"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, payload=None, authorized=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + self.key
        connection.request(method, path, body=None if payload is None else json.dumps(payload), headers=headers)
        response = connection.getresponse()
        status, body = response.status, json.loads(response.read())
        connection.close()
        return status, body

    def test_authentication_and_model_listing(self):
        self.assertEqual(self.request("GET", "/v1/models", authorized=False)[0], 401)
        status, body = self.request("GET", "/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual([entry["id"] for entry in body["data"]], [MODEL])

    def test_blocks_other_models_and_management_endpoints(self):
        self.assertEqual(self.request("GET", "/api/v1/models")[0], 404)
        self.assertEqual(self.request("POST", "/v1/chat/completions", {
            "model": "other", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8,
        })[0], 400)

    def test_rejects_streaming_on_temporary_tunnel(self):
        with patch("scripts.public_model_gateway.urlopen") as upstream:
            status, body = self.request("POST", "/v1/chat/completions", {
                "model": MODEL, "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 8, "stream": True,
            })
        self.assertEqual(status, 400)
        self.assertIn("streaming", body["error"]["message"])
        upstream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
