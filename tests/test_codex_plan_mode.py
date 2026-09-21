import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts import codex_plan_mode as plan


SUMMARY = "VEREDITO_PLAN: INDETERMINADO | CONFIANCA: 0.75 | RECOMENDACAO: AUDITAR_HUMANO"
REPORT = "As evidencias fornecidas sao insuficientes para concluir a integridade.\n\n" + SUMMARY


class PlanModeTests(unittest.TestCase):
    def test_host_with_and_without_scheme(self):
        for host in ("127.0.0.1:11435", "http://127.0.0.1:11435/"):
            with self.subTest(host=host):
                self.assertEqual(plan.ollama_chat_url(host), "http://127.0.0.1:11435/api/chat")
        self.assertEqual(plan.ollama_chat_url("https://example.com/"), "https://example.com/api/chat")

    def test_summary_rejects_invalid_enums_labels_and_confidence(self):
        for line in (
            SUMMARY.replace("INDETERMINADO", "DESCONHECIDO"),
            SUMMARY.replace("AUDITAR_HUMANO", "IGNORAR"),
            SUMMARY.replace("CONFIANCA", "SCORE"),
            *(SUMMARY.replace("0.75", value) for value in ("nan", "inf", "1.01", "-0.10", "0.5")),
        ):
            with self.subTest(line=line):
                self.assertIsNone(plan.parse_plan_summary(line))
        self.assertEqual(plan.parse_plan_summary(SUMMARY)["confianca"], 0.75)

    def test_summary_must_be_last_nonempty_line(self):
        self.assertIsNotNone(plan.extract_plan_summary(REPORT + "\n\n"))
        self.assertIsNone(plan.extract_plan_summary(REPORT + "\nTexto contraditorio."))
        self.assertIsNone(plan.extract_plan_summary(""))

    def test_chat_payload_and_response(self):
        response = io.BytesIO(json.dumps({"message": {"content": REPORT}}).encode())
        with patch.object(plan, "urlopen", return_value=response) as mocked:
            self.assertEqual(plan.call_ollama_chat("sistema", "evidencias", "modelo-teste"), REPORT)
        request = mocked.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "modelo-teste")
        self.assertFalse(payload["stream"])
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])
        self.assertEqual(mocked.call_args.kwargs["timeout"], 60)

    def test_empty_or_malformed_chat_response_is_rejected(self):
        for data in ({}, [], {"message": None}, {"message": {"content": " "}}):
            with self.subTest(data=data):
                with patch.object(plan, "urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
                    with self.assertRaises(ValueError):
                        plan.call_ollama_chat("sistema", "evidencias")

    def run_cli(self, folder, evidence, response=REPORT, failure=None):
        source = folder / "evidence.json"
        source.write_text(json.dumps(evidence), encoding="utf-8-sig")
        target = folder / "reports" / "parecer.txt"
        structured = target.with_suffix(".json")
        with patch.object(plan, "call_ollama_chat", return_value=response, side_effect=failure) as mocked:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = plan.main([
                    "--input-json", str(source), "--output-txt", str(target),
                    "--output-json", str(structured), "--model", "modelo-teste",
                ])
        return status, target, structured, mocked

    def test_cli_creates_reports_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            status, target, structured, mocked = self.run_cli(Path(directory), {"quality": "insuficiente"})
            self.assertEqual(status, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), REPORT)
            result = json.loads(structured.read_text(encoding="utf-8"))
            self.assertEqual(result["resumo_extraido"]["veredito"], "INDETERMINADO")
            self.assertIn('"quality": "insuficiente"', mocked.call_args.args[1])
            self.assertEqual(mocked.call_args.args[2], "modelo-teste")

    def test_invalid_summary_preserves_raw_text_with_null_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            status, target, structured, _ = self.run_cli(Path(directory), {"score": 42}, response="Sem resumo.")
            self.assertEqual(status, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "Sem resumo.")
            self.assertIsNone(json.loads(structured.read_text())["resumo_extraido"])

    def test_invalid_input_does_not_call_model(self):
        for evidence in ([], {}, "texto"):
            with self.subTest(evidence=evidence), tempfile.TemporaryDirectory() as directory:
                status, target, _, mocked = self.run_cli(Path(directory), evidence)
                self.assertEqual(status, 1)
                mocked.assert_not_called()
                self.assertFalse(target.exists())

    def test_connection_failure_does_not_create_report(self):
        with tempfile.TemporaryDirectory() as directory:
            status, target, _, _ = self.run_cli(Path(directory), {"score": 42}, failure=URLError("offline"))
            self.assertEqual(status, 1)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
