"""Backend preflight checks before launching the API server."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"

# Detect standard git conflict markers and malformed leftovers like >>>>main.
# Supports common forms such as "<<<<<<< HEAD" and ">>>>>>> branch-name".
CONFLICT_RE = re.compile(r"^\s*(<<<<<<<(?:\s+.*)?|=======|>>>>>>>?(?:\s+.*)?|>>>>\s*main)\s*$")

# Some Windows copy/paste flows strip chevrons and leave only `main`/`HEAD` on a line.
SUSPICIOUS_LEFTOVER_RE = re.compile(r"^\s*(main|HEAD)\s*$")


def find_conflicts() -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for py_file in APP_DIR.rglob("*.py"):
        try:
            lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines, start=1):
            if CONFLICT_RE.match(line) or SUSPICIOUS_LEFTOVER_RE.match(line):
                findings.append((py_file, idx, line.strip()))
    return findings


def main() -> int:
    conflicts = find_conflicts()
    if not conflicts:
        return 0

    print("[ERROR] Merge conflict markers were found in backend Python files.")
    print("Please resolve these before starting the backend:")
    for path, line_no, marker in conflicts:
        print(f" - {path}:{line_no}: {marker}")
    print("Tip: remove markers like <<<<<<<, =======, >>>>>>>, >>>>main, or stray main/HEAD lines.")
    print("How to choose in your editor's merge UI:")
    print(" - Accept Current Change: keep your branch's version.")
    print(" - Accept Incoming Change: keep the other branch's version.")
    print(" - Accept Both Changes: keep both, then manually remove duplicates/conflicts.")
    print("After choosing, delete conflict markers and keep valid Python syntax.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
