import ast
import os
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aider.repomap_scope import contains, infer_scope, read_scope, scope_rank


def production_method(name):
    source = Path(__file__).resolve().parents[2] / 'aider' / 'repomap.py'
    cls = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'RepoMap')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    env = dict(infer_scope=infer_scope, scope_rank=scope_rank,
               filter_important_files=lambda _: [], UPDATING_REPO_MAP_MESSAGE='map',
               time=time, Spinner=lambda _: SimpleNamespace(step=lambda *args: None, end=lambda: None))
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), env)
    return env[name]


class TestRepoMapScope(unittest.TestCase):
    def test_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(read_scope(), ())
        with patch.dict(os.environ, {'AIDER_REPO_MAP_SCOPE': '["service with space", "lib"]'}):
            self.assertEqual(read_scope(), ('lib', 'service with space'))
        self.assertEqual(read_scope('auto'), 'auto')
        self.assertEqual(read_scope(['src\\area']), ('src/area',))
        for bad in ('garbage', '{"path":"src"}', ['../src'], ['/src'], ['C:\\src'], ['.'], ['x//y'], ['x\n'], [2]):
            with self.assertRaises(ValueError):
                read_scope(bad)

    def test_boundaries_are_component_safe(self):
        self.assertTrue(contains('src/api', 'src/api/handler.py'))
        self.assertFalse(contains('src/api', 'src/api-old/handler.py'))

    def test_different_project_layouts(self):
        cases = [
            (['pkg/a/package.json', 'pkg/a/src/a.ts', 'pkg/b/package.json'], ['pkg/a/src/a.ts'], ('pkg/a',)),
            (['engine/pyproject.toml', 'engine/lib/a.py'], ['engine/lib/a.py'], ('engine',)),
            (['crates/core/Cargo.toml', 'crates/core/src/lib.rs'], ['crates/core/src/lib.rs'], ('crates/core',)),
            (['ui/Package.swift', 'ui/Sources/App.swift'], ['ui/Sources/App.swift'], ('ui',)),
            (['desktop/App.csproj', 'desktop/View.cs'], ['desktop/View.cs'], ('desktop',)),
            (['package.json', 'main.js', 'util.js'], ['main.js'], ('main.js',)),
            (['src/one.py', 'src/two.py'], ['src/one.py'], ('src',)),
        ]
        for files, seeds, want in cases:
            with self.subTest(files=files):
                self.assertEqual(infer_scope(files, seeds), want)

    def test_nested_manifest_and_unknown_seed(self):
        files = ['outer/package.json', 'outer/inner/pyproject.toml', 'outer/inner/x.py']
        self.assertEqual(infer_scope(files, ['outer/inner/x.py']), ('outer/inner',))
        self.assertEqual(infer_scope(files, ['missing.py']), ())

    def test_stable_interleave_and_no_filtering(self):
        tags = [('global/a.py',), ('area/a.py',), ('area/b.py',), ('area/c.py',), ('area/d.py',), ('global/b.py',)]
        ranked, report = scope_rank(tags, ('area',))
        self.assertEqual(ranked[:4], [tags[1], tags[2], tags[3], tags[0]])
        self.assertCountEqual(ranked, tags)
        self.assertTrue(report['applied'])
        self.assertEqual(scope_rank(tags, ('missing',))[0], tags)
        self.assertEqual(scope_rank(tags, ())[0], tags)

    def test_production_ranking_hook(self):
        tags = [('other/global.py',), ('component/src/a.py',), ('other/next.py',)]
        method = production_method('get_ranked_tags_map_uncached')
        def make(scope):
            return SimpleNamespace(scope_paths=scope, max_map_tokens=1000, verbose=False,
                get_rel_fname=lambda f: f, get_ranked_tags=lambda *a, **k: tags,
                to_tree=lambda t, *_: ''.join(x[0] + '\n' for x in t), token_count=len,
                last_scope_metrics=None)
        other = ['component/package.json', 'component/src/a.py', 'other/global.py', 'other/next.py']
        m = make(('component',))
        result = method(m, [], other)
        self.assertTrue(result.startswith('component/src/a.py'))
        self.assertIn('other/global.py', result)
        auto = make('auto')
        result = method(auto, [], other, mentioned_fnames={'component/src/a.py'})
        self.assertTrue(result.startswith('component/src/a.py'))
        flat = make(())
        self.assertTrue(method(flat, [], other).startswith('other/global.py'))
        unknown = make(('absent',))
        self.assertTrue(method(unknown, [], other).startswith('other/global.py'))

    def test_windows_auto_paths(self):
        method = production_method('get_ranked_tags_map_uncached')
        m = SimpleNamespace(scope_paths='auto', max_map_tokens=1000, verbose=False,
            get_rel_fname=lambda f: f, get_ranked_tags=lambda *a, **k: [('other/x.py',), ('area/x.py',)],
            to_tree=lambda t, *_: ''.join(x[0] + '\n' for x in t), token_count=len,
            last_scope_metrics=None)
        result = method(m, [], ['area\\pyproject.toml', 'area\\x.py', 'other\\x.py'],
                        mentioned_fnames={'area\\x.py'})
        self.assertTrue(result.startswith('area/x.py'))

    def test_map_cache_separates_scope_and_auto_seed(self):
        method = production_method('get_ranked_tags_map')
        calls = []
        m = SimpleNamespace(scope_paths=('one',), refresh='files', last_map=None,
                            map_cache={}, map_processing_time=0)
        def build(*args):
            calls.append(args)
            return str(m.scope_paths) + str(args[3])
        m.get_ranked_tags_map_uncached = build
        first = method(m, [], ['file.py'], 100)
        self.assertEqual(method(m, [], ['file.py'], 100), first)
        self.assertEqual(len(calls), 1)
        m.scope_paths = ('two',)
        self.assertNotEqual(method(m, [], ['file.py'], 100), first)
        m.scope_paths = 'auto'
        a = method(m, [], ['file.py'], 100, mentioned_fnames={'a.py'})
        b = method(m, [], ['file.py'], 100, mentioned_fnames={'b.py'})
        self.assertNotEqual(a, b)


if __name__ == '__main__':
    unittest.main()
