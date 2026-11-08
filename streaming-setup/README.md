# Streaming setup (Redpanda + Flink) on k3s

Minimal stack for learning Flink with a realtime voting app. Installed 2026-11-07.

| Component | Namespace | Chart / version |
|---|---|---|
| cert-manager | `cert-manager` | jetstack/cert-manager v1.21.3 |
| Redpanda (1 broker, plaintext, no SASL) + Console | `redpanda` | redpanda/redpanda 26.2.5 (Redpanda v26.2.6) |
| Flink Kubernetes Operator (watches `flink`) | `flink` | flink-kubernetes-operator 1.16.1 |

Redpanda data: 10Gi PVC on `local-path` (set explicitly; the cluster has two default StorageClasses).

## Install

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo add redpanda https://charts.redpanda.com
helm repo add flink-operator-repo https://downloads.apache.org/flink/flink-kubernetes-operator-1.16.1/
helm repo update

helm install cert-manager jetstack/cert-manager --version v1.21.3 -n cert-manager --create-namespace -f cert-manager-values.yaml --wait
helm install redpanda redpanda/redpanda --version 26.2.5 -n redpanda --create-namespace -f redpanda-values.yaml --wait
./create-topics.sh
helm install flink-kubernetes-operator flink-operator-repo/flink-kubernetes-operator --version 1.16.1 -n flink --create-namespace -f flink-operator-values.yaml --wait
```

## Use

- Kafka bootstrap (in-cluster, plaintext): `redpanda-0.redpanda.redpanda.svc.cluster.local:9093`
- Topics: `votes` (3 partitions), `tallies` (3 partitions, `cleanup.policy=compact`), RF 1
- Console: `kubectl -n redpanda port-forward svc/redpanda-console 8080:8080` then http://localhost:8080
- rpk: `kubectl -n redpanda exec -it redpanda-0 -c redpanda -- rpk topic list`

## Smoke test Flink

```bash
kubectl apply -f manifests/flink-smoke-test.yaml   # upstream basic.yaml (Flink 2.2)
kubectl -n flink get flinkdeployment basic-example # wait for RUNNING / STABLE
kubectl -n flink delete -f manifests/flink-smoke-test.yaml
```
