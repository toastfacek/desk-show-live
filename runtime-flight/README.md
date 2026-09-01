# One-tweet live flight

Zero-cost operator commands for the Dwarkesh Patel one-tweet live test. Paid
`smoke` and `live` are human-gated and are not implied by a passing test suite.

`board` is the visual producer harness: a loopback control room with program
preview, live state, writer/story/queue tabs, and operator buttons. It runs a
zero-cost demo clock. `check`, `setup-obs`, `rehearse`, `replay`, and
`verify-flight` are bound to the flight services. `smoke` and `live` are bound
too, but they still refuse unless `RUNTIME_ALLOW_PAID=1` and `--confirm-spend`
matches the cap. They never stop an existing OBS stream.

Flight source (operator-supplied, never paraphrase):

- Tweet: https://x.com/dwarkesh_sp/status/2093833419377815719
- Article: https://www.dwarkesh.com/p/openai-huggingface

## Commands

```bash
python3 -m runtime_flight board --port 8766
python3 -m runtime_flight check --config config.yaml
python3 -m runtime_flight setup-obs --config config.yaml
python3 -m runtime_flight rehearse --config config.yaml --rundown rundowns/one_tweet_90s.yaml
python3 -m runtime_flight replay --latest --out out/flights
python3 -m runtime_flight verify-flight --automated --latest --out out/flights
python3 -m runtime_flight verify-flight --final --latest --out out/flights
```

No-OBS paid segment (planner + writer + two fal takes, hero then chain). Human-gated.
Does not connect to OBS.

```bash
RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight segment \
  --config config.segment.example.yaml --confirm-spend 2.00 --max-fal-submissions 2
```

Paid `smoke` and `live` still require OBS. They never stop an existing OBS stream.

```bash
RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight smoke \
  --config config.local.yaml --confirm-spend 2.00 --max-fal-submissions 2

RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight live \
  --config config.local.yaml --confirm-spend 12.00 --max-text-requests 24
```

Coding agents stop at S-CODE. Do not run paid smoke or the 90-second flight
from this package's tests.
