#!/usr/bin/env bash
# (Re)create every index from mappings/. Destructive: pass --force to confirm.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_es

FORCE="${1:-}"
say "Creating indices on $ES"
for f in "$ROOT"/elasticsearch/mappings/*.json; do
  idx=$(basename "$f" .json)
  if curl -fsS -o /dev/null "$ES/$idx" 2>/dev/null; then
    if [ "$FORCE" = "--force" ]; then
      curl -fsS -XDELETE "$ES/$idx" >/dev/null && ok "deleted existing $idx"
    else
      printf '\033[0;33m  skip\033[0m%s already exists (use --force to recreate)\n' " $idx"
      continue
    fi
  fi
  resp=$(curl -fsS -XPUT "$ES/$idx" -H 'Content-Type: application/json' --data-binary "@$f")
  echo "$resp" | jq -e '.acknowledged == true' >/dev/null || die "$idx: $resp"
  ok "created $idx"
done
