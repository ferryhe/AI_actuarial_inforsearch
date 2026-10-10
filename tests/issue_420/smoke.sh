#!/usr/bin/env bash
set -euo pipefail

image="${1:-issue420-image:v2}"

docker run --rm --network none --restart no -m 512m --cpus 1.0 \
  --workdir /app \
  --env PYTHONPATH=/app \
  --entrypoint python "$image" /app/tests/issue_420/offline_tokenizer_smoke.py
