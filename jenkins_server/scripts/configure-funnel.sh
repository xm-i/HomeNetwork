#!/usr/bin/env bash
set -euo pipefail

SOCKET="/run/tailscale/tailscaled.sock"
TS_HOSTNAME="${TS_HOSTNAME:-jenkins-webhook}"

for _ in $(seq 1 30); do
  if [ -S "${SOCKET}" ] && /usr/bin/tailscale --socket="${SOCKET}" status --json >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

STATE="$(/usr/bin/tailscale --socket="${SOCKET}" status --json | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState",""))' 2>/dev/null || true)"

if [ "${STATE}" != "Running" ]; then
  UP_ARGS=(--hostname="${TS_HOSTNAME}" --accept-dns=false)
  if [ -n "${TS_AUTHKEY:-}" ]; then
    UP_ARGS+=(--auth-key="${TS_AUTHKEY}")
  fi
  if [ -n "${TS_EXTRA_ARGS:-}" ]; then
    # shellcheck disable=SC2206
    UP_ARGS+=(${TS_EXTRA_ARGS})
  fi
  /usr/bin/tailscale --socket="${SOCKET}" up "${UP_ARGS[@]}"
else
  /usr/bin/tailscale --socket="${SOCKET}" set --hostname="${TS_HOSTNAME}" --accept-dns=false
fi

/usr/bin/tailscale --socket="${SOCKET}" funnel --bg --yes --set-path=/github-webhook/ http://127.0.0.1:8080/github-webhook/
