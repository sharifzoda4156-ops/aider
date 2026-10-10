import re
from pathlib import Path

from .base_coder import Coder
from .search_prompts import SearchPrompts

TOOL_RE = re.compile(r"^\s*(SEARCH|READ):\s*(.+?)\s*$", re.MULTILINE)
FILES_RE = re.compile(r"^\s*FILES:\s*$(?P<body>(?:\n.*)*)", re.MULTILINE)
READ_RANGE_RE = re.compile(r"^(?P<path>.+?):(?P<start>\d+)-(?P<end>\d+)$")
LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+`?([^`\s]+)`?\s*$")


class SearchCoder(Coder):
    """
    johan: find which files need to be edited by letting the model explore the
    repo with SEARCH/READ tool calls, then answer with a FILES: list.

    Read-only: tools only see git-tracked files under the repo root, no shell.
    The chosen files end up in coder.abs_fnames (and coder.search_files).
    """

    edit_format = "search"
    gpt_prompts = SearchPrompts()

    max_reflections = 8
    max_tools_per_reply = 5
    max_search_matches = 40
    max_read_lines = 200
    max_line_chars = 300
    max_file_bytes = 1_000_000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_files = None
        self.search_tool_calls = 0

        if not self.repo_map:
            return

        self.repo_map.refresh = "always"
        self.repo_map.max_map_tokens *= self.repo_map.map_mul_no_files
        self.repo_map.map_mul_no_files = 1.0

    def fmt_system_prompt(self, prompt):
        prompt = prompt.replace("{max_tools}", str(self.max_tools_per_reply))
        return super().fmt_system_prompt(prompt)

    def check_for_file_mentions(self, content):
        pass

    def reply_completed(self):
        content = self.partial_response_content or ""

        calls = TOOL_RE.findall(content)
        files_match = FILES_RE.search(content)

        if files_match and not calls:
            self.set_search_files(self.parse_files(files_match.group("body")))
            return True

        if not calls:
            if self.num_reflections >= self.max_reflections - 1:
                return True
            self.reflected_message = self.gpt_prompts.no_tools_no_files
            return True

        results = [self.run_tool(kind, arg) for kind, arg in calls[: self.max_tools_per_reply]]
        if len(calls) > self.max_tools_per_reply:
            results.append(f"(only the first {self.max_tools_per_reply} tool calls were run)")

        message = self.gpt_prompts.tool_results_prefix + "\n\n".join(results)
        if self.num_reflections >= self.max_reflections - 1:
            message += "\n\n" + self.gpt_prompts.out_of_rounds
        self.reflected_message = message
        return True

    def parse_files(self, body):
        tracked = set(self.get_all_relative_files())
        files = []
        for line in body.splitlines():
            m = LIST_ITEM_RE.match(line)
            if not m:
                continue
            fname = m.group(1).strip().strip("'\"")
            if fname in tracked and fname not in files:
                files.append(fname)
        return files

    def set_search_files(self, files):
        self.search_files = files
        self.abs_fnames = set()
        for fname in files:
            self.abs_fnames.add(self.abs_root_path(fname))

    def run_tool(self, kind, arg):
        self.search_tool_calls += 1
        if kind == "SEARCH":
            return self.tool_search(arg)
        return self.tool_read(arg)

    def read_tracked(self, fname):
        path = Path(self.abs_root_path(fname))
        try:
            # tracked symlinks must not lead outside the repo (e.g. to ~/.ssh)
            if not path.resolve().is_relative_to(Path(self.root).resolve()):
                return None
            if path.stat().st_size > self.max_file_bytes:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        if b"\0" in data[:8192]:
            return None
        return data.decode("utf-8", errors="replace")

    def clip(self, line):
        line = line.rstrip()
        if len(line) > self.max_line_chars:
            line = line[: self.max_line_chars] + "…"
        return line

    def tool_search(self, pattern):
        header = f"SEARCH: {pattern}"
        try:
            regex = re.compile(pattern)
        except re.error as err:
            return f"{header}\nerror: bad regular expression: {err}"

        matches = []
        total = 0
        for fname in self.get_all_relative_files():
            text = self.read_tracked(fname)
            if text is None:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if len(line) > 2000:
                    continue
                if regex.search(line):
                    total += 1
                    if len(matches) < self.max_search_matches:
                        matches.append(f"{fname}:{lineno}: {self.clip(line)}")

        if not matches:
            return f"{header}\nno matches"
        out = [header, *matches]
        if total > len(matches):
            out.append(f"... {total - len(matches)} more matches, narrow the search")
        return "\n".join(out)

    def tool_read(self, arg):
        header = f"READ: {arg}"
        fname, start, end = arg, None, None
        m = READ_RANGE_RE.match(arg)
        if m:
            fname, start, end = m.group("path"), int(m.group("start")), int(m.group("end"))
        fname = fname.strip().strip("`'\"")

        if fname not in set(self.get_all_relative_files()):
            return f"{header}\nerror: not a tracked file in this repo"
        text = self.read_tracked(fname)
        if text is None:
            return f"{header}\nerror: binary or too large"

        lines = text.splitlines()
        start = max(1, start or 1)
        end = min(len(lines), end or len(lines))
        if end - start + 1 > self.max_read_lines:
            end = start + self.max_read_lines - 1
        body = [f"{n}: {self.clip(lines[n - 1])}" for n in range(start, end + 1)]
        out = [f"{header} (lines {start}-{end} of {len(lines)})", *body]
        if end < len(lines):
            out.append(f"... use READ: {fname}:{end + 1}-{end + self.max_read_lines} for more")
        return "\n".join(out)
