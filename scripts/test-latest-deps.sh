#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

artifact_dir=${1:?Usage: test-latest-deps.sh ARTIFACT_DIRECTORY}
mkdir -p "$artifact_dir"
artifact_dir=$(realpath "$artifact_dir")

docker run --rm --userns=host \
  --mount "type=bind,source=$PWD,target=/source,readonly" \
  --mount "type=bind,source=$artifact_dir,target=/artifacts" \
  --workdir /app \
  ghcr.io/astral-sh/uv:python3.13-trixie bash -euo pipefail -c '
    apt-get update
    apt-get install -y --no-install-recommends libcairo2 git
    git -c safe.directory=/source -C /source ls-files -z |
      tar -C /source --null -T - -cf - | tar -xf -
    cp -a /source/.git .git
    git config --global --add safe.directory /app
    uv lock --upgrade
    cp uv.lock /artifacts/uv.lock
    uv sync --frozen --all-extras --dev
    uv run --frozen pytest src/send_bills/tests
  '
