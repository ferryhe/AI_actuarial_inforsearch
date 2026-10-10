#!/usr/bin/env bash
set -euo pipefail

docker rm -f issue420-test 2>/dev/null || true
docker run --rm --network none --restart no -m 512m --cpus 1.0 --name issue420-test \
  issue420-image:probe python -c "import tiktoken, os; print(tiktoken.__version__, os.environ.get('TIKTOKEN_CACHE_DIR')); print(tiktoken.get_encoding('cl100k_base').name, tiktoken.encoding_for_model('gpt-4').name)"
