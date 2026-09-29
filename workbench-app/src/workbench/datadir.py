"""Where the workbench keeps its working data.

Code and data live in different places on purpose:

* The **repo** (what is on GitHub) holds the app, the specs, and the published
  example programs in ``<repo>/examples/``.
* The **data folder** holds every program you actually work on — including live
  engagement material — plus the run log (``runs/stamps.jsonl``) and exports.
  It sits OUTSIDE the git repo, so nothing in it can be committed by accident.

Data folder precedence:
  1. an explicit ``data=`` argument (tests, hosted deployments);
  2. an explicitly passed app root (tests / legacy single-folder layout) — data
     then lives inside that root, exactly as before;
  3. ``WORKBENCH_DATA`` (environment or ``workbench-app/.env``);
  4. default: a ``workbench-data`` folder beside the repo.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

DATA_ENV = "WORKBENCH_DATA"
SKIP_ON_COPY = {"restricted", "explorations", ".DS_Store", "__pycache__"}


def repo_root(app_root: Path) -> Path:
    """The git repo root: the folder that contains workbench-app/."""
    return Path(app_root).resolve().parent


def examples_dir(app_root: Path) -> Path:
    return repo_root(app_root) / "examples"


def resolve(app_root: Path, data: Optional[str | Path] = None, legacy_root: bool = False) -> Path:
    if data:
        return Path(data).expanduser().resolve()
    if legacy_root:
        return Path(app_root)
    env = os.environ.get(DATA_ENV, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (repo_root(app_root).parent / "workbench-data").resolve()


def seed_examples(app_root: Path, data_root: Path) -> list[str]:
    """First run only: if the data folder has no programs/ yet, copy in the
    published example programs so there is something to read. Never overwrites."""
    programs = Path(data_root) / "programs"
    if programs.exists():
        return []
    programs.mkdir(parents=True)
    seeded = []
    ex = examples_dir(app_root)
    if ex.is_dir():
        for src in sorted(ex.iterdir()):
            if src.is_dir() and not src.name.startswith((".", "_")):
                shutil.copytree(src, programs / src.name)
                seeded.append(src.name)
    return seeded


def legacy_programs(app_root: Path) -> list[str]:
    """Programs still sitting in the old location (workbench-app/programs/)."""
    old = Path(app_root) / "programs"
    if not old.is_dir():
        return []
    return sorted(p.name for p in old.iterdir() if p.is_dir() and not p.name.startswith("."))


def publish_examples(app_root: Path, data_root: Path) -> dict[str, list[str]]:
    """Copy your working versions of the example programs (data folder) into
    <repo>/examples/ so they can be committed. Only programs that are ALREADY
    examples are published; restricted/ and explorations/ are never copied.
    Nothing is deleted — files that exist only in examples/ are reported."""
    report: dict[str, list[str]] = {}
    ex = examples_dir(app_root)
    for dst in sorted(p for p in ex.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        src = Path(data_root) / "programs" / dst.name
        if not src.is_dir():
            report[dst.name] = ["(no working copy in the data folder — left unchanged)"]
            continue
        changed, only_in_examples = [], []
        for f in src.rglob("*"):
            rel = f.relative_to(src)
            if f.is_dir() or SKIP_ON_COPY.intersection(rel.parts):
                continue
            target = dst / rel
            if not target.exists() or target.read_bytes() != f.read_bytes():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                changed.append(str(rel))
        for f in dst.rglob("*"):
            rel = f.relative_to(dst)
            if f.is_file() and not SKIP_ON_COPY.intersection(rel.parts) and not (src / rel).exists():
                only_in_examples.append(f"(only in examples — review) {rel}")
        report[dst.name] = changed + only_in_examples
    return report
