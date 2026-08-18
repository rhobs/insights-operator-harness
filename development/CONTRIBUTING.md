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
