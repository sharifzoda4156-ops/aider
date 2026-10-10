import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import git

from aider.coders import Coder
from aider.coders.search_coder import SearchCoder
from aider.io import InputOutput
from aider.models import Model
from aider.utils import GitTemporaryDirectory


def make_repo():
    repo = git.Repo()
    Path("app").mkdir()
    Path("app/routes.py").write_text("def login():\n    return check_password()\n")
    Path("app/auth.py").write_text("def check_password():\n    return True\n")
    Path("README.md").write_text("demo\n")
    Path("blob.bin").write_bytes(b"\0\1check_password\0")
    Path("secret.env").write_text("check_password=hunter2\n")  # untracked
    repo.git.add("app/routes.py", "app/auth.py", "README.md", "blob.bin")
    repo.git.commit("-m", "init")


class TestSearchCoder(unittest.TestCase):
    def setUp(self):
        self.model = Model("gpt-3.5-turbo")
        self.webbrowser_patcher = patch("aider.io.webbrowser.open")
        self.webbrowser_patcher.start()

    def tearDown(self):
        self.webbrowser_patcher.stop()

    def create(self):
        io = InputOutput(yes=True, pretty=False)
        coder = Coder.create(self.model, "search", io=io, map_tokens=0)
        self.assertIsInstance(coder, SearchCoder)
        return coder

    def scripted(self, coder, replies):
        sent = []

        def mock_send(messages, functions=None):
            sent.append([m for m in messages if m["role"] == "user"][-1]["content"])
            coder.partial_response_content = replies[len(sent) - 1]
            coder.partial_response_function_call = dict()
            return []

        coder.send = mock_send
        return sent

    def test_search_read_then_files(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            sent = self.scripted(
                coder,
                [
                    "SEARCH: check_password\n",
                    "READ: app/auth.py\nREAD: app/routes.py:1-1\n",
                    "FILES:\n- app/auth.py\n- `app/routes.py`\n- not/there.py\n",
                ],
            )
            coder.run(with_message="make login stricter")

            self.assertEqual(coder.search_files, ["app/auth.py", "app/routes.py"])
            self.assertEqual(coder.get_inchat_relative_files(), ["app/auth.py", "app/routes.py"])
            self.assertEqual(coder.search_tool_calls, 3)

            search_result = sent[1]
            self.assertIn("app/routes.py:2:", search_result)
            self.assertIn("app/auth.py:1:", search_result)
            self.assertNotIn("blob.bin", search_result)
            self.assertNotIn("secret.env", search_result)

            read_result = sent[2]
            self.assertIn("1: def check_password():", read_result)
            self.assertIn("READ: app/routes.py:1-1 (lines 1-1 of 2)", read_result)
            self.assertNotIn("return check_password()", read_result)

    def test_read_refuses_untracked_and_traversal(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            for arg in ("secret.env", "../etc/passwd", "/etc/passwd"):
                self.assertIn("not a tracked file", coder.tool_read(arg))
            self.assertIn("binary or too large", coder.tool_read("blob.bin"))

    def test_symlink_outside_repo_is_not_read(self):
        with GitTemporaryDirectory(), tempfile.TemporaryDirectory() as other:
            make_repo()
            outside = Path(other) / "outside_secret.txt"
            outside.write_text("check_password=hunter2\n")
            Path("link.txt").symlink_to(outside)
            git.Repo().git.add("link.txt")
            coder = self.create()
            self.assertIn("binary or too large", coder.tool_read("link.txt"))
            self.assertNotIn("link.txt", coder.tool_search("hunter2"))

    def test_bad_regex_and_no_matches(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            self.assertIn("bad regular expression", coder.tool_search("(unclosed"))
            self.assertIn("no matches", coder.tool_search("zzz_nothing_zzz"))

    def test_search_caps_matches(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            coder.max_search_matches = 1
            out = coder.tool_search("def ")
            self.assertEqual(len([ln for ln in out.splitlines() if ".py:" in ln]), 1)
            self.assertIn("more matches", out)

    def test_nudges_when_no_tools_and_no_files(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            sent = self.scripted(coder, ["I think auth.py", "FILES:\n- app/auth.py\n"])
            coder.run(with_message="x")
            self.assertIn("did not find any SEARCH:/READ:", sent[1])
            self.assertEqual(coder.search_files, ["app/auth.py"])

    def test_empty_files_list(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            self.scripted(coder, ["FILES:\n"])
            coder.run(with_message="add a new module")
            self.assertEqual(coder.search_files, [])
            self.assertEqual(coder.get_inchat_relative_files(), [])

    def test_stops_after_max_reflections(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            coder.max_reflections = 2
            sent = self.scripted(coder, ["SEARCH: def"] * 10)
            coder.run(with_message="x")
            self.assertEqual(len(sent), 3)
            self.assertIn("last chance", sent[-1])
            self.assertIsNone(coder.search_files)

    def test_tool_call_cap_per_reply(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            coder.max_tools_per_reply = 2
            sent = self.scripted(
                coder,
                ["SEARCH: a\nSEARCH: b\nSEARCH: c\n", "FILES:\n- README.md\n"],
            )
            coder.run(with_message="x")
            self.assertIn("only the first 2 tool calls", sent[1])
            self.assertEqual(coder.search_tool_calls, 2)

    def test_does_not_edit_files(self):
        with GitTemporaryDirectory():
            make_repo()
            coder = self.create()
            before = Path("app/auth.py").read_text()
            self.scripted(
                coder,
                [
                    "app/auth.py\n<<<<<<< SEARCH\ndef check_password():\n"
                    "=======\nx\n>>>>>>> REPLACE\n"
                    "FILES:\n- app/auth.py\n"
                ],
            )
            coder.run(with_message="x")
            self.assertEqual(Path("app/auth.py").read_text(), before)
