"""Unified-diff parsing used to validate findings against the real PR diff.

This module only ever reads diff text as data (str in, sets/dicts out).
Nothing here — or anywhere in PR Guardian — imports, evals or executes code
found in the pull request (requirement #19). A ``patch`` string is just a
sequence of characters to a regex/string parser, never a program.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FileDiff:
    path: str
    # commentable line numbers per side, exactly as accepted by
    # POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews
    right_lines: set[int] = field(default_factory=set)
    left_lines: set[int] = field(default_factory=set)


class DiffIndex:
    """Maps file path -> commentable (line, side) pairs for one PR diff."""

    def __init__(self, files: dict[str, FileDiff]):
        self._files = files

    @classmethod
    def from_github_files(cls, files: list[dict]) -> "DiffIndex":
        """Build from the GitHub 'list PR files' API response.

        Each element is expected to have ``filename`` and (optionally,
        absent for binary/renamed-only files) ``patch``.
        """
        parsed: dict[str, FileDiff] = {}
        for f in files:
            path = f["filename"]
            patch = f.get("patch")
            file_diff = FileDiff(path=path)
            if patch:
                right, left = parse_patch(patch)
                file_diff.right_lines = right
                file_diff.left_lines = left
            parsed[path] = file_diff
        return cls(parsed)

    def is_commentable(self, path: str, line: int, side: str = "RIGHT") -> bool:
        file_diff = self._files.get(path)
        if file_diff is None:
            return False
        return line in (file_diff.right_lines if side == "RIGHT" else file_diff.left_lines)

    def paths(self) -> list[str]:
        return list(self._files.keys())


def parse_patch(patch: str) -> tuple[set[int], set[int]]:
    """Parse one file's unified-diff hunk text into commentable line sets.

    Returns (right_lines, left_lines): line numbers in the new file (RIGHT)
    and old file (LEFT) that a GitHub PR review comment may attach to.
    Context lines are commentable on both sides; added lines only on
    RIGHT; removed lines only on LEFT.
    """
    right_lines: set[int] = set()
    left_lines: set[int] = set()

    old_line = new_line = 0
    for raw_line in patch.splitlines():
        if raw_line.startswith("@@"):
            old_start, new_start = _parse_hunk_header(raw_line)
            old_line, new_line = old_start, new_start
            continue
        if raw_line.startswith("\\"):
            # e.g. "\ No newline at end of file" — no counter change.
            continue
        if raw_line.startswith("+"):
            right_lines.add(new_line)
            new_line += 1
        elif raw_line.startswith("-"):
            left_lines.add(old_line)
            old_line += 1
        else:
            # context line (starts with a space, or is blank)
            left_lines.add(old_line)
            right_lines.add(new_line)
            old_line += 1
            new_line += 1

    return right_lines, left_lines


def build_diff_text(files: list[dict]) -> str:
    """Render the GitHub 'list PR files' response as one plain-text blob
    for the LLM prompt. Purely textual — this is prompt input, never
    parsed back into code or executed.
    """
    chunks = []
    for f in files:
        patch = f.get("patch")
        if not patch:
            chunks.append(f"FILE: {f['filename']} (binary or no textual diff)")
            continue
        chunks.append(f"FILE: {f['filename']}\n{patch}")
    return "\n\n".join(chunks)


def _parse_hunk_header(line: str) -> tuple[int, int]:
    # Format: @@ -old_start[,old_count] +new_start[,new_count] @@ [context]
    try:
        ranges = line.split("@@")[1].strip()
        old_part, new_part = ranges.split(" ")
        old_start = int(old_part.split(",")[0].lstrip("-"))
        new_start = int(new_part.split(",")[0].lstrip("+"))
        return old_start, new_start
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Malformed hunk header: {line!r}") from exc
