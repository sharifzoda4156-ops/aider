"""Offline budget regressions, including production get_repo_map without parser deps."""
import ast
import os
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aider.repomap_budget import bound_map, read_map_limit


def map_class():
    # Execute the real production method; ranking/parser dependencies are not involved.
    source = Path(__file__).resolve().parents[2] / "aider" / "repomap.py"
    tree = ast.parse(source.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RepoMap")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "get_repo_map")
    module = ast.Module(body=[method], type_ignores=[])
    env = {"time": time, "bound_map": bound_map}
    exec(compile(module, str(source), "exec"), env)
    return type("BudgetMap", (), {"get_repo_map": env["get_repo_map"]})


class TestRepoMapBudget(unittest.TestCase):
    def make_map(self, limit, listing="one\ntwo\nthree\n", prefix=""):
        m = map_class()()
        m.max_map_tokens = 4096
        m.map_mul_no_files = 8
        m.max_context_window = 65536
        m.map_token_limit = limit
        m.verbose = False
        m.repo_content_prefix = prefix
        m.main_model = SimpleNamespace(token_count=len)
        m.last_map_metrics = None
        m.budgets = []
        def rank(chat, other, budget, *args):
            m.budgets.append(budget)
            return listing
        m.get_ranked_tags_map = rank
        return m

    def test_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(read_map_limit())
        with patch.dict(os.environ, {"AIDER_REPO_MAP_TOKEN_LIMIT": "8192"}):
            self.assertEqual(read_map_limit(), 8192)
            self.assertEqual(read_map_limit(100), 100)
        for bad in (-1, "oops", 2.5, True):
            with self.assertRaises(ValueError):
                read_map_limit(bad)

    def test_multiplier_is_bounded(self):
        m = self.make_map(8192)
        m.get_repo_map([], {"a.py"})
        self.assertEqual(m.budgets, [8192])
        self.assertEqual(m.last_map_metrics["actual_tokens"], 14)

    def test_selected_files_keep_base_budget(self):
        m = self.make_map(8192)
        m.get_repo_map({"b.py"}, {"a.py"})
        self.assertEqual(m.budgets, [4096])

    def test_no_limit_preserves_multiplier(self):
        m = self.make_map(None)
        self.assertEqual(m.get_repo_map([], {"a.py"}), "one\ntwo\nthree\n")
        self.assertEqual(m.budgets, [32768])
        self.assertIsNone(m.last_map_metrics)

    def test_model_window_and_zero(self):
        m = self.make_map(8192)
        m.max_context_window = 6000
        m.get_repo_map([], {"a.py"})
        self.assertEqual(m.budgets, [1904])
        m.map_token_limit = 0
        self.assertIsNone(m.get_repo_map([], {"a.py"}))
        self.assertEqual(len(m.budgets), 1)
        self.assertIsNone(m.last_map_metrics)

    def test_actual_render_including_prefix(self):
        m = self.make_map(8, prefix="P:")
        text = m.get_repo_map([], {"a.py"})
        self.assertEqual(text, "P:one\n")
        self.assertLessEqual(len(text), 8)
        self.assertTrue(m.last_map_metrics["clipped"])

    def test_too_small_for_prefix(self):
        m = self.make_map(2, prefix="prefix:")
        self.assertIsNone(m.get_repo_map([], {"a.py"}))

    def test_nonmonotonic_tokenizer_and_whole_lines(self):
        def count(s):
            return {"a\n": 2, "a\nb\n": 100, "a\nb\nc\n": 3}.get(s, len(s))
        text, tokens, clipped = bound_map("", "a\nb\nc\nd\n", 4, count)
        self.assertLessEqual(count(text), 4)
        self.assertEqual(tokens, count(text))
        self.assertTrue(clipped)
        self.assertTrue(not text or text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
