"""Real parser/tokenizer integration; full Aider dependencies are required."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tiktoken

from aider.repomap import RepoMap


class TestRepoMapFeaturesIntegration(unittest.TestCase):
    def model(self):
        encoding = tiktoken.get_encoding('cl100k_base')
        return SimpleNamespace(token_count=lambda text: len(encoding.encode(text)))

    def io(self):
        return SimpleNamespace(read_text=lambda path: Path(path).read_text(),
            tool_output=lambda *a: None, tool_warning=lambda *a: None,
            tool_error=lambda *a: None)

    def test_real_map_scope_and_hard_ceiling(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / 'repo'
            repo.mkdir()
            (repo / 'engine').mkdir(); (repo / 'client').mkdir()
            (repo / 'engine' / 'pyproject.toml').write_text('[project]\nname="engine"\n')
            py = repo / 'engine' / 'service.py'
            py.write_text('def search_service(query):\n    return query\n\ndef handle_request(query):\n    return search_service(query)\n')
            js = repo / 'client' / 'view.js'
            js.write_text('export function renderView(value) { return value; }\n')
            with patch.dict(os.environ, {'AIDER_SYMBOL_CACHE_DIR': str(root / 'cache')}):
                model = self.model()
                rm = RepoMap(root=str(repo), io=self.io(), main_model=model,
                    map_tokens=128, map_token_limit=128, max_context_window=8192,
                    scope_paths='auto', repo_content_prefix='Repository outline:\n')
                try:
                    text = rm.get_repo_map([], [str(py), str(js), str(repo / 'engine' / 'pyproject.toml')],
                                           mentioned_fnames={'engine/service.py'})
                    self.assertTrue(text)
                    self.assertLessEqual(model.token_count(text), 128)
                    self.assertTrue(rm.last_scope_metrics['applied'])
                    self.assertTrue(rm.symbol_cache.stats['writes'])
                    self.assertTrue(list(rm.get_tags(str(js), 'client/view.js')))
                finally:
                    rm.TAGS_CACHE.close()

    def test_real_symbols_reused_and_paths_rebound(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            maps = []
            try:
                with patch.dict(os.environ, {'AIDER_SYMBOL_CACHE_DIR': str(root / 'cache')}):
                    for name in ('one', 'two'):
                        repo = root / name; repo.mkdir()
                        source = repo / 'api.py'
                        source.write_text('def get_value():\n    return 1\n')
                        rm = RepoMap(root=str(repo), io=self.io(), main_model=self.model(),
                                     map_token_limit=128, scope_paths=[])
                        maps.append(rm)
                        tags = list(rm.get_tags(str(source), 'api.py'))
                        self.assertTrue(tags)
                        self.assertTrue(all(t.fname == str(source) for t in tags))
                    self.assertEqual(maps[1].symbol_cache.stats['hits'], 1)
                    self.assertEqual(maps[1].symbol_cache.stats['writes'], 0)
                    stamp = source.stat().st_mtime_ns
                    source.write_text('def updated_value():\n    return 2\n')
                    os.utime(source, ns=(stamp, stamp))
                    tags = list(maps[1].get_tags(str(source), 'api.py'))
                    self.assertTrue(any(t.name == 'updated_value' for t in tags))
                    self.assertFalse(any(t.name == 'get_value' for t in tags))
            finally:
                for rm in maps:
                    rm.TAGS_CACHE.close()

    def test_default_features_off_and_cache_inside_repo_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / 'repo'; repo.mkdir()
            with patch.dict(os.environ, {}, clear=True):
                rm = RepoMap(root=str(repo), io=self.io(), main_model=self.model())
                try:
                    self.assertIsNone(rm.map_token_limit)
                    self.assertEqual(rm.scope_paths, ())
                    self.assertIsNone(rm.symbol_cache)
                finally:
                    rm.TAGS_CACHE.close()
            with patch.dict(os.environ, {'AIDER_SYMBOL_CACHE_DIR': str(repo / 'cache')}):
                rm = RepoMap(root=str(repo), io=self.io(), main_model=self.model(), scope_paths=[])
                try:
                    self.assertIsNone(rm.symbol_cache)
                    self.assertFalse((repo / 'cache').exists())
                finally:
                    rm.TAGS_CACHE.close()


if __name__ == '__main__':
    unittest.main()
