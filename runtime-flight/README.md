# One-tweet live flight

Zero-cost operator commands for the Dwarkesh Patel one-tweet live test. Paid
`smoke` and `live` are human-gated and are not implied by a passing test suite.

Programme learnings from the first paid OBS live (decode, audio, fade, crop,
overlay port): [LIVE_FLIGHT_CHECK.md](LIVE_FLIGHT_CHECK.md).

`check`, `setup-obs`, `rehearse`, `replay`, and `verify-flight` are bound to the
flight services. `smoke` and `live` are bound too, but they still refuse unless
`RUNTIME_ALLOW_PAID=1` and `--confirm-spend` matches the cap. They never stop an
existing OBS stream.

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

Tweet link → tweet image + dynamic producer card + writer look-ahead (no fal):

```bash
python3 -m runtime_flight stage \
  --config config.local.yaml \
  --tweet-url 'https://x.com/<user>/status/<id>' \
  --confirm-text-requests 3 \
  --keep-overlay

python3 scripts/load-design-preview.py \
  --card-origin http://127.0.0.1:8765

RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight live \
  --config config.local.yaml \
  --source-dir out/staged/<id> \
  --confirm-spend 12.00
```

`--ingest-only` writes the packet, lock, and `tweet.png` with no text model.
`--plan-only` stops after the planner (`--confirm-text-requests 1`).
The default stage path is planner plus two Writer look-ahead lines
(`--confirm-text-requests 3`). Named shows never enter those prompts.

No-OBS paid segment (planner + writer + fal takes). Hero on take 1 and on a speaker cut; same-host runs chain the last frame. Human-gated.
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
