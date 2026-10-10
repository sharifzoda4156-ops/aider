"""
Смоук форка для JAE: собирает Coder так же, как apps/jae/aider_adapter.py
(johan-systems), без вызова LLM. Ловит поломку API, на который опирается JAE.
"""

import subprocess
import sys
import tempfile

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.repo import GitRepo


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def main():
    d = tempfile.mkdtemp()
    git(d, "init", "-q")
    with open(f"{d}/a.py", "w") as f:
        f.write("x = 1\n")
    git(d, "add", "-A")
    git(d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    head = git(d, "rev-parse", "HEAD")

    model = Model("openrouter/deepseek/deepseek-chat-v3")
    io = InputOutput(yes=True, pretty=False)
    abs_fnames = [f"{d}/a.py"]
    repo = GitRepo(io, abs_fnames, d, models=model.commit_message_models())
    coder = Coder.create(
        main_model=model,
        io=io,
        repo=repo,
        fnames=abs_fnames,
        auto_commits=False,
        auto_lint=False,
        suggest_shell_commands=False,
        stream=False,
        edit_format="diff",
        map_tokens=1024,
    )

    assert coder.auto_commits is False
    assert coder.num_malformed_responses == 0
    assert hasattr(coder, "partial_response_content")
    assert coder.allowed_to_edit("new_file.py")
    assert git(d, "rev-parse", "HEAD") == head, "auto_commits=False не должен коммитить"
    print("jae smoke ok")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
