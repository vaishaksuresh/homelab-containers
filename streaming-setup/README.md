# Streaming setup (Redpanda + Flink) on k3s

A minimal stack for learning Flink, aimed at a realtime voting app (votes in, live tallies
and winners out). It runs on the k3s cluster in [`../k3s-setup`](../k3s-setup). Installed
2026-11-07.

## What's installed

| Component | Namespace | Chart / version | Notes |
|---|---|---|---|
| cert-manager | `cert-manager` | `jetstack/cert-manager` v1.21.3 | Needed by the Flink operator webhook. Supports k8s 1.33–1.36 |
| Redpanda (1 broker, **Community Edition**) | `redpanda` | `redpanda/redpanda` 26.2.5 (Redpanda v26.2.6) | Plaintext, no SASL, no external listener |
| Redpanda Console | `redpanda` | bundled with the Redpanda chart (Console v3.9.0) | No login or RBAC (those are enterprise features) |
| Flink Kubernetes Operator | `flink` | `flink-kubernetes-operator` 1.16.1 | Watches only the `flink` namespace |

Redpanda resources: 1 core (`overprovisioned`), 2Gi memory, and a 10Gi PVC on `local-path`.
The storage class is set explicitly because the cluster has **two** default StorageClasses
(`local-path` and `nfs-client`). Always set `storageClassName` on new PVCs.

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
| `votes` | 3 | 1 | default (delete) |
| `tallies` | 3 | 1 | `cleanup.policy=compact` |

```bash
kubectl -n redpanda exec -it redpanda-0 -c redpanda -- rpk topic list
```

## Connecting

- **Kafka bootstrap for Flink** (in-cluster, plaintext):
  `redpanda-0.redpanda.redpanda.svc.cluster.local:9093`
- **Schema Registry** (in-cluster): `http://redpanda-0.redpanda.redpanda.svc.cluster.local:8081`
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
On a single broker, continuous balancing did nothing useful anyway.

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
