"""Real RepoMap/tree-sitter integration, without LLM calls."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aider.repomap import RepoMap
from aider.symbol_index import StaleSymbolIndex


class TestSymbolIndexIntegration(unittest.TestCase):
    def test_real_parser_cache_caps_are_equivalent_to_uncached_extraction(self):
        for language, filename, source in (
            ('python', 'api.py', '\n'.join(f'def func{i}(): return {i}' for i in range(8))),
            ('javascript', 'api.js', '\n'.join(
                f'export function func{i}() {{ return func{(i + 1) % 8}(); }}'
                for i in range(8))),
        ):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as d:
                root = Path(d); repo = root / 'repo'; repo.mkdir()
                path = repo / filename
                path.write_text(source)
                with patch.dict(os.environ, {'AIDER_SYMBOL_CACHE_DIR': str(root / 'cache')}):
                    io = SimpleNamespace(read_text=lambda p: Path(p).read_text(),
                                         tool_output=lambda *a: None, tool_warning=lambda *a: None)
                    rm = RepoMap(root=str(repo), io=io, main_model=None)
                    try:
                        original = rm.get_tags_raw
                        consumed = []
                        def observed(*args):
                            for tag in original(*args):
                                consumed.append(tag)
                                yield tag
                        with patch.object(rm, 'get_tags_raw', observed):
                            capped = rm.build_symbol_index([filename], max_symbols_per_file=2)
                        self.assertEqual(len(consumed), 3)
                        self.assertEqual(capped.files[0].coverage, 'truncated')
                        self.assertEqual(rm.symbol_cache.stats['writes'], 0)
                        with patch.object(rm, 'symbol_cache', None):
                            uncached = rm.build_symbol_index([filename], max_symbols_per_file=2)
                        self.assertEqual(capped.snapshot_id, uncached.snapshot_id)
                        # Ordinary map extraction is still complete and can populate the cache.
                        all_tags = rm.get_tags(str(path), filename)
                        self.assertGreater(len(all_tags), 3)
                        self.assertEqual(rm.symbol_cache.stats['writes'], 1)
                        with patch.object(rm, 'get_tags_raw', side_effect=AssertionError('cache miss')):
                            hit = rm.build_symbol_index([filename], max_symbols_per_file=2)
                            full = rm.build_symbol_index([filename], max_symbols_per_file=256)
                        self.assertEqual(hit.snapshot_id, capped.snapshot_id)
                        self.assertEqual(full.files[0].coverage, 'extracted')
                        self.assertGreater(len(full.files[0].symbols), len(hit.files[0].symbols))
                        self.assertEqual(rm.symbol_cache.stats['writes'], 1)
                    finally:
                        rm.TAGS_CACHE.close()

    def test_real_parser_shared_views_and_fresh_content_without_shared_cache(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            root = Path(d)
            source = root / 'api.py'
            source.write_text('def find_value():\n    return 1\n')
            js = root / 'ui.js'
            js.write_text('export function renderView(value) { return value; }\n')
            io = SimpleNamespace(read_text=lambda p: Path(p).read_text(),
                                 tool_output=lambda *a: None, tool_warning=lambda *a: None)
            rm = RepoMap(root=d, io=io, main_model=None)
            try:
                # Prime the legacy mtime cache, then edit without changing mtime.
                self.assertTrue(list(rm.get_tags(str(source), 'api.py')))
                stamp = source.stat().st_mtime_ns
                source.write_text('def changed_value():\n    return 2\n')
                os.utime(source, ns=(stamp, stamp))
                index = rm.build_symbol_index(['api.py', 'ui.js'])
                planner = index.view('planner')
                names = {s['name'] for f in planner['files'] for s in f['definitions']}
                self.assertIn('changed_value', names)
                self.assertIn('renderView', names)
                self.assertNotIn('find_value', names)
                self.assertEqual(planner['snapshot_id'], index.view('executor')['snapshot_id'])
                source.write_text('def later_value(): pass\n')
                with self.assertRaises(StaleSymbolIndex):
                    index.view('executor')
            finally:
                rm.TAGS_CACHE.close()

    def test_shared_cache_reused_by_second_index(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); repo = root / 'repo'; repo.mkdir()
            (repo / 'api.py').write_text('def api(): return 1\n')
            with patch.dict(os.environ, {'AIDER_SYMBOL_CACHE_DIR': str(root / 'cache')}):
                io = SimpleNamespace(read_text=lambda p: Path(p).read_text(),
                                     tool_output=lambda *a: None, tool_warning=lambda *a: None)
                rm = RepoMap(root=str(repo), io=io, main_model=None)
                try:
                    first = rm.build_symbol_index(['api.py'])
                    second = rm.build_symbol_index(['api.py'])
                    self.assertEqual(first.snapshot_id, second.snapshot_id)
                    self.assertGreater(rm.symbol_cache.stats['hits'], 0)
                finally:
                    rm.TAGS_CACHE.close()
