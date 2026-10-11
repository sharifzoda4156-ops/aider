"""Offline regressions for opt-in definition priority within the existing cap."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aider.symbol_index import StaleSymbolIndex, build_symbol_index


def tag(name, kind, line):
    return SimpleNamespace(name=name, kind=kind, line=line)


class TestSymbolViewPriority(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'a.py').write_text('synthetic python fixture\n' * 4)
        (self.root / 'z.js').write_text('synthetic javascript fixture\n' * 4)
        self.calls = []

    def build(self, tags=None, **limits):
        tags = tags or {
            'a.py': [tag('external', 'ref', 0), tag('another', 'ref', 1),
                     tag('entry', 'def', 2)],
            'z.js': [tag('entry', 'ref', 0), tag('render', 'def', 1)],
        }
        def extract(absolute, relative):
            self.calls.append(relative)
            return tags[relative]
        return build_symbol_index(self.root, list(tags), extract, **limits)

    def symbols(self, view):
        return [s for f in view['files'] for s in f['symbols']]

    def test_default_keeps_source_order_and_existing_output(self):
        index = self.build()
        default = index.view('executor', max_symbols=2)
        self.assertEqual(default, index.view('executor', 2, prefer_definitions=False))
        self.assertEqual([s['kind'] for s in self.symbols(default)], ['ref', 'ref'])
        self.assertNotIn('selection_policy', default)
        self.assertEqual(default['omitted_symbols'], 3)

    def test_definitions_in_later_files_precede_earlier_references(self):
        index = self.build()
        view = index.view('executor', 2, prefer_definitions=True)
        self.assertEqual(self.symbols(view), [
            {'name': 'entry', 'line': 3, 'kind': 'def'},
            {'name': 'render', 'line': 2, 'kind': 'def'},
        ])
        self.assertEqual(view['selection_policy'], 'definitions_first')
        self.assertEqual(view['omitted_symbols'], 3)
        self.assertEqual(view['snapshot_id'], index.view('planner')['snapshot_id'])
        self.assertEqual(self.calls, ['a.py', 'z.js'])

    def test_remaining_budget_retains_lexical_references(self):
        view = self.build().view('executor', 4, prefer_definitions=True)
        first, last = view['files']
        self.assertEqual([s['kind'] for s in first['symbols']], ['def', 'ref', 'ref'])
        self.assertEqual([s['kind'] for s in last['symbols']], ['def'])
        self.assertEqual(view['omitted_symbols'], 1)
        self.assertEqual(len(self.symbols(view)), 4)
        self.assertTrue(any('not resolved calls' in s for s in view['limitations']))

    def test_definition_overflow_is_bounded_and_reported(self):
        index = self.build({'a.py': [tag('one', 'def', 0), tag('two', 'def', 1)],
                            'z.js': [tag('three', 'def', 0)]})
        view = index.view('executor', 1, prefer_definitions=True)
        self.assertEqual(len(self.symbols(view)), 1)
        self.assertEqual(view['files'][1]['symbols'], [])
        self.assertEqual(view['omitted_symbols'], 2)

    def test_reference_only_and_unknown_locations_are_preserved(self):
        index = self.build({'a.py': [tag('unlocated', 'ref', -1), tag('located', 'ref', 0)]})
        view = index.view('executor', 2, prefer_definitions=True)
        self.assertEqual(self.symbols(view), [
            {'name': 'located', 'line': 1, 'kind': 'ref'},
            {'name': 'unlocated', 'line': None, 'kind': 'ref'},
        ])
        self.assertEqual(view['omitted_symbols'], 0)

    def test_unknown_and_extraction_truncation_are_not_promoted_to_complete(self):
        index = self.build({'a.py': [], 'z.js': [tag('ref', 'ref', 0),
                                              tag('hidden', 'def', 1)]},
                           max_symbols_per_file=1)
        view = index.view('executor', 2, prefer_definitions=True)
        self.assertEqual([f['coverage'] for f in view['files']], ['unknown', 'truncated'])
        self.assertEqual([s['name'] for s in self.symbols(view)], ['ref'])
        self.assertEqual(view['omitted_symbols'], 0)  # Unparsed tags are not counted.

    def test_duplicates_removed_by_index_and_same_name_locations_retained(self):
        index = self.build({'a.py': [tag('name', 'def', 0), tag('name', 'def', 0),
                                   tag('name', 'def', 1), tag('name', 'ref', 1)]})
        view = index.view('executor', 2, prefer_definitions=True)
        self.assertEqual([s['line'] for s in self.symbols(view)], [1, 2])
        self.assertEqual(view['omitted_symbols'], 1)

    def test_stale_content_is_still_rejected(self):
        index = self.build()
        (self.root / 'a.py').write_text('changed')
        with self.assertRaises(StaleSymbolIndex):
            index.view('executor', 2, prefer_definitions=True)

    def test_invalid_options_and_planner_opt_in_are_rejected(self):
        index = self.build()
        for value in (None, 0, 1, 'true', []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                index.view('executor', prefer_definitions=value)
        with self.assertRaises(ValueError):
            index.view('planner', prefer_definitions=True)
        self.assertEqual(index.view('planner'),
                         index.view('planner', prefer_definitions=False))


if __name__ == '__main__':
    unittest.main()
