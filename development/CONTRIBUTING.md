# Contributing

This guide covers contribution workflows for the projects in this harness. Because **insights-operator**, **insights-runtime-extractor**, and **deployment-validation-operator** are all developed directly in their OpenShift/App-SRE repos (there is no separate community upstream to contribute to first), changes go straight to those repos.

## insights-operator

### Adding a new gatherer

The `/create-gatherer` skill in Claude Code can scaffold the boilerplate for a new gatherer. For a manual approach:

1. Create `pkg/gatherers/clusterconfig/gather_<name>.go` with a method on `*Gatherer` following the existing pattern (see any `gather_*.go` for reference).
2. Register it in the `gatheringFunctions` map in `pkg/gatherers/clusterconfig/clusterconfig_gatherer.go`.
3. Write a unit test in `pkg/gatherers/clusterconfig/gather_<name>_test.go`.
4. Regenerate the gathered-data documentation:
   ```bash
   make docs
   ```
   This updates `docs/gathered-data.md` from the godoc comments on your gatherer function.
5. Add an archive sample under `docs/insights-archive-sample/` if applicable.

### Running unit tests and linting

```bash
make unit   # go test -race ./...
make lint   # golangci-lint
```

### Testing a change on a cluster

**1. Build and push a custom image**

```bash
make build-container   # builds and tags the image as insights-operator locally
podman tag insights-operator quay.io/<your-user>/insights-operator:dev
podman push quay.io/<your-user>/insights-operator:dev
```

**2. Scale down the Cluster Version Operator**

The CVO will otherwise revert any manual deployment changes. Scale it down first:

```bash
oc -n openshift-cluster-version scale deployment/cluster-version-operator --replicas=0
```

**3. Patch the deployment to use your image**

```bash
oc -n openshift-insights set image deployment/insights-operator \
  insights-operator=quay.io/<your-user>/insights-operator:dev
```

**4. Trigger a data-gathering job and inspect the archive**

Create an on-demand `DataGather` CR (or wait for the periodic gather), then use `oc rsync` to pull the archive from the pod:

```bash
# Find the gather job pod
oc -n openshift-insights get pods

# Sync the archive directory locally
oc -n openshift-insights rsync <pod-name>:/var/lib/insights-operator ./archive-out
```

Inspect the `.tar.gz` archive in `./archive-out` to verify your gatherer produced the expected output.

### Integration tests

Integration tests live at https://gitlab.cee.redhat.com/ccx/insights-operator-tests — see that repo's README for local setup and run instructions.

### Commit and PR conventions

- Include a Jira or Bugzilla number in the PR title.
- Unit tests and linting must pass (CI blocks merge on failure).
- See `DoD.md` in the insights-operator repo for the full Definition of Done checklist.

## deployment-validation-operator

### Changing which checks run

DVO does not ship its own check implementations. It runs [kube-linter](https://github.com/stackrox/kube-linter) checks selected by a ConfigMap. An example is `deploy/openshift/configmap.yaml`. With no custom ConfigMap, the operator enables its built-in default set (see `ARCHITECTURE.md`).

- Enable every built-in check with `addAllBuiltIn: true`.
- Enable only a named set with `include`, and set `doNotAutoAddDefaults: true` to ignore the defaults.
- Disable named checks with `exclude`. `exclude` wins when a check appears in both `include` and `exclude`.
- Skip a namespace with the `NAMESPACE_IGNORE_PATTERN` environment variable.
- Skip one object with a kube-linter annotation: `ignore-check.kube-linter.io/<check>` or `kube-linter.io/ignore-all`.

Short notes on a few enabled checks live in `docs/checks.md` in the DVO repo.

### Running unit tests and linting

```bash
make test       # unit tests
make lint       # golangci-lint
make coverage   # coverage script used by CI
```

### Running locally

```bash
make go-build
POD_NAMESPACE="deployment-validation-operator" WATCH_NAMESPACE="" \
  NAMESPACE_IGNORE_PATTERN='^(openshift.*|kube-.*)$' \
  build/_output/bin/deployment-validation-operator \
  --kubeconfig=$HOME/.kube/config --zap-devel
curl localhost:8383/metrics
```

### Testing a change on a cluster

Manifests are under `deploy/openshift`. The default deployment sets `nodeAffinity` for `node-role.kubernetes.io/infra`. Self-managed clusters often have no infra node, so remove that affinity before installing there.

```bash
oc new-project deployment-validation-operator
for manifest in service-account.yaml \
                service.yaml \
                role.yaml \
                cluster-role.yaml \
                role-binding.yaml \
                cluster-role-binding.yaml \
                configmap.yaml \
                operator.yaml
do
    oc create -f deploy/openshift/$manifest
done
```

If the namespace is not `deployment-validation-operator`, update the commented namespace lines in `deploy/openshift/cluster-role-binding.yaml` and `deploy/openshift/role-binding.yaml` first. Deploy one replica: metrics are not shared across pods.

Changes under `deploy/openshift` need a regenerated OLM bundle:

```bash
operator-sdk generate bundle --package=deployment-validation-operator --input-dir=deploy/openshift
```

Then remove the `NodeAffinity` section from `bundle/manifests/clusterserviceversion.yaml`.

Build and push an image with `make docker-build` and `make docker-push` (`IMAGE_REGISTRY`, `QUAY_USER`, and `QUAY_TOKEN` as needed).

### Integration tests

OpenShift CI end-to-end tests live at https://gitlab.cee.redhat.com/ccx/deployment-validation-operator-tests. The DVO README also describes a local `make e2e-test` flow that needs [ginkgo](https://onsi.github.io/ginkgo/#installing-ginkgo) and a `KUBECONFIG`. That target is not in the `master` Makefile; use the GitLab suite for CI-equivalent runs.

### Commit and PR conventions

- Include a Jira or bug number in the pull request.
- Unit tests and lint must pass. Failing CI blocks merge.
- See `DoD.md` in the deployment-validation-operator repo for the Definition of Done.
