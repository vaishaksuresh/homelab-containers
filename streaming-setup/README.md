# Streaming setup (Redpanda + Flink) on k3s

A minimal stack for learning Flink, aimed at a realtime voting app (votes in, live tallies
and winners out). It runs on the k3s cluster in [`../k3s-setup`](../k3s-setup). Installed
2026-11-07.

## What's installed

| Component | Namespace | Chart / version | Notes |
|---|---|---|---|
| cert-manager | `cert-manager` | `jetstack/cert-manager` v1.21.3 | Needed by the Flink operator webhook. Supports k8s 1.33–1.36 |
| Redpanda (3 brokers, **Community Edition**) | `redpanda` | `redpanda/redpanda` 26.2.5 (Redpanda v26.2.6) | Plaintext, no SASL, no external listener |
| Redpanda Console | `redpanda` | bundled with the Redpanda chart (Console v3.9.0) | No login or RBAC (those are enterprise features) |
| Flink Kubernetes Operator | `flink` | `flink-kubernetes-operator` 1.16.1 | Watches only the `flink` namespace |

Redpanda resources, per broker: 1 core (`overprovisioned`), 2Gi memory, and a 10Gi PVC on
`local-path`. The storage class is set explicitly because the cluster has **two** default
StorageClasses (`local-path` and `nfs-client`). Always set `storageClassName` on new PVCs.

## Redpanda topology and failure tolerance

| Pod | Broker id | Node | Data |
|---|---|---|---|
| `redpanda-0` | 0 | bestla | `datadir-redpanda-0`, local-path on bestla |
| `redpanda-1` | 2 | mimir | `datadir-redpanda-1`, local-path on mimir |
| `redpanda-2` | 1 | heimdall | `datadir-redpanda-2`, local-path on heimdall |

Broker ids were assigned in join order, so they don't match the pod ordinal. Check with
`rpk cluster info`.

- **Placement:** required pod anti-affinity on `kubernetes.io/hostname`, so there's one broker
  per node and a broker never doubles up. The PodDisruptionBudget allows at most one broker
  down at a time (`statefulset.budget.maxUnavailable: 1`).
- **Replication:**
  - `default_topic_replications: 3` and `internal_topic_replication_factor: 3`, so every
    topic, including `_schemas` and `__consumer_offsets`, has 3 replicas.
  - `minimum_topic_replications: 3` rejects creating any topic with RF below 3.
- **Durability:** Redpanda replicates with Raft, so `acks=all` (`acks=-1`) waits for a
  majority of replicas: 2 of 3, the same guarantee as Kafka's `min.insync.replicas=2`.
  Redpanda accepts `min.insync.replicas` as a topic property but doesn't store or apply it,
  so we don't set it.
- **Losing one broker** (node down, pod deleted, rolling upgrade): reads and `acks=all` writes
  keep working. Leadership moves to the surviving replicas, and the broker catches up when it
  returns. Tested 2026-11-08 by deleting `redpanda-2`: 30 `acks=all` messages were produced
  and consumed during the outage, with no leaderless or under-replicated partitions after
  recovery.
- **Losing two brokers:** partitions lose their majority, so produce with `acks=all` fails
  and partitions without a leader become unavailable until a broker returns. No acknowledged
  data is lost.
- **Node-local storage:** a broker's data lives on its node's disk (`local-path`), so a pod
  can only reschedule onto its own node. If a node's disk is lost, its broker must be
  decommissioned and replaced (`rpk redpanda admin brokers decommission <id>`, then delete
  its PVC). The other two replicas keep the data. `local-path` doesn't enforce the 10Gi
  size; brokers see the whole node disk.
- **Leadership balancing:** Community mode uses `partition_autobalancing_mode: node_add`,
  which moves partitions only when a broker is added. Leaders may stay skewed after an
  outage. Redpanda's leader balancer (`enable_leader_balancer`, on by default, Community)
  evens them out over time.

**Known single points of failure (out of scope here):**
- **k3s control plane:** it runs only on heimdall (single server, embedded etcd). If heimdall
  is down, running pods (including the other two brokers) keep working, but nothing can be
  scheduled or changed through the API.
- **NAS (`10.0.15.15`):** it backs the `nfs-client` StorageClass, which is planned for Flink
  checkpoints. If the NAS is down, anything on NFS stalls. Redpanda doesn't use NFS.

## Install / reinstall

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo add redpanda https://charts.redpanda.com
helm repo add flink-operator-repo https://downloads.apache.org/flink/flink-kubernetes-operator-1.16.1/
helm repo update

helm install cert-manager jetstack/cert-manager --version v1.21.3 \
  -n cert-manager --create-namespace -f cert-manager-values.yaml --wait
helm install redpanda redpanda/redpanda --version 26.2.5 \
  -n redpanda --create-namespace -f redpanda-values.yaml --wait
./create-topics.sh
kubectl apply -f manifests/redpanda-console-nodeport.yaml
helm install flink-kubernetes-operator flink-operator-repo/flink-kubernetes-operator --version 1.16.1 \
  -n flink --create-namespace -f flink-operator-values.yaml --wait
```

To change Redpanda settings, edit `redpanda-values.yaml` and run
`helm upgrade redpanda redpanda/redpanda --version 26.2.5 -n redpanda -f redpanda-values.yaml`.

## Topics

| Topic | Partitions | RF | Config |
|---|---|---|---|
| `votes` | 3 | 3 | default (delete) |
| `tallies` | 3 | 3 | `cleanup.policy=compact` |
| `_schemas` (internal) | 1 | 3 | Schema Registry storage, protected topic |
| `__consumer_offsets` (internal) | 16 | 3 | created on first consumer-group use |

```bash
kubectl -n redpanda exec -it redpanda-0 -c redpanda -- rpk topic list
```

## Connecting

- **Kafka bootstrap for Flink** (in-cluster, plaintext): list all three brokers so the client
  can still bootstrap while any one of them is down:
  `redpanda-0.redpanda.redpanda.svc.cluster.local:9093,redpanda-1.redpanda.redpanda.svc.cluster.local:9093,redpanda-2.redpanda.redpanda.svc.cluster.local:9093`
  Use `acks=all` for producers. Flink's Kafka sink with `DeliveryGuarantee.EXACTLY_ONCE` or
  `AT_LEAST_ONCE` sets it.
- **Schema Registry** (in-cluster), on any broker, for example
  `http://redpanda-0.redpanda.redpanda.svc.cluster.local:8081`.
- **Redpanda Console**: **https://redpanda.heb.bet**
  - Nginx Proxy Manager (`10.0.20.200`, Docker, outside the cluster) proxies it to the
    NodePort `30081`, which is open on every node (`http://10.0.20.160:30081`). See
    `manifests/redpanda-console-nodeport.yaml`.
  - Without NPM: `kubectl -n redpanda port-forward svc/redpanda-console 8080:8080`, then
    http://localhost:8080
  - Console rejects `HEAD` requests (405), so check it with a GET (`curl -s -o /dev/null -w '%{http_code}' https://redpanda.heb.bet/`),
    not `curl -I`.
  - If `redpanda.heb.bet` doesn't resolve on a Mac while `dig` works, see the macOS DoH
    note in [`../docs/TROUBLESHOOTING.md`](../docs/TROUBLESHOOTING.md#macos-hebbet-fails-but-dig-works).

## NPM proxy host script

`npm-add-redpanda-console.sh` creates the `redpanda.heb.bet` proxy host through the Nginx
Proxy Manager API (`http://10.0.20.200:81/api`):

1. **Auth:** it uses `NPM_TOKEN` if set. Otherwise it prompts for the NPM admin email and
   password (the password is read silently) and exchanges them for a token. No credentials
   are stored or hardcoded.
2. **Duplicates:** it does nothing if a proxy host for the domain already exists.
3. **SSL:** it reuses the existing `*.heb.bet` Let's Encrypt certificate and forces HTTPS,
   with websockets on. If no such cert exists, the host is created HTTP-only and it warns.
4. **Overrides:** `DOMAIN`, `FORWARD_HOST`, `FORWARD_PORT` and `NPM_API` can be set as
   environment variables to reuse it for other services.

It needs `jq` and must be run by someone who has the NPM admin login.

## Community Edition only (no license)

Every new Redpanda cluster starts a built-in 30-day enterprise trial (this one expires
**Dec 8 2026**) and turns on continuous partition and core balancing by default. We have no
license, so `redpanda-values.yaml` turns those off:

```yaml
config:
  cluster:
    partition_autobalancing_mode: node_add
    core_balancing_continuous: false
```

Why: after the trial, Redpanda keeps running, but enterprise features are restricted and
Redpanda "blocks upgrades to new feature releases if enterprise features are active without
a valid license" ([licensing overview](https://docs.redpanda.com/current/get-started/licensing/overview/),
[disabling enterprise features](https://docs.redpanda.com/current/get-started/licensing/disable-enterprise-features/)).
With 3 brokers, `node_add` still rebalances partitions when a broker is added; continuous
balancing would only add automatic moves after failures or disk-usage changes.

Keep it Community:
- Don't enable SASL/OIDC, audit logging, tiered storage, RBAC, schema ID validation or
  Console login/RBAC.
- Keep these keys in the values file, or a later `helm upgrade` may re-enable the defaults.
- Check after any change. "Enterprise features in use" should not appear:
  ```bash
  kubectl -n redpanda exec redpanda-0 -c redpanda -- rpk cluster license info
  ```
  `Type: free_trial` stays in the output; that's the built-in trial label, not a problem.

Community Edition is free for self-hosting under the BSL 1.1. The main restriction is that
you can't sell it as a hosted streaming service.

## Smoke test Flink

```bash
kubectl apply -f manifests/flink-smoke-test.yaml    # upstream basic.yaml (Flink 2.2)
kubectl -n flink get flinkdeployment basic-example  # wait for RUNNING / STABLE
kubectl -n flink delete -f manifests/flink-smoke-test.yaml
```
