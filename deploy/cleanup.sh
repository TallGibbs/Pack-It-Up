#!/usr/bin/env bash
# Delete moves (runs/<id>/) with no file changed in RUNS_KEEP_DAYS days, and cache files older
# than CACHE_KEEP_DAYS days. Run daily by packitup-cleanup.timer as the service user.
# The usage history in .history/analysis.db keeps a deleted move, marked archived.
#   deploy/cleanup.sh [APP_DIR]        DRY_RUN=1 deploy/cleanup.sh   lists what it would delete
set -euo pipefail

APP_DIR="${1:-/opt/pack-it-up}"
RUNS_KEEP_DAYS="${RUNS_KEEP_DAYS:-30}"
CACHE_KEEP_DAYS="${CACHE_KEEP_DAYS:-14}"
DRY_RUN="${DRY_RUN:-0}"

remove() { if [ "$DRY_RUN" = "1" ]; then echo "would delete $1"; else rm -rf -- "$1"; echo "deleted $1"; fi; }

if [ -d "$APP_DIR/runs" ]; then
  for run in "$APP_DIR"/runs/*/; do
    [ -d "$run" ] || continue
    # Keep the move if any file in it changed recently.
    if [ -z "$(find "$run" -type f -newermt "-$RUNS_KEEP_DAYS days" -print -quit)" ]; then
      remove "${run%/}"
    fi
  done
fi

for dir in llm renders route_live shop_mcp co_move_scans; do
  [ -d "$APP_DIR/.cache/$dir" ] || continue
  find "$APP_DIR/.cache/$dir" -type f -mtime "+$CACHE_KEEP_DAYS" -print0 |
    while IFS= read -r -d '' f; do remove "$f"; done
done
