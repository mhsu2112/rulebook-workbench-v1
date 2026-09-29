#!/usr/bin/env bash
# Build a shareable zip of the Rulebook Workbench repo with secrets and machine
# cruft excluded. Run from the workbench-app folder:
#   bash package-share.sh
#
# Produces workbench-share-YYYYMMDD.zip in your data folder's exports/ (or the
# repo root if that folder doesn't exist), containing spec/, examples/,
# workbench-app/, docs/ and README.md — ready for a recipient to unzip and
# follow workbench-app/RUN-LOCALLY.md.
#
# Only the PUBLISHED example programs are included. Your live programs live in
# the data folder outside the repo and are never packaged.
# To send a CLEAN SLATE with no example programs, pass --no-programs.
set -euo pipefail

cd "$(dirname "$0")/.."          # repo root
if [[ ! -d spec || ! -d workbench-app ]]; then
  echo "Error: run this from workbench-app inside the repo (expected spec/ and workbench-app/)." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d)"
DEST="${WORKBENCH_DATA:-../workbench-data}/exports"
[[ -d "$DEST" ]] || DEST="."
OUT="$DEST/workbench-share-${STAMP}.zip"
rm -f "$OUT"

EXCLUDES=(
  -x '*/.venv/*' -x '*/.git/*' -x '*/__pycache__/*' -x '*.pyc'
  -x '*/.pytest_cache/*' -x '*.egg-info/*' -x '*/.DS_Store'
  -x '*/.env' -x '*/restricted/*' -x 'workbench-app/programs/*' -x 'workbench-app/runs/*'
)
PARTS=(spec workbench-app docs README.md)
if [[ "${1:-}" == "--no-programs" ]]; then
  echo "Packaging WITHOUT example programs (clean slate)."
else
  PARTS+=(examples)
  echo "Packaging WITH the published example programs (restricted stores excluded)."
fi

zip -r "$OUT" "${PARTS[@]}" "${EXCLUDES[@]}" >/dev/null

echo "Wrote $OUT"
echo "Recipient: unzip, then follow workbench-app/RUN-LOCALLY.md"
# Safety check: confirm no secrets slipped in.
if unzip -l "$OUT" | grep -Eq '/\.env$|/restricted/'; then
  echo "WARNING: the archive appears to contain .env or restricted files — inspect before sending." >&2
  exit 1
fi
echo "Verified: no .env or restricted/ content in the archive."
