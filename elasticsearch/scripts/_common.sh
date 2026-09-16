# Shared config, sourced by the other scripts.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ES="${ES_URL:-http://localhost:9200}"

say()  { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
ok()   { printf '\033[0;32m  ok  \033[0m%s\n' "$*"; }
die()  { printf '\033[0;31m FAIL \033[0m%s\n' "$*" >&2; exit 1; }

require_es() {
  curl -fsS "$ES" >/dev/null 2>&1 || die "Elasticsearch unreachable at $ES. Run: docker compose up -d"
}
