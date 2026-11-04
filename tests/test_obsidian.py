import json
from pathlib import Path
import tempfile
import unittest

from scripts.export_obsidian import export


class ObsidianExportTests(unittest.TestCase):
    def test_exports_aggregates_without_image_names_responses_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'runtime/analysis_cache/example'
            cache.mkdir(parents=True)
            (root / '.env').write_text('GEMINI_API_KEY=SECRET', encoding='utf-8')
            (cache / 'result.json').write_text(json.dumps({'status': 'concluida', 'model': 'fixture',
                'filename': 'PRIVATE_NAME.png', 'report': 'PRIVATE_REPORT', 'conclusion_type': 'inconclusiva'}), encoding='utf-8')
            vault = root / 'vault'
            result = export(vault, root)
            text = (vault / 'Gerado/Estado do projeto.md').read_text(encoding='utf-8')
            self.assertEqual(len(result['saved']), 1)
            self.assertIn('inconclusiva', text)
            for forbidden in ('SECRET', 'PRIVATE_NAME', 'PRIVATE_REPORT'):
                self.assertNotIn(forbidden, text)

    def test_manual_edit_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / 'vault'
            export(vault, root)
            note = vault / 'Gerado/Estado do projeto.md'
            note.write_text('Minha anotação manual.', encoding='utf-8')
            result = export(vault, root)
            self.assertEqual(result['preserved_user_edits'], [note.name])
            self.assertEqual(note.read_text(encoding='utf-8'), 'Minha anotação manual.')

    def test_new_export_does_not_overwrite_existing_unmanaged_note(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Gerado').mkdir()
            (root / 'Gerado/Estado do projeto.md').write_text('Preexistente', encoding='utf-8')
            self.assertTrue(export(root, root)['preserved_user_edits'])
