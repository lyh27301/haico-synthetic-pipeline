#!/usr/bin/env bash
# Build the two images the step-8 harness runs on, from the SDK in harness/sdk-v1.22.1 (a git worktree of
# ~/Documents/workspace/benchmarks/vendor/software-agent-sdk at tag v1.22.1, plus the same one-line FastAPI fix
# (Query lte= -> le=) the group checkout carries; without it the agent-server dies on import):
#   openagentsafety-agent-server:<sha>  = the OAS Dockerfile, unchanged, with this SDK in its build context
#   openagentsafety-agentdojo:<sha>     = that + our envs and MCP server (harness/Dockerfile.agentdojo)
set -euo pipefail
H="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$H")"
SHA="$(git -C "$H/sdk-v1.22.1" rev-parse --short=9 HEAD)"
CTX="$(mktemp -d)"; trap 'rm -rf "$CTX"' EXIT
mkdir -p "$CTX/benchmarks/vendor/software-agent-sdk"
rsync -a --exclude .git "$H/sdk-v1.22.1/" "$CTX/benchmarks/vendor/software-agent-sdk/"   
docker build -f "$HOME/Documents/workspace/benchmarks/benchmarks/openagentsafety/Dockerfile" \
  -t "openagentsafety-agent-server:$SHA" --platform linux/amd64 "$CTX"
docker build -f "$H/Dockerfile.agentdojo" --build-arg "BASE=openagentsafety-agent-server:$SHA" \
  -t "openagentsafety-agentdojo:$SHA" --platform linux/amd64 "$ROOT"
