#!/usr/bin/env bash
# Create the voting-app topics on the single Redpanda broker (idempotent-ish: errors if they exist).
set -euo pipefail
RPK="kubectl -n redpanda exec redpanda-0 -c redpanda -- rpk"
$RPK topic create votes   -p 3 -r 1
$RPK topic create tallies -p 3 -r 1 -c cleanup.policy=compact
$RPK topic list
