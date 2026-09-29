"""Copy your working versions of the public example programs into ../examples/.

Usage:  make publish-examples      (then review with git and commit)

Only programs that already exist in examples/ are published — a live
engagement program can never be published this way. restricted/ and
explorations/ folders are never copied, and nothing is deleted.
"""
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "src"))

from workbench import datadir  # noqa: E402
from workbench.server import load_dotenv  # noqa: E402

load_dotenv(APP)
data = datadir.resolve(APP)
print(f"Data folder:     {data}")
print(f"Examples folder: {datadir.examples_dir(APP)}\n")
report = datadir.publish_examples(APP, data)
for pid, files in report.items():
    print(f"{pid}: {len(files)} file(s) updated" if files else f"{pid}: already up to date")
    for f in files[:20]:
        print(f"   {f}")
    if len(files) > 20:
        print(f"   … and {len(files) - 20} more")
print("\nNext: review the changes (git status) and commit when happy.")
