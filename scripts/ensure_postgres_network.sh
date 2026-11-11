#!/usr/bin/env bash
set -eu

docker network inspect aiinforsearch-pg-net >/dev/null 2>&1 ||
  docker network create --driver bridge aiinforsearch-pg-net >/dev/null
