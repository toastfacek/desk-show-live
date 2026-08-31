# One-tweet live flight

Zero-cost operator commands for the Dwarkesh Patel one-tweet live test. Paid
`smoke` and `live` are human-gated and are not implied by a passing test suite.

Flight source (operator-supplied, never paraphrase):

- Tweet: https://x.com/dwarkesh_sp/status/2093833419377815719
- Article: https://www.dwarkesh.com/p/openai-huggingface

## Commands

```bash
python3 -m runtime_flight check --config config.yaml
python3 -m runtime_flight setup-obs --config config.yaml
python3 -m runtime_flight rehearse --config config.yaml --rundown rundowns/one_tweet_90s.yaml
python3 -m runtime_flight replay --latest --out out/flights
python3 -m runtime_flight verify-flight --automated --latest --out out/flights
python3 -m runtime_flight verify-flight --final --latest --out out/flights
```

Paid commands require `RUNTIME_ALLOW_PAID=1` and `--confirm-spend` equal to the
configured cap. They never stop an existing OBS stream.

```bash
RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight smoke \
  --config config.local.yaml --confirm-spend 2.00 --max-fal-submissions 2

RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight live \
  --config config.local.yaml --confirm-spend 12.00 --max-text-requests 24
```

Coding agents stop at S-CODE. Do not run paid smoke or the 90-second flight
from this package's tests.
