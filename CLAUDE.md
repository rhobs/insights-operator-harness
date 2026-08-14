# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a structured workspace (harness) for the OpenShift Insights Operator ecosystem. It aggregates related projects as Git submodules under `projects/`.

## Documentation

- https://ccx.pages.redhat.com/ccx-docs/
- **Enhancement proposals** (architecture/design/feature decisions): https://github.com/openshift/enhancements/tree/master/enhancements/insights

## CI configuration

| Project | CI config |
|---------|-----------|
| insights-operator | https://github.com/openshift/release/tree/main/ci-operator/config/openshift/insights-operator |
| insights-runtime-extractor | https://github.com/openshift/release/tree/main/ci-operator/config/openshift/insights-runtime-extractor |

## Integration tests

Integration tests for both insights-operator and insights-runtime-extractor:
https://gitlab.cee.redhat.com/ccx/insights-operator-tests

## Related repositories

- **openshift/api — Insights CRDs** (`InsightsDataGather`, `DataGather`): https://github.com/openshift/api/tree/master/insights

## Submodules

| Path | Upstream | Language |
|------|----------|----------|
| `projects/insights-operator` | github.com/openshift/insights-operator | Go |
| `projects/insights-runtime-extractor` | github.com/openshift/insights-runtime-extractor | Rust + Go |
| `projects/deployment-validation-operator` | github.com/app-sre/deployment-validation-operator | Go |

Clone with submodules:
```bash
git clone --recurse-submodules <url>
# or after cloning:
git submodule update --init --recursive
```

Update a submodule to latest upstream:
```bash
git submodule update --remote projects/<name>
```

## Per-project commands

### insights-operator (`projects/insights-operator`)
```bash
make build       # compile
make run         # run locally (uses config/local.yaml by default)
make test        # run unit tests
make unit        # go test -race ./...
make lint        # golangci-lint
make githooks    # set up git hooks
```

### insights-runtime-extractor (`projects/insights-runtime-extractor`)
Multi-component repo: `fingerprints` (Rust), `extractor` (Rust), `exporter` (Go).
```bash
IMAGE_REGISTRY=quay.io/<user> make build-image   # build both container images
make unit-tests      # Go unit tests (exporter + fingerprints)
make rust-unit-tests # Rust unit tests (extractor)
make lint            # check extractor
make e2e-test        # build image then run e2e
```

### deployment-validation-operator (`projects/deployment-validation-operator`)
```bash
make go-build   # build binary
make test       # unit tests
make lint       # golangci-lint
```

## Architecture

**insights-operator** gathers anonymized OpenShift cluster configuration and reports it to Red Hat Insights. It runs as a standard cluster operator and produces an archive of gathered data.

**insights-runtime-extractor** provides runtime container inspection as a feature integrated into the Insights Operator. It runs as a two-container pod:
- `extractor` container: a privileged coordinator that enters container process namespaces and runs `fingerprints` executables to extract runtime info, paired with an `extractor_server` TCP server that triggers extraction on demand.
- `exporter` container: an HTTP server that triggers the extractor, reads results from a shared volume, and returns a JSON payload.

**deployment-validation-operator** (from app-sre) validates Kubernetes deployment configurations.
