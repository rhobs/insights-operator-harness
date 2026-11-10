# insights-operator-harness

A structured workspace for the Insights Operator and all related components, aggregating projects as Git submodules under `projects/`.

## Projects

| Path | Upstream | Language |
|------|----------|----------|
| `projects/insights-operator` | github.com/openshift/insights-operator | Go |
| `projects/insights-runtime-extractor` | github.com/openshift/insights-runtime-extractor | Rust + Go |
| `projects/deployment-validation-operator` | github.com/app-sre/deployment-validation-operator | Go |
| `projects/release` | github.com/openshift/release | Prow/ci-operator config (YAML) |

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

## CI configuration

`projects/release` is a submodule of [openshift/release](https://github.com/openshift/release), the monorepo that defines the Prow/ci-operator presubmit, postsubmit, and periodic jobs for OpenShift component repos. It's the place to fix, update, or add CI tests for the projects in this harness.

| Project | CI config (in `projects/release`) |
|---------|-----------|
| insights-operator | `ci-operator/config/openshift/insights-operator/` |
| insights-runtime-extractor | `ci-operator/config/openshift/insights-runtime-extractor/` |
| deployment-validation-operator | `ci-operator/config/app-sre/deployment-validation-operator/` |

After editing a config file, run `make update` (from `projects/release`) to regenerate the Prow jobs under `ci-operator/jobs/` — never hand-edit that directory. See `projects/release/CLAUDE.md` for the full workflow (step registry, variant `__periodics.yaml` files, `config-brancher`, etc).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — component overview and subsystem descriptions
- [development/CONTRIBUTING.md](development/CONTRIBUTING.md) — how to add features, test changes on a cluster, and run integration tests

## Skills

Harness-wide Claude Code skills live under `.agents/skills/` (project-specific
skills live under `projects/<name>/.claude/skills/`):

- [prow-failure-investigator](.agents/skills/prow-failure-investigator/SKILL.md) — triage a failed OpenShift Prow CI job for insights-operator / insights-runtime-extractor: flake vs. regression, suspect commit, root cause trace into gatherer code. Requires the [`openshift-ci-mcp`](https://github.com/openshift-eng/openshift-ci-mcp) MCP server to be registered with Claude Code (`claude mcp list` to check); there is no fallback if it's unavailable

## Links

- **Documentation:** https://ccx.pages.redhat.com/ccx-docs/
- **Enhancement proposals** (architecture/design/feature decisions): https://github.com/openshift/enhancements/tree/master/enhancements/insights
- **Insights CRDs** (`InsightsDataGather`, `DataGather`): https://github.com/openshift/api/tree/master/insights
- **Integration tests** (insights-operator + insights-runtime-extractor): https://gitlab.cee.redhat.com/ccx/insights-operator-tests
- **Integration tests** (deployment-validation-operator): https://gitlab.cee.redhat.com/ccx/deployment-validation-operator-tests
- **CI configuration** (see table above): `projects/release` — https://github.com/openshift/release
- **OpenShift CI docs:** https://docs.ci.openshift.org/
- **CI operator config reference:** https://steps.ci.openshift.org/ci-operator-reference
