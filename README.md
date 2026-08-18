# insights-operator-harness

A structured workspace for the Insights Operator and all related components, aggregating projects as Git submodules under `projects/`.

## Projects

| Path | Upstream | Language |
|------|----------|----------|
| `projects/insights-operator` | github.com/openshift/insights-operator | Go |
| `projects/insights-runtime-extractor` | github.com/openshift/insights-runtime-extractor | Rust + Go |
| `projects/deployment-validation-operator` | github.com/app-sre/deployment-validation-operator | Go |

## Getting started

```bash
git clone --recurse-submodules <url>
# or after cloning:
git submodule update --init --recursive
```

Update a submodule to latest upstream:
```bash
git submodule update --remote projects/<name>
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — component overview and subsystem descriptions
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to add features, test changes on a cluster, and run integration tests

## Links

- **Documentation:** https://ccx.pages.redhat.com/ccx-docs/
- **Enhancement proposals** (architecture/design/feature decisions): https://github.com/openshift/enhancements/tree/master/enhancements/insights
- **Insights CRDs** (`InsightsDataGather`, `DataGather`): https://github.com/openshift/api/tree/master/insights
- **Integration tests** (insights-operator + insights-runtime-extractor): https://gitlab.cee.redhat.com/ccx/insights-operator-tests
- **CI config — insights-operator:** https://github.com/openshift/release/tree/main/ci-operator/config/openshift/insights-operator
- **CI config — insights-runtime-extractor:** https://github.com/openshift/release/tree/main/ci-operator/config/openshift/insights-runtime-extractor
