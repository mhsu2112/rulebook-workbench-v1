#!/usr/bin/env bash
# Build a shareable zip of the Rulebook Workbench (both sibling repos) with
# secrets and machine cruft excluded. Run from the workbench-app folder:
#   bash package-share.sh
#
# Produces ../workbench-share-YYYYMMDD.zip containing rulebook-workbench/ and
# workbench-app/ side by side, ready for a recipient to unzip and follow
# RUN-LOCALLY.md.
#
# Excludes (never shared): .env (your OpenRouter key), programs/*/restricted/
# (interview transcripts), .venv, .git, __pycache__, build cruft.
# To send a CLEAN SLATE with no finished programs, pass --no-programs.
set -euo pipefail

cd "$(dirname "$0")/.."          # parent folder holding both repos
if [[ ! -d rulebook-workbench || ! -d workbench-app ]]; then
  echo "Error: run this from workbench-app; expected rulebook-workbench and workbench-app as siblings." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d)"
OUT="workbench-share-${STAMP}.zip"
rm -f "$OUT"

EXCLUDES=(
  -x '*/.venv/*' -x '*/.git/*' -x '*/__pycache__/*' -x '*.pyc'
  -x '*/.pytest_cache/*' -x '*.egg-info/*' -x '*/.DS_Store'
  -x '*/.env' -x '*/programs/*/restricted/*'
)
if [[ "${1:-}" == "--no-programs" ]]; then
  EXCLUDES+=( -x 'workbench-app/programs/*' )
  echo "Packaging WITHOUT finished programs (clean slate)."
else
  echo "Packaging WITH finished programs (governed artifacts only; restricted stores excluded)."
fi

zip -r "$OUT" rulebook-workbench workbench-app "${EXCLUDES[@]}" >/dev/null

echo "Wrote $(pwd)/$OUT"
echo "Recipient: unzip, keep both folders side by side, then follow workbench-app/RUN-LOCALLY.md"
# Safety check: confirm no secrets slipped in.
if unzip -l "$OUT" | grep -Eq '/\.env$|/restricted/'; then
  echo "WARNING: the archive appears to contain .env or restricted files — inspect before sending." >&2
  exit 1
fi
echo "Verified: no .env or restricted/ content in the archive."
