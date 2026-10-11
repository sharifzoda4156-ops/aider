"""Bounded, content-bound symbol snapshots shared by planner and executor views."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class StaleSymbolIndex(ValueError):
    pass


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("expected a relative POSIX file path")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or ":" in relative or any(ord(c) < 32 for c in relative):
        raise ValueError("invalid repository path")
    absolute = root.joinpath(*path.parts)
    # Do not follow repository symlinks, including directories.
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlinks are not indexed")
    if not absolute.resolve().is_relative_to(root):
        raise ValueError("path escapes repository")
    return absolute, path.as_posix()


def _read(root, path, limit):
    absolute, _ = _path(root, path)
    with absolute.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file exceeds byte limit")
    return absolute, data


@dataclass(frozen=True)
class IndexedFile:
    path: str
    content_sha256: str
    symbols: tuple
    coverage: str


@dataclass(frozen=True)
class SymbolIndex:
    root: Path
    files: tuple
    omitted_files: int
    file_byte_limit: int

    @property
    def snapshot_id(self):
        # Identifies the complete retained index, not a Git revision or an identity.
        records = [(f.path, f.content_sha256, f.symbols, f.coverage) for f in self.files]
        payload = [1, records, self.omitted_files]
        return _digest(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode())

    def validate(self):
        changed = []
        for entry in self.files:
            try:
                _, data = _read(self.root, entry.path, self.file_byte_limit)
                same = _digest(data) == entry.content_sha256
            except (OSError, ValueError):
                same = False
            if not same:
                changed.append(entry.path)
        return {"valid": not changed, "changed_files": changed, "snapshot_id": self.snapshot_id}

    def view(self, role, max_symbols=256, *, prefer_definitions=False):
        if role not in ("planner", "executor"):
            raise ValueError("role must be planner or executor")
        _positive(max_symbols, "max_symbols")
        if type(prefer_definitions) is not bool:
            raise ValueError("prefer_definitions must be a boolean")
        if prefer_definitions and role != "executor":
            raise ValueError("prefer_definitions is only supported for executor views")
        if not self.validate()["valid"]:
            raise StaleSymbolIndex("repository files changed; rebuild symbol index")
        remaining = max_symbols
        prioritized = None
        if prefer_definitions:
            # Scan the already bounded index, reserving the global budget for
            # definitions across all selected files before lexical references.
            prioritized = [[] for _ in self.files]
            for kind in ("def", "ref"):
                if not remaining:
                    break
                for file_number, entry in enumerate(self.files):
                    if not remaining:
                        break
                    for symbol in entry.symbols:
                        if symbol[2] != kind:
                            continue
                        prioritized[file_number].append(symbol)
                        remaining -= 1
                        if not remaining:
                            break
        records = []
        omitted_symbols = 0
        for file_number, entry in enumerate(self.files):
            wanted = [s for s in entry.symbols if role == "executor" or s[2] == "def"]
            if prioritized is None:
                selected = wanted[:remaining]
                remaining -= len(selected)
            else:
                selected = prioritized[file_number]
            omitted_symbols += len(wanted) - len(selected)
            record = {"path": entry.path, "content_sha256": entry.content_sha256,
                      "coverage": entry.coverage}
            if role == "planner":
                record["definitions"] = [{"name": name, "line": line} for line, name, _ in selected]
            else:
                record["symbols"] = [{"name": name, "line": line, "kind": kind}
                                     for line, name, kind in selected]
            records.append(record)
        result = {"schema_version": 1, "snapshot_id": self.snapshot_id, "role": role,
                "files": records, "omitted_files": self.omitted_files,
                "omitted_symbols": omitted_symbols,
                "limitations": ["definitions are not proven public APIs or contracts",
                                "references are lexical candidates, not resolved calls",
                                "empty extraction does not prove absence of symbols",
                                "validation covers selected files, not the entire repository"]}
        if prefer_definitions:
            result["selection_policy"] = "definitions_first"
        return result


def build_symbol_index(root, paths, extract, *, max_files=128, max_file_bytes=1024 * 1024,
                       max_total_bytes=8 * 1024 * 1024, max_symbols_per_file=2048):
    """Extract once, project twice. Caller supplies tracked/authorized file selection.

    extract(absolute_path, relative_path) yields Aider tags; its file reads must
    observe the same workspace. No paid model or repository command is executed.
    """
    for name, value in (("max_files", max_files), ("max_file_bytes", max_file_bytes),
                        ("max_total_bytes", max_total_bytes),
                        ("max_symbols_per_file", max_symbols_per_file)):
        _positive(value, name)
    root = Path(root).resolve()
    # Bound input enumeration too; caller must explicitly narrow a large project.
    selected = set()
    for count, relative in enumerate(paths):
        if count >= max_files * 4:
            raise ValueError("too many input paths; deduplicate and narrow selection")
        _, normalized = _path(root, relative)
        selected.add(normalized)
        if len(selected) > max_files:
            raise ValueError("file selection exceeds max_files; select a narrower scope")
    files = []
    total_bytes = 0
    for relative in sorted(selected):
        absolute, before = _read(root, relative, max_file_bytes)
        total_bytes += len(before)
        if total_bytes > max_total_bytes:
            raise ValueError("selection exceeds total byte limit; select a narrower scope")
        symbols = set()
        capped = False
        # Also bound tag enumeration, including duplicate tags.
        for number, tag in enumerate(extract(str(absolute), relative)):
            if number >= max_symbols_per_file:
                capped = True
                break
            if tag.kind not in ("def", "ref") or type(tag.line) is not int:
                continue
            if not isinstance(tag.name, str) or not tag.name or len(tag.name) > 512:
                continue
            # Tree-sitter uses zero-based lines; lexer fallback has no location.
            line = tag.line + 1 if tag.line >= 0 else None
            symbols.add((line, tag.name, tag.kind))
        _, after = _read(root, relative, max_file_bytes)
        if after != before:
            raise StaleSymbolIndex("file changed during extraction; rebuild symbol index")
        coverage = "truncated" if capped else "extracted" if symbols else "unknown"
        ordered = tuple(sorted(symbols, key=lambda s: (s[0] is None, s[0] or 0, s[1], s[2])))
        files.append(IndexedFile(relative, _digest(before), ordered, coverage))
    result = SymbolIndex(root, tuple(files), 0, max_file_bytes)
    if not result.validate()["valid"]:
        raise StaleSymbolIndex("file changed during index construction; rebuild symbol index")
    return result
