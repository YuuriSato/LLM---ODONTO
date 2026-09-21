from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
from pydantic import ValidationError

from app.ai.audit import audit_analysis
from app.ai.config import AISettings, get_settings
from app.ai.evidence import collect_evidence, fft_metrics
from app.ai.gemini_client import Generation, ProviderError
from app.ai.gemini_integrity_analyzer import AnalysisValidationError, GeminiIntegrityAnalyzer
from app.ai.pipeline import run_integrity_pipeline
from app.ai.schemas import EvidenceRecord, ForensicAnalysis, IntegrityAnalysis, LocalEvidence, validate_references


def sample_evidence():
    families = {"ela": "compressao", "fft": "frequencia", "ruido": "textura", "ruido_blocos": "textura",
                "nitidez": "textura", "compressao": "compressao", "metadata": "metadata", "detector_ia": "detector", "comparacao": "comparacao"}
    records = [EvidenceRecord(id=key, family=family, status="disponivel", method="synthetic test",
                              values={"measurement": 1.0}, signal="sem_anomalia") for key, family in families.items()]
    for record in records:
        if record.id in {"detector_ia", "comparacao"}:
            record.status = "desativado" if record.id == "detector_ia" else "ausente"
            record.signal = "desconhecido"
            record.values = {}
    return LocalEvidence(schema_version="2.0", analysis_id="test", image_sha256="hash", reference_sha256=None,
                         quality="boa", records=records, observations=["Synthetic evidence"], limitations=[])


def sample_analysis(evidence=None, verdict="REAL"):
    evidence = evidence or sample_evidence()
    sections = {}
    for name in ForensicAnalysis.model_fields:
        record = next(r for r in evidence.records if r.id == name)
        sections[name] = {"status": record.status, "interpretacao": "Descricao qualitativa",
                          "referencias": [{"evidence_id": name, "metric": "measurement", "value": 1.0}] if record.status == "disponivel" else []}
    raw = {
        "veredito": verdict, "confidence": 0.91, "modalidade": "INTRAORAL", "justificativa": "Justificativa especifica.",
        "analise_visual": {key: [] for key in ("anatomia_dental", "texturas", "bordas", "iluminacao", "artefatos_suspeitos")},
        "analise_forense": sections,
        "evidencias_favoraveis": [
            {"descricao": "Observacao visual", "fonte": "visual", "referencias": []},
            {"descricao": "Medicoes locais", "fonte": "computacional", "referencias": [
                {"evidence_id": "ela", "metric": "measurement", "value": 1.0},
                {"evidence_id": "ruido", "metric": "measurement", "value": 1.0}]},
        ], "evidencias_contrarias": [], "limitacoes": [], "requer_auditoria": False,
    }
    return IntegrityAnalysis.model_validate_json(json.dumps(raw))


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.image = self.folder / "sample.png"
        Image.new("RGB", (64, 64), "white").save(self.image)

    def test_schema_rejects_invalid_output(self):
        base = sample_analysis().model_dump(mode="json")
        invalid = []
        for key, value in [("confidence", -1), ("confidence", 2), ("confidence", float("nan")), ("confidence", "0.9"), ("veredito", "MODIFICADO"), ("modalidade", "INVALIDA")]:
            data = copy.deepcopy(base)
            data[key] = value
            invalid.append(data)
        missing = copy.deepcopy(base)
        del missing["analise_forense"]
        invalid.append(missing)
        invalid.append({**base, "unexpected": True})
        for data in invalid:
            with self.subTest(data=data.get("confidence")), self.assertRaises(ValidationError):
                IntegrityAnalysis.model_validate_json(json.dumps(data))

    def test_invalid_references_values_and_states_rejected(self):
        for change in ({"value": 99.0}, {"value": True}, {"metric": "inventada"}, {"evidence_id": "inexistente"}):
            data = sample_analysis().model_dump(mode="json")
            data["analise_forense"]["ela"]["referencias"][0].update(change)
            analysis = IntegrityAnalysis.model_validate_json(json.dumps(data))
            with self.assertRaises(ValueError):
                validate_references(analysis, sample_evidence())
        analysis = sample_analysis()
        analysis.analise_forense.detector_ia.status = "disponivel"
        with self.assertRaises(ValueError):
            validate_references(analysis, sample_evidence())

    def test_audit_accepts_supported_result_with_detector_disabled(self):
        result = audit_analysis(sample_analysis(), sample_evidence())
        self.assertEqual(result["verdict"], "REAL")
        self.assertFalse(result["requires_review"])
        self.assertEqual(result["confidence"], 0.91)

    def test_numeric_computational_claims_must_use_validated_references(self):
        analysis = sample_analysis()
        analysis.analise_forense.ela.interpretacao = "ELA de 999 comprova edicao."
        with self.assertRaises(ValueError):
            validate_references(analysis, sample_evidence())

    def test_completed_review_cannot_erase_persistent_conflict(self):
        evidence = sample_evidence()
        analyzer = Mock(calls=[])
        analyzer.analyze_integrity.return_value = sample_analysis(evidence, "IA_EDITADA")
        analyzer.review.return_value = sample_analysis(evidence, "IA_EDITADA")
        with patch("app.ai.pipeline.collect_evidence", return_value=evidence):
            result = run_integrity_pipeline(self.image, settings=AISettings(api_key="test"), cache_dir=self.folder / "cache", analyzer=analyzer)
        analyzer.review.assert_called_once()
        self.assertEqual(result["status"], "concluida")
        self.assertEqual(result["verdict"], "INDETERMINADO")
        self.assertIsNone(result["confidence"])
        self.assertEqual(result["initial_analysis"]["confidence"], 0.91)
        self.assertIsNotNone(result["reviewed_analysis"])

    def test_ai_with_weak_forensics_and_low_detector_is_indeterminate(self):
        evidence = sample_evidence()
        detector = next(r for r in evidence.records if r.id == "detector_ia")
        detector.status, detector.signal, detector.values = "disponivel", "sem_anomalia", {"measurement": 1.0}
        analysis = sample_analysis(evidence, "IA_EDITADA")
        result = audit_analysis(analysis, evidence)
        self.assertEqual(result["verdict"], "INDETERMINADO")
        self.assertIsNone(result["confidence"])
        self.assertTrue(result["requires_review"])
        self.assertEqual(audit_analysis(analysis, evidence, reviewed=True)["verdict"], "INDETERMINADO")

    def test_real_with_multiple_anomalies_and_high_detector(self):
        evidence = sample_evidence()
        for record in evidence.records:
            if record.id in {"ela", "ruido", "detector_ia"}:
                record.status, record.signal, record.values = "disponivel", "anomalia", {"measurement": 1.0}
        result = audit_analysis(sample_analysis(evidence), evidence)
        self.assertEqual(result["verdict"], "INDETERMINADO")
        self.assertTrue(result["suspeita_ia"])

    def test_correlated_signals_are_not_independent_support(self):
        evidence = sample_evidence()
        for record in evidence.records:
            if record.family == "textura":
                record.signal = "anomalia"
        analysis = sample_analysis(evidence, "EDICAO_TRADICIONAL")
        analysis.evidencias_favoraveis[1].referencias[0].evidence_id = "nitidez"
        audit = audit_analysis(analysis, evidence)
        self.assertEqual(audit["support_families"], ["textura"])
        self.assertEqual(audit["verdict"], "INDETERMINADO")

    def test_quality_constraint_cannot_be_overridden(self):
        evidence = sample_evidence()
        evidence.quality = "insuficiente"
        for reviewed in (False, True):
            result = audit_analysis(sample_analysis(evidence), evidence, reviewed=reviewed)
            self.assertEqual(result["verdict"], "INDETERMINADO")

    def test_one_repair_only_and_validation_not_regex(self):
        client = Mock()
        invalid = Generation("```json\n{}\n```", "model", None, "STOP", [])
        client.generate.return_value = invalid
        analyzer = GeminiIntegrityAnalyzer(client)
        with self.assertRaises(AnalysisValidationError):
            analyzer.analyze_integrity(self.image, sample_evidence())
        self.assertEqual(client.generate.call_count, 2)
        client.generate.reset_mock()
        client.generate.side_effect = [invalid, Generation(sample_analysis().model_dump_json(), "model", None, "STOP", [])]
        result = GeminiIntegrityAnalyzer(client).analyze_integrity(self.image, sample_evidence())
        self.assertEqual(result.veredito.value, "REAL")

    def test_metrics_png_jpeg_noise_blocks_and_fft_constant(self):
        for extension in ("png", "jpg"):
            path = self.image.with_suffix("." + extension)
            Image.new("RGB", (64, 64), "white").save(path)
            evidence = collect_evidence(path, "test")
            records = {r.id: r for r in evidence.records}
            self.assertFalse(records["metadata"].values["exif_present"])
            self.assertEqual(records["detector_ia"].status, "desativado")
            self.assertIsNone(records["detector_ia"].values["score"])
            self.assertEqual(records["comparacao"].status, "ausente")
            self.assertTrue(records["ruido_blocos"].values["blocks"])
            self.assertEqual(records["compressao"].values["jpeg_status"], "disponivel" if extension == "jpg" else "nao_aplicavel")
            self.assertIsNone(records["fft"].values["radial_energy_fraction"])

    def test_fft_distinguishes_synthetic_frequencies(self):
        low = np.tile((127 + 100 * np.sin(np.arange(128) * 2 * np.pi / 32)).astype("uint8"), (128, 1))
        high = np.tile((127 + 100 * np.sin(np.arange(128) * 2 * np.pi / 4)).astype("uint8"), (128, 1))
        Image.fromarray(low).save(self.image)
        low_result = fft_metrics(self.image)
        Image.fromarray(high).save(self.image)
        high_result = fft_metrics(self.image)
        self.assertGreater(low_result["low_energy_fraction"], high_result["low_energy_fraction"])
        self.assertAlmostEqual(sum(high_result["radial_energy_fraction"]), 1.0)

    def test_failed_extraction_is_not_zero(self):
        with patch("app.ai.evidence.local.ela_metrics", side_effect=ValueError("bad")):
            result = collect_evidence(self.image, "test", self.image)
        ela = next(r for r in result.records if r.id == "ela")
        self.assertEqual(ela.status, "falhou")
        self.assertEqual(ela.values, {})
        self.assertEqual(next(r for r in result.records if r.id == "comparacao").status, "disponivel")

    def test_production_calls_model_despite_calibration_and_preserves_evidence_before_call(self):
        client = Mock()
        def fail(*args, **kwargs):
            saved = list((self.folder / "cache").glob("*/local_evidence.json"))
            self.assertEqual(len(saved), 1)
            data = json.loads(saved[0].read_text(encoding="utf-8"))
            self.assertGreater(len(data["records"]), 5)
            raise ProviderError("404", "model_unavailable")
        client.generate.side_effect = fail
        from app.local_forensics import file_sha256
        result = run_integrity_pipeline(self.image, settings=AISettings(api_key="test"), cache_dir=self.folder / "cache",
                                        calibration={file_sha256(self.image): {"label": "REAL", "score": 0}}, analyzer=GeminiIntegrityAnalyzer(client))
        client.generate.assert_called_once()
        self.assertEqual(result["status"], "nao_concluida")
        self.assertIsNone(result["verdict"])
        self.assertTrue((self.folder / "cache" / result["analysis_id"] / "result.json").exists())

    def test_concurrent_requests_have_separate_artifacts(self):
        def run(_):
            client = Mock()
            client.generate.side_effect = ProviderError("offline")
            return run_integrity_pipeline(self.image, settings=AISettings(api_key="test"), cache_dir=self.folder / "cache", analyzer=GeminiIntegrityAnalyzer(client))
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(run, range(3)))
        self.assertEqual(len({r["analysis_id"] for r in results}), 3)
        self.assertEqual(len(list((self.folder / "cache").glob("*/local_evidence.json"))), 3)

    def test_review_failure_is_not_a_final_verdict(self):
        evidence = sample_evidence()
        initial = sample_analysis(evidence, "IA_GERADA")
        analyzer = Mock(calls=[])
        analyzer.analyze_integrity.return_value = initial
        analyzer.review.side_effect = ProviderError("offline")
        with patch("app.ai.pipeline.collect_evidence", return_value=evidence):
            result = run_integrity_pipeline(self.image, settings=AISettings(api_key="test"), cache_dir=self.folder / "cache", analyzer=analyzer)
        self.assertEqual(result["status"], "nao_concluida")
        self.assertIsNone(result["verdict"])
        self.assertEqual(result["initial_analysis"]["veredito"], "IA_GERADA")
        self.assertEqual(result["review_status"], "falhou")

    def test_supported_pipeline_always_runs_backend_audit(self):
        evidence = sample_evidence()
        analyzer = Mock(calls=[])
        analyzer.analyze_integrity.return_value = sample_analysis(evidence)
        with patch("app.ai.pipeline.collect_evidence", return_value=evidence):
            result = run_integrity_pipeline(self.image, settings=AISettings(api_key="test"), cache_dir=self.folder / "cache", analyzer=analyzer)
        self.assertEqual(result["status"], "concluida")
        self.assertEqual(result["audit_status"], "executada")
        analyzer.review.assert_not_called()

    def test_environment_precedence_and_production_model_lock(self):
        with patch("app.ai.config.load_project_env"), patch.dict("os.environ", {"AI_PROVIDER": "gemini", "LLM_PROVIDER": "ollama"}, clear=True):
            self.assertEqual(get_settings().provider, "gemini")
        with patch("app.ai.config.load_project_env"), patch.dict("os.environ", {"LLM_PROVIDER": "ollama"}, clear=True):
            self.assertEqual(get_settings().provider, "ollama")
        with self.assertRaises(ValueError):
            AISettings(api_key="test", model="gemini-flash-latest").validate_production()


if __name__ == "__main__":
    unittest.main()
