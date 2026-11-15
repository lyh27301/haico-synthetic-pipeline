#!/usr/bin/env bash
# Build the step-16b agent image on top of the agent-server image of harness/build_images.sh.
#   harness/v16b/build.sh            -> prints the tag
set -euo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$(dirname "$H")"
SHA="$(git -C "$H/sdk-v1.22.1" rev-parse --short=9 HEAD)"
SUM="$(cd "$ROOT" && cat harness/v16b/Dockerfile harness/v16b/*.py harness/v16b/clock.c harness/v16b/agent-shell harness/*.py \
       recipe/*.py *_suite/*.py | shasum | cut -c1-10)"
TAG="openagentsafety-agentdojo16b:${SHA}-${SUM}"
if ! docker image inspect "$TAG" >/dev/null 2>&1; then
  docker build -f "$H/v16b/Dockerfile" --build-arg "BASE=openagentsafety-agent-server:$SHA" -t "$TAG" \
    --platform linux/amd64 "$ROOT" >&2
fi
echo "$TAG"
