#!/usr/bin/env bash
# Create the Nginx Proxy Manager proxy host redpanda.heb.bet -> Redpanda Console (k3s NodePort 30081).
# Repo conventions: NPM at 10.0.20.200 (API on :81), *.heb.bet resolves to NPM via AdGuard,
# SSL is terminated in NPM with a Let's Encrypt cert for *.heb.bet.
#
# Auth: export NPM_TOKEN=<bearer token>, or leave it unset and you'll be prompted for the
# NPM admin email/password (the password is read silently and never echoed or stored).
set -euo pipefail

NPM_API="${NPM_API:-http://10.0.20.200:81/api}"
DOMAIN="${DOMAIN:-redpanda.heb.bet}"
FORWARD_HOST="${FORWARD_HOST:-10.0.20.160}"   # heimdall; NodePort is open on every node
FORWARD_PORT="${FORWARD_PORT:-30081}"

command -v jq >/dev/null || { echo "jq is required (brew install jq)"; exit 1; }

if [ -z "${NPM_TOKEN:-}" ]; then
  read -rp "NPM admin email: " NPM_EMAIL
  read -rsp "NPM admin password: " NPM_PASS; echo
  NPM_TOKEN=$(jq -n --arg i "$NPM_EMAIL" --arg s "$NPM_PASS" '{identity:$i, secret:$s}' |
    curl -sf -H 'Content-Type: application/json' -d @- "$NPM_API/tokens" | jq -r .token)
  unset NPM_PASS
fi
[ -n "$NPM_TOKEN" ] && [ "$NPM_TOKEN" != null ] || { echo "Login failed"; exit 1; }
AUTH=(-H "Authorization: Bearer $NPM_TOKEN")

if curl -sf "${AUTH[@]}" "$NPM_API/nginx/proxy-hosts" |
   jq -e --arg d "$DOMAIN" 'any(.[]; .domain_names | index($d))' >/dev/null; then
  echo "A proxy host for $DOMAIN already exists; not creating another."; exit 0
fi

# Prefer an existing cert that covers *.heb.bet (or the exact name). 0 = no cert.
CERT_ID=$(curl -sf "${AUTH[@]}" "$NPM_API/nginx/certificates" | jq -r --arg d "$DOMAIN" '
  [ .[] | select(.domain_names | index("*.heb.bet") or index($d)) | .id ] | first // 0')
echo "Using certificate id: $CERT_ID"

SSL=false; [ "$CERT_ID" != 0 ] && SSL=true
jq -n --arg d "$DOMAIN" --arg h "$FORWARD_HOST" --argjson p "$FORWARD_PORT" \
      --argjson c "$CERT_ID" --argjson ssl "$SSL" '{
  domain_names: [$d], forward_scheme: "http", forward_host: $h, forward_port: $p,
  certificate_id: $c, ssl_forced: $ssl, http2_support: $ssl, hsts_enabled: false,
  block_exploits: true, allow_websocket_upgrade: true, caching_enabled: false,
  access_list_id: 0, advanced_config: "", locations: [], meta: {}
}' | curl -sf "${AUTH[@]}" -H 'Content-Type: application/json' -d @- "$NPM_API/nginx/proxy-hosts" |
  jq '{id, domain_names, forward_host, forward_port, certificate_id, ssl_forced, enabled}'
[ "$CERT_ID" = 0 ] && echo "No *.heb.bet cert found: host is HTTP-only. Add/request a cert in NPM, then edit the host."
