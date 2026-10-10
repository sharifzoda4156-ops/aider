import itertools
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aider.symbol_index import StaleSymbolIndex, build_symbol_index


def tag(name, kind='def', line=0):
    return SimpleNamespace(name=name, kind=kind, line=line)


class TestSymbolIndex(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'api.py'
        self.source.write_text('def api():\n    return helper()\n')

    def build(self, extract=None, **limits):
        return build_symbol_index(self.root, ['api.py'], extract or
                                  (lambda *a: [tag('api'), tag('helper', 'ref', 1)]), **limits)

    def test_views_share_snapshot_and_extract_once(self):
        calls = []
        index = self.build(lambda *a: calls.append(a) or [tag('api'), tag('helper', 'ref', 1)])
        planner, executor = index.view('planner'), index.view('executor')
        self.assertEqual(len(calls), 1)
        self.assertEqual(planner['snapshot_id'], executor['snapshot_id'])
        self.assertEqual(planner['files'][0]['definitions'], [{'name': 'api', 'line': 1}])
        self.assertEqual(len(executor['files'][0]['symbols']), 2)
        self.assertNotIn(str(self.root), str(planner))
        self.assertNotIn('return helper()', str(executor))

    def test_same_mtime_edit_refuses_view(self):
        index = self.build()
        stamp = self.source.stat().st_mtime_ns
        self.source.write_text('def new():\n    return other()\n')
        os.utime(self.source, ns=(stamp, stamp))
        self.assertEqual(index.validate()['changed_files'], ['api.py'])
        with self.assertRaises(StaleSymbolIndex):
            index.view('planner')

    def test_deleted_file_and_symlink_replacement_refuse_view(self):
        index = self.build()
        self.source.unlink()
        self.assertFalse(index.validate()['valid'])
        try:
            self.source.symlink_to(self.root / 'missing.py')
        except OSError:
            return
        self.assertFalse(index.validate()['valid'])

    def test_mutation_during_extraction(self):
        def extract(*args):
            self.source.write_text('changed')
            return [tag('api')]
        with self.assertRaises(StaleSymbolIndex):
            self.build(extract)

    def test_earlier_file_mutation_during_later_extraction(self):
        (self.root / 'z.py').write_text('def z(): pass')
        def extract(absolute, relative):
            if relative == 'z.py':
                self.source.write_text('changed')
            return [tag('api')]
        with self.assertRaises(StaleSymbolIndex):
            build_symbol_index(self.root, ['api.py', 'z.py'], extract)

    def test_bounds_are_explicit(self):
        with self.assertRaises(ValueError):
            self.build(max_file_bytes=2)
        with self.assertRaises(ValueError):
            self.build(max_total_bytes=2)
        with self.assertRaises(ValueError):
            build_symbol_index(self.root, ['api.py', 'z.py'], lambda *a: [], max_files=1)
        with self.assertRaises(ValueError):
            build_symbol_index(self.root, itertools.repeat('api.py'), lambda *a: [], max_files=1)
        index = self.build(lambda *a: itertools.repeat(tag('api')), max_symbols_per_file=2)
        self.assertEqual(index.files[0].coverage, 'truncated')

    def test_unknown_and_projection_truncation(self):
        index = self.build(lambda *a: [])
        self.assertEqual(index.files[0].coverage, 'unknown')
        index = self.build()
        view = index.view('executor', max_symbols=1)
        self.assertEqual(view['omitted_symbols'], 1)
        self.assertEqual(len(view['files'][0]['symbols']), 1)
        with self.assertRaises(ValueError):
            index.view('agent')
        with self.assertRaises(ValueError):
            index.view('planner', max_symbols=True)

    def test_path_traversal_and_symlink_directories(self):
        for path in ('../api.py', '/api.py', 'C:/api.py', 'a\\api.py', 'api\n.py'):
            with self.assertRaises(ValueError):
                build_symbol_index(self.root, [path], lambda *a: [])
        try:
            (self.root / 'alias').symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest('symlinks unavailable')
        with self.assertRaises(ValueError):
            build_symbol_index(self.root, ['alias/api.py'], lambda *a: [])

    def test_snapshot_reproducible_across_clones_and_changes_on_symbols(self):
        index = self.build()
        other = self.root / 'clone'
        other.mkdir()
        (other / 'api.py').write_bytes(self.source.read_bytes())
        clone = build_symbol_index(other, ['api.py'], lambda *a: [tag('api'), tag('helper', 'ref', 1)])
        self.assertEqual(index.snapshot_id, clone.snapshot_id)
        different = self.build(lambda *a: [tag('different')])
        self.assertNotEqual(index.snapshot_id, different.snapshot_id)

    def test_unknown_lexical_locations_and_invalid_tags(self):
        index = self.build(lambda *a: [tag('helper', 'ref', -1), tag('bad', 'other'),
                                      tag('x' * 513), tag('bad', line='1')])
        self.assertEqual(index.view('executor')['files'][0]['symbols'],
                         [{'name': 'helper', 'line': None, 'kind': 'ref'}])


if __name__ == '__main__':
    unittest.main()
