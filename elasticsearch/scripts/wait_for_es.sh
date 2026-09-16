#!/usr/bin/env bash
# Block until the cluster answers and reaches at least yellow.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

say "Waiting for Elasticsearch at $ES"
for i in $(seq 1 60); do
  if curl -fsS "$ES/_cluster/health?wait_for_status=yellow&timeout=5s" >/dev/null 2>&1; then
    v=$(curl -fsS "$ES" | jq -r .version.number)
    ok "cluster up, Elasticsearch $v"
    curl -fsS "$ES/_cluster/health" | jq '{status,number_of_nodes,active_shards}'
    exit 0
  fi
  printf '.'
  sleep 3
done
die "timed out after 3 minutes. Check: docker compose logs elasticsearch"
