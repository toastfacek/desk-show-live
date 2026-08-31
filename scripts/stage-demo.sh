#!/usr/bin/env bash
# Stage Pack Manager hosts + the reviewed source packet on this machine.
# Does not call fal, a text model, or OBS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/pack-manager${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f pack-manager/fixtures/hero_wide.png ]]; then
  echo "missing pack-manager/fixtures/hero_wide.png" >&2
  exit 1
fi

python3 -m pack_manager.hosts \
  --data-dir pack-manager/data \
  --hero pack-manager/fixtures/hero_wide.png \
  | tee /tmp/desk-show-lock-hosts.out

BASELINE_ID="$(head -n1 /tmp/desk-show-lock-hosts.out)"
if [[ -z "$BASELINE_ID" || "$BASELINE_ID" != baseline_* ]]; then
  echo "lock did not print a baseline id" >&2
  exit 1
fi
printf '%s\n' "$BASELINE_ID" > pack-manager/data/RUNTIME_BASELINE_ID

python3 runtime-flight/scripts/materialize_source.py --inputs runtime-flight/inputs

cat <<EOF
staged
  baseline_id=$BASELINE_ID
  hero=$(sed -n '2p' /tmp/desk-show-lock-hosts.out)
  source=runtime-flight/inputs/source_packet.local.json

export RUNTIME_BASELINE_ID=$BASELINE_ID
export RUNTIME_SPEND_CAP_USD=2.00
# Paid segment still needs FAL_KEY, TEXT_BASE_URL, TEXT_API_KEY, TEXT_MODEL,
# and RUNTIME_ALLOW_PAID=1. Do not put those in git.
EOF
