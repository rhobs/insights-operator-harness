# Architecture

This document describes the architecture of the Insights Operator ecosystem and how the components in this harness relate to each other.

## Component overview

```
┌─────────────────────────────────────────────────────────┐
│                    OpenShift Cluster                    │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │              insights-operator                   │   │
│  │                                                  │   │
│  │  - Gathers cluster configuration & state         │   │
│  │  - Produces an archive of anonymized data        │   │
│  │  - Reports to Red Hat Insights                   │   │
│  │  - Manages DataGather / InsightsDataGather CRDs  │   │
│  │                                                  │   │
│  │         ┌────────────────────────┐               │   │
│  │         │  insights-runtime-     │               │   │
│  │         │  extractor (sidecar)   │               │   │
│  │         │                        │               │   │
│  │         │  extractor container:  │               │   │
│  │         │  - coordinator (priv.) │               │   │
│  │         │  - extractor_server    │               │   │
│  │         │  - fingerprints        │               │   │
│  │         │                        │               │   │
│  │         │  exporter container:   │               │   │
│  │         │  - HTTP server         │               │   │
│  │         └────────────────────────┘               │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │       deployment-validation-operator             │   │
│  │  - kube-linter checks; does not mutate objects   │   │
│  │  - Exposes Prometheus gauges on port 8383        │   │
│  │  - Insights Operator gathers those metrics       │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
               Red Hat Insights / CCX
```

## Projects

### insights-operator

**Repo:** https://github.com/openshift/insights-operator

A standard OpenShift cluster operator that gathers anonymized system configuration and reports it to Red Hat Insights. It is part of the default OpenShift distribution.

**Key subsystems:**
- **Gatherers** — collect data from the cluster (node configs, logs, Prometheus metrics, etc.)
- **Archive** — packages gathered data into a compressed archive
- **Reporter** — uploads the archive to the Insights ingress service
- **Conditional gathering** — server-driven rules that trigger additional data collection
- **Controllers** — manage `DataGather` and `InsightsDataGather` CRs to support on-demand gathering

**CRDs** (defined in [openshift/api](https://github.com/openshift/api/tree/master/insights)):
- `InsightsDataGather` (`config.openshift.io/v1`) — cluster-scoped config for the operator
- `DataGather` (`insights.openshift.io/v1alpha1`, `v1alpha2`, `v1`) — represents a single on-demand gather operation

**Language:** Go

---

### insights-runtime-extractor

**Repo:** https://github.com/openshift/insights-runtime-extractor

Provides runtime container inspection as a feature integrated into the Insights Operator. Deployed as a two-container pod sharing a volume:

**`extractor` container** (privileged):
- `coordinator` — enters container process namespaces and runs `fingerprints` executables to extract runtime info, storing results on the shared volume
- `extractor_server` — a TCP server that triggers the coordinator on demand

**`exporter` container**:
- HTTP server that receives requests from the Insights Operator, triggers an extraction via the `extractor_server`, reads results from the shared volume, and returns a JSON payload

**Sub-components:**
- `fingerprints/` — self-contained Rust executables, each detecting a specific runtime (JVM, Node.js, Python, etc.)
- `extractor/` — Rust core engine (coordinator + extractor_server)
- `exporter/` — Go HTTP server
- `runtime-samples/` — sample workloads used in e2e tests

**Language:** Rust (extractor, fingerprints) + Go (exporter)

---

### deployment-validation-operator

**Repo:** https://github.com/app-sre/deployment-validation-operator

The Deployment Validation Operator (DVO) checks Kubernetes workloads against [kube-linter](https://github.com/stackrox/kube-linter) best-practice rules, mainly around fault tolerance. It only watches resources: it does not modify them, and it does not define CRDs. Maintained by App-SRE.

Failed checks are Prometheus gauges. A value of `1` means the check failed. Metric names use the `deployment_validation_operator_` prefix and carry `name`, `namespace`, and `kind` labels. The metrics server listens on port `8383`.

**Key behavior:**
- **Checks** — a ConfigMap mirrors kube-linter's `include`, `exclude`, `addAllBuiltIn`, and `doNotAutoAddDefaults`. With no custom ConfigMap, the built-in defaults are `host-ipc`, `host-network`, `host-pid`, `non-isolated-pod`, `pdb-max-unavailable`, `pdb-min-available`, `privilege-escalation-container`, `privileged-container`, `run-as-non-root`, `unsafe-sysctls`, `unset-cpu-requirements`, and `unset-memory-requirements`.
- **Exclusions** — `NAMESPACE_IGNORE_PATTERN` skips whole namespaces. Per-object ignores use kube-linter annotations (`ignore-check.kube-linter.io/<check>` or `kube-linter.io/ignore-all`).
- **Replicas** — run a single pod. Metrics are not shared across replicas.
- **Install** — manual manifests under `deploy/openshift`, or OLM. The default deployment `nodeAffinity` expects an infra node (`node-role.kubernetes.io/infra`).

**Insights Operator integration:**

`GatherDVOMetrics` in insights-operator finds Services labeled `name=deployment-validation-operator`, scrapes `/metrics`, and keeps lines with the `deployment_validation_operator_` prefix. The result is stored at `config/dvo_metrics` in the archive (config id `clusterconfig/dvo_metrics`).

When that Service is in `openshift-deployment-validation-operator`, workload `name` and `namespace` labels are replaced with UIDs. In any other namespace the names are kept, unless the `insights-config` ConfigMap in `openshift-insights` sets `dataReporting.obfuscation` to include `workload_names`. If no matching Service exists, the archive has no `dvo_metrics` file.

**Language:** Go

---

## API / CRD definitions

The Insights Operator CRDs are defined outside the operator repo itself:

- https://github.com/openshift/api/tree/master/insights

---

## Related resources

| Resource | Link |
|----------|------|
| Documentation | https://ccx.pages.redhat.com/ccx-docs/ |
| Enhancement proposals | https://github.com/openshift/enhancements/tree/master/enhancements/insights |
| Integration tests | https://gitlab.cee.redhat.com/ccx/insights-operator-tests |
| CI — insights-operator | https://github.com/openshift/release/tree/main/ci-operator/config/openshift/insights-operator |
| CI — insights-runtime-extractor | https://github.com/openshift/release/tree/main/ci-operator/config/openshift/insights-runtime-extractor |
| CI — deployment-validation-operator | https://github.com/openshift/release/tree/main/ci-operator/config/app-sre/deployment-validation-operator |
| Integration tests — DVO | https://gitlab.cee.redhat.com/ccx/deployment-validation-operator-tests |
