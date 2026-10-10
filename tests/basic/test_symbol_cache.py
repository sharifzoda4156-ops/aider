import ast
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

from aider.symbol_cache import SymbolCache, cache_key

Tag = namedtuple('Tag', 'rel_fname fname line name kind')


def shared_method():
    path = Path(__file__).resolve().parents[2] / 'aider' / 'repomap.py'
    cls = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'RepoMap')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_shared_tags')
    env = dict(Path=Path, Tag=Tag, cache_key=cache_key, filename_to_lang=lambda _: 'python')
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), env)
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


if __name__ == '__main__':
    unittest.main()
