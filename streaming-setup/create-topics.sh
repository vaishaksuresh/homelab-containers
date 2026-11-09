#!/usr/bin/env bash
# Create the voting-app topics on the 3-broker Redpanda cluster (RF=3).
# Errors if they already exist. acks=all needs a majority of replicas (2 of 3).
set -euo pipefail
rpk() { kubectl -n redpanda exec redpanda-0 -c redpanda -- rpk "$@"; }
rpk topic create votes   -p 3 -r 3
rpk topic create tallies -p 3 -r 3 -c cleanup.policy=compact
rpk topic list
