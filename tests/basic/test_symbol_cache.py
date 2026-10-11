import ast
import tempfile
import unittest
from collections import namedtuple
from itertools import islice
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aider.symbol_cache import SymbolCache, cache_key

Tag = namedtuple('Tag', 'rel_fname fname line name kind')


def shared_method():
    path = Path(__file__).resolve().parents[2] / 'aider' / 'repomap.py'
    cls = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'RepoMap')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_shared_tags')
    build = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'build_symbol_index')
    env = dict(Path=Path, Tag=Tag, cache_key=cache_key, islice=islice,
               filename_to_lang=lambda _: 'python')
    exec(compile(ast.Module(body=[method, build], type_ignores=[]), str(path), 'exec'), env)
    return env


class TestSymbolCache(unittest.TestCase):
    def test_key_invalidation(self):
        args = ['code', 'python', 'query', 'a.py', {'parser': '1'}, 'impl']
        original = cache_key(*args)
        for index, replacement in enumerate(['edit', 'js', 'new-query', 'b.py', {'parser': '2'}, 'new-impl']):
            changed = args.copy()
            changed[index] = replacement
            self.assertNotEqual(original, cache_key(*changed))

    def test_restart_and_corrupt_entry(self):
        with tempfile.TemporaryDirectory() as d:
            c = SymbolCache(d)
            self.assertIsNone(c.get('k'))
            c.put('k', [[0, 'hello', 'def']])
            self.assertEqual(SymbolCache(d).get('k'), [[0, 'hello', 'def']])
            with c.connect() as db:
                db.execute('UPDATE tags SET payload=? WHERE key=?', ('not-json', 'k'))
            self.assertIsNone(c.get('k'))
            self.assertEqual(c.stats['errors'], 1)
            with c.connect() as db:
                db.execute('UPDATE tags SET payload=? WHERE key=?', (b'bad-blob', 'k'))
            self.assertIsNone(c.get('k'))
            self.assertEqual(c.stats['errors'], 2)

    def test_eviction_and_size_limit(self):
        with tempfile.TemporaryDirectory() as d:
            c = SymbolCache(d, max_bytes=40)
            c.put('one', [[0, 'a', 'def']])
            c.put('two', [[0, 'b', 'def']])
            c.put('three', [[0, 'c', 'def']])
            with c.connect() as db:
                self.assertLessEqual(db.execute('SELECT SUM(bytes) FROM tags').fetchone()[0], 40)
            self.assertIsNone(c.get('one'))
            c.put('large', [[0, 'x' * 1000, 'def']])
            self.assertIsNone(c.get('large'))

    def test_two_clones_rebind_and_same_mtime_edit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            q = root / 'query.scm'
            q.write_text('query')
            a, b = root / 'clone-a' / 'a.py', root / 'clone-b' / 'a.py'
            a.parent.mkdir(); b.parent.mkdir()
            a.write_text('def old(): pass'); b.write_text(a.read_text())
            env = shared_method()
            env['get_scm_fname'] = lambda _: q
            calls = []
            def make():
                m = SimpleNamespace(symbol_cache=SymbolCache(root / 'cache'),
                    symbol_parser_identity={'parser': '1'}, symbol_implementation='impl',
                    io=SimpleNamespace(read_text=lambda f: Path(f).read_text()))
                def parse(f, rel):
                    calls.append(f)
                    yield Tag(rel, f, 0, 'new' if 'new' in Path(f).read_text() else 'old', 'def')
                m.get_tags_raw = parse
                return m
            method = env['get_shared_tags']
            first = method(make(), str(a), 'a.py')
            second = method(make(), str(b), 'a.py')
            self.assertEqual(len(calls), 1)
            self.assertEqual(second[0].fname, str(b))
            self.assertEqual(first[0].name, second[0].name)
            import os
            stamp = b.stat().st_mtime_ns
            b.write_text('def new(): pass')
            os.utime(b, ns=(stamp, stamp))
            self.assertEqual(method(make(), str(b), 'a.py')[0].name, 'new')
            self.assertEqual(len(calls), 2)

    def test_no_store_on_mid_parse_change_or_empty_result(self):
        with tempfile.TemporaryDirectory() as d:
            q = Path(d) / 'query.scm'; q.write_text('q')
            f = Path(d) / 'a.py'; f.write_text('old')
            env = shared_method(); env['get_scm_fname'] = lambda _: q
            c = SymbolCache(Path(d) / 'cache')
            m = SimpleNamespace(symbol_cache=c, symbol_parser_identity={}, symbol_implementation='impl',
                io=SimpleNamespace(read_text=lambda p: Path(p).read_text()))
            def parse(path, rel):
                f.write_text('changed')
                yield Tag(rel, path, 0, 'old', 'def')
            m.get_tags_raw = parse
            env['get_shared_tags'](m, str(f), 'a.py')
            self.assertEqual(c.stats['writes'], 0)
            m.get_tags_raw = lambda *_: []
            env['get_shared_tags'](m, str(f), 'a.py')
            self.assertEqual(c.stats['writes'], 0)

    def test_concurrent_writers(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as d:
            SymbolCache(d)
            def write(i):
                cache = SymbolCache(d)
                cache.put(str(i), [[0, str(i), 'def']])
                return cache.get(str(i))
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(write, range(16)))
            self.assertTrue(all(results))


class TestBoundedSharedSymbols(unittest.TestCase):
    """Execute production methods with a real SQLite cache and controlled tag streams."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'api.py'
        self.source.write_text('def api(): return 1\n')
        self.query = self.root / 'query.scm'
        self.query.write_text('query')
        self.env = shared_method()
        self.env['get_scm_fname'] = lambda _: self.query
        self.cache = SymbolCache(self.root / 'cache')
        self.consumed = 0
        self.m = SimpleNamespace(
            root=self.root, symbol_cache=self.cache, symbol_parser_identity={},
            symbol_implementation='impl', io=SimpleNamespace(read_text=lambda p: Path(p).read_text()))
        self.m.get_shared_tags = lambda *a, **kw: self.env['get_shared_tags'](self.m, *a, **kw)

    def stream(self, count, duplicate=False, stop_after=None):
        def extract(path, relative):
            for number in range(count):
                self.consumed += 1
                if stop_after is not None and self.consumed > stop_after:
                    raise AssertionError('tag enumeration exceeded cap plus lookahead')
                yield Tag(relative, path, 0, 'api' if duplicate else str(number), 'def')
        self.m.get_tags_raw = extract

    def build(self, cap):
        return self.env['build_symbol_index'](self.m, ['api.py'], max_symbols_per_file=cap)

    def test_miss_bounds_enumeration_and_never_caches_partial_tags(self):
        self.stream(100, stop_after=3)
        index = self.build(2)
        self.assertEqual(self.consumed, 3)
        self.assertEqual(index.files[0].coverage, 'truncated')
        self.assertEqual(len(index.files[0].symbols), 2)
        self.assertEqual(self.cache.stats['writes'], 0)
        # A later, larger request must not see the truncated prefix as a full hit.
        self.stream(4)
        larger = self.build(10)
        self.assertEqual(len(larger.files[0].symbols), 4)
        self.assertEqual(larger.files[0].coverage, 'extracted')
        self.assertEqual(self.cache.stats['hits'], 0)
        self.assertEqual(self.cache.stats['writes'], 1)

    def test_duplicate_tags_still_count_toward_enumeration_limit(self):
        self.stream(100, duplicate=True, stop_after=3)
        index = self.build(2)
        self.assertEqual(self.consumed, 3)
        self.assertEqual(index.files[0].coverage, 'truncated')
        self.assertEqual(len(index.files[0].symbols), 1)
        self.assertEqual(self.cache.stats['writes'], 0)

    def test_default_index_cap_is_forwarded_to_cache_extraction(self):
        self.stream(3000, stop_after=2049)
        index = self.env['build_symbol_index'](self.m, ['api.py'])
        self.assertEqual(self.consumed, 2049)
        self.assertEqual(len(index.files[0].symbols), 2048)
        self.assertEqual(index.files[0].coverage, 'truncated')
        self.assertEqual(self.cache.stats['writes'], 0)

    def test_exact_limit_is_complete_and_reusable(self):
        self.stream(2)
        first = self.build(2)
        self.assertEqual(first.files[0].coverage, 'extracted')
        self.assertEqual(self.cache.stats['writes'], 1)
        self.m.get_tags_raw = lambda *a: self.fail('complete entry should be reused')
        second = self.build(2)
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(self.cache.stats['hits'], 1)

    def test_warm_cache_limits_rebinding_without_poisoning_full_entry(self):
        self.stream(6)
        complete = self.m.get_shared_tags(str(self.source), 'api.py')
        self.assertEqual(len(complete), 6)
        self.m.get_tags_raw = lambda *a: self.fail('cache hit must not parse')
        rebound = self.m.get_shared_tags(str(self.source), 'renamed.py', max_tags=2)
        self.assertEqual(len(rebound), 3)
        self.assertTrue(all(t.rel_fname == 'renamed.py' for t in rebound))
        limited = self.build(2)
        self.assertEqual(limited.files[0].coverage, 'truncated')
        self.assertEqual(len(limited.files[0].symbols), 2)
        self.assertEqual(len(self.build(10).files[0].symbols), 6)
        self.assertEqual(self.cache.stats['writes'], 1)

    def test_all_uncached_fallbacks_are_bounded(self):
        for reason in ('no_code', 'no_language', 'no_query', 'query_read_error', 'corrupt_cache'):
            with self.subTest(reason=reason):
                self.consumed = 0
                self.stream(100, stop_after=3)
                self.query.write_text('query')
                with patch.dict(self.env):
                    self.m.io.read_text = lambda p: Path(p).read_text()
                    if reason == 'no_code':
                        self.m.io.read_text = lambda p: None
                    elif reason == 'no_language':
                        self.env['filename_to_lang'] = lambda _: None
                    elif reason == 'no_query':
                        self.query.unlink()
                    elif reason == 'query_read_error':
                        self.env['get_scm_fname'] = lambda _: SimpleNamespace(
                            exists=lambda: True, read_text=lambda: (_ for _ in ()).throw(OSError()))
                    else:
                        self.cache.put(self.key(), [[0, 'api', 'def']])
                        with self.cache.connect() as db:
                            db.execute('UPDATE tags SET payload=?', ('not-json',))
                    data = self.m.get_shared_tags(str(self.source), 'api.py', max_tags=2)
                self.assertEqual(len(data), 3)
                self.assertEqual(self.consumed, 3)

    def key(self):
        return cache_key(self.source.read_text(), 'python', 'query', 'api.py', {}, 'impl')

    def test_bounded_parse_mutation_is_rejected_and_not_cached(self):
        from aider.symbol_index import StaleSymbolIndex
        def extract(path, relative):
            self.source.write_text('changed')
            yield Tag(relative, path, 0, 'api', 'def')
        self.m.get_tags_raw = extract
        with self.assertRaises(StaleSymbolIndex):
            self.build(2)
        self.assertEqual(self.cache.stats['writes'], 0)

    def test_empty_result_is_unknown_and_not_cached(self):
        self.stream(0)
        self.assertEqual(self.build(2).files[0].coverage, 'unknown')
        self.assertEqual(self.cache.stats['writes'], 0)

    def test_invalid_caps_are_rejected_before_extraction(self):
        self.m.get_tags_raw = lambda *a: self.fail('invalid cap must not parse')
        for cap in (0, -1, True, 2.5, '2'):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.m.get_shared_tags(str(self.source), 'api.py', max_tags=cap)


if __name__ == '__main__':
    unittest.main()
