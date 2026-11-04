import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.ai.audit import audit_analysis
from app.ai.config import AISettings
from app.ai.pipeline import run_integrity_pipeline
from app.ai.schemas import VisualIntake
from app.ai.integrity_analyzer import IntegrityAnalyzer
from app.ai.gemini_client import Generation, ProviderError
from tests.test_integrity_pipeline import sample_analysis, sample_evidence


class ConsistencyTests(unittest.TestCase):
    def test_absence_of_anomalies_does_not_establish_authenticity(self):
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.justificativa = 'A ausência de anomalias significativas sugere que a imagem é original e não foi gerada por IA.'
        audit = audit_analysis(analysis, sample_evidence())
        self.assertTrue(audit['requires_review'])
        self.assertIn('unsupported_authenticity_inference', [item['code'] for item in audit['consistency_conflicts']])

    def test_explicit_denial_of_authenticity_inference_is_allowed(self):
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.justificativa = 'A ausência de anomalias não comprova autenticidade.'
        self.assertEqual(audit_analysis(analysis, sample_evidence())['consistency_conflicts'], [])

    def test_missing_exif_does_not_establish_traditional_processing(self):
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.justificativa = 'A ausência de informações EXIF e a qualidade geral da imagem sugerem um processo tradicional.'
        self.assertTrue(audit_analysis(analysis, sample_evidence())['requires_review'])

    def test_missing_exif_can_remain_a_limitation(self):
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.justificativa = 'A ausência de EXIF não indica edição tradicional. A origem permanece indeterminada.'
        self.assertEqual(audit_analysis(analysis, sample_evidence())['consistency_conflicts'], [])

    def test_intake_repairs_description_once_and_records_both_attempts(self):
        client = Mock(settings=AISettings(provider='lmstudio', development=True))
        def response(description):
            return Generation(VisualIntake(modalidade='INTRAORAL', paineis=2,
                              descricao=description).model_dump_json(), 'test', 'test', 'stop', [])
        client.generate.side_effect = [response('Uma radiografia intraoral.'), response('Duas fotografias coloridas.')]
        analyzer = IntegrityAnalyzer(client)
        analyzer._identify_image(Path('unused.png'))
        self.assertEqual(client.generate.call_count, 2)
        self.assertEqual([call['validated'] for call in analyzer.calls], [False, True])
        self.assertEqual(analyzer.visual_intake.modalidade, 'INTRAORAL')

    def test_intake_persistent_conflict_stops_after_two_attempts(self):
        client = Mock(settings=AISettings(provider='lmstudio', development=True))
        client.generate.return_value = Generation(
            VisualIntake(modalidade='INTRAORAL', paineis=1, descricao='Uma radiografia.').model_dump_json(),
            'test', 'test', 'stop', [])
        analyzer = IntegrityAnalyzer(client)
        with self.assertRaises(ProviderError) as raised:
            analyzer._identify_image(Path('unused.png'))
        self.assertEqual(raised.exception.code, 'inconsistent_model_output')
        self.assertEqual(client.generate.call_count, 2)
        self.assertIsNone(analyzer.visual_intake)

    def test_photograph_enum_cannot_hide_radiograph_description(self):
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.justificativa = 'A imagem mostra uma radiografia intraoral.'
        self.assertEqual(audit_analysis(analysis, sample_evidence())['consistency_conflicts'][0]['code'],
                         'modality_text_disagreement')

    def test_denial_of_radiograph_is_not_a_modality_contradiction(self):
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.justificativa = 'Não é uma radiografia. Mostra uma fotografia intraoral.'
        self.assertEqual(audit_analysis(analysis, sample_evidence())['consistency_conflicts'], [])

    def test_modality_conflict_requires_review(self):
        intake = VisualIntake(modalidade='INTRAORAL', paineis=2, descricao='Duas fotografias coloridas.')
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.modalidade = 'RADIOGRAFIA'
        audit = audit_analysis(analysis, sample_evidence(), visual_intake=intake)
        self.assertTrue(audit['requires_review'])
        self.assertEqual(audit['consistency_conflicts'][0]['code'], 'modality_disagreement')

    def test_unknown_intake_does_not_force_a_modality(self):
        intake = VisualIntake(modalidade='OUTRA', paineis=1, descricao='Modalidade incerta.')
        audit = audit_analysis(sample_analysis(), sample_evidence(), visual_intake=intake)
        self.assertEqual(audit['consistency_conflicts'], [])

    def test_review_cannot_hide_bad_resolution_claim_in_inconclusive_text(self):
        evidence = sample_evidence()
        initial = sample_analysis(evidence, 'INDETERMINADO')
        initial.justificativa = 'A baixa resolução impede a avaliação.'
        reviewed = copy.deepcopy(initial)
        analyzer = Mock(calls=[])
        analyzer.analyze_integrity.return_value = initial
        analyzer.review.return_value = reviewed
        with tempfile.TemporaryDirectory() as folder, patch('app.ai.pipeline.collect_evidence', return_value=evidence):
            result = run_integrity_pipeline(Path('unused.png'), settings=AISettings(api_key='test'),
                                            cache_dir=Path(folder), analyzer=analyzer)
        self.assertEqual(result['status'], 'nao_concluida')
        self.assertEqual(result['error_code'], 'inconsistent_model_output')
        self.assertIsNone(result['verdict'])
        self.assertEqual(result['audit']['status'], 'conflito')
        self.assertEqual(result['reviewed_analysis']['justificativa'], initial.justificativa)

    def test_correction_can_remain_legitimately_inconclusive(self):
        evidence = sample_evidence()
        initial = sample_analysis(evidence, 'INDETERMINADO')
        initial.justificativa = 'A resolução insuficiente impede avaliar.'
        reviewed = sample_analysis(evidence, 'INDETERMINADO')
        reviewed.justificativa = 'Não há baixa resolução. A origem não foi estabelecida pelas evidências.'
        analyzer = Mock(calls=[])
        analyzer.analyze_integrity.return_value = initial
        analyzer.review.return_value = reviewed
        with tempfile.TemporaryDirectory() as folder, patch('app.ai.pipeline.collect_evidence', return_value=evidence):
            result = run_integrity_pipeline(Path('unused.png'), settings=AISettings(api_key='test'),
                                            cache_dir=Path(folder), analyzer=analyzer)
        self.assertEqual(result['status'], 'concluida')
        self.assertEqual(result['verdict'], 'INDETERMINADO')
        self.assertEqual(result['audit']['status'], 'validada')

    def test_structured_issue_is_checked_even_without_trigger_words(self):
        evidence = sample_evidence()
        issue = [{'tipo': 'resolucao_insuficiente', 'descricao': 'Os detalhes não permitem avaliar.',
                  'fonte': 'computacional', 'referencias': [
                      {'evidence_id': 'dimensoes', 'metric': 'image_min_side', 'value': 640}]}]
        analysis = sample_analysis(evidence, 'INDETERMINADO', 'impossivel_avaliar', issue)
        self.assertEqual(audit_analysis(analysis, evidence)['consistency_conflicts'][0]['code'],
                         'unsupported_resolucao_insuficiente')

    def test_low_resolution_does_not_justify_claim_of_extreme_blur(self):
        evidence = sample_evidence()
        evidence.quality = 'insuficiente'
        sharpness = next(record for record in evidence.records if record.id == 'nitidez')
        sharpness.values['laplacian_var'] = 183.0
        analysis = sample_analysis(evidence, 'INDETERMINADO')
        analysis.justificativa = 'O desfoque extremo impede avaliar.'
        self.assertEqual(audit_analysis(analysis, evidence)['consistency_conflicts'][0]['code'],
                         'unsupported_desfoque_extremo')

    def test_measured_low_resolution_is_not_a_model_contradiction(self):
        evidence = sample_evidence()
        evidence.quality = 'insuficiente'
        next(record for record in evidence.records if record.id == 'dimensoes').values['image_min_side'] = 224
        analysis = sample_analysis(evidence, 'INDETERMINADO')
        analysis.justificativa = 'A baixa resolução limita detalhes.'
        self.assertEqual(audit_analysis(analysis, evidence)['consistency_conflicts'], [])

    def test_negative_claim_does_not_hide_following_positive_claim(self):
        analysis = sample_analysis(verdict='INDETERMINADO')
        analysis.justificativa = 'Não há ruído, mas há baixa resolução.'
        self.assertTrue(audit_analysis(analysis, sample_evidence())['consistency_conflicts'])

    def test_regional_obstruction_with_good_global_quality_remains_possible(self):
        issue = [{'tipo': 'regiao_interesse_encoberta', 'descricao': 'Instrumento cobre a região de interesse.',
                  'fonte': 'visual', 'referencias': []}]
        analysis = sample_analysis(None, 'INDETERMINADO', 'impossivel_avaliar', issue)
        self.assertEqual(audit_analysis(analysis, sample_evidence(), reviewed=True)['conclusion_type'],
                         'impossivel_avaliar')
