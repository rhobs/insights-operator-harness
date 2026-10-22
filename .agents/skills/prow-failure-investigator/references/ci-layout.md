# OpenShift CI layout for the Insights Operator ecosystem

Everything below was verified against live infrastructure on 2026-10-16. Where an
endpoint is known to be unavailable, that is recorded too — don't retry it.

## Data sources: what works anonymously

| Source | URL | Works without auth? |
|---|---|---|
| **Public artifact bucket** | `https://storage.googleapis.com/test-platform-results-public/<path>` | **Yes** — read *and* list |
| Public bucket JSON list API | `https://storage.googleapis.com/storage/v1/b/test-platform-results-public/o?prefix=…&delimiter=/` | **Yes** |
| Prow job history | `https://prow.ci.openshift.org/job-history/gs/test-platform-results/{pr-logs/directory,logs}/<job>` | **Yes** (HTML with an embedded `allBuilds = [...]` JSON array) |
| Sippy | `https://sippy.dptools.openshift.org/api/{releases,jobs,jobs/runs}` | **Yes** (`release=` is a required param on most endpoints) |
| `test-platform-results` (private bucket) | `storage.googleapis.com/test-platform-results/…` | **No** — 403 anonymous, both get and list |
| gcsweb | `gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com` → `gcs.ci.openshift.org` | **No** — now just 303s to the GCS web console |
| `prow.ci.openshift.org/log?job=…&id=…` | | **No** — 404 |
| Spyglass page HTML | `prow.ci.openshift.org/view/gs/…` | Loads, but it's a JS shell; artifacts come from POSTs to `/spyglass/lens/*`. Not scriptable — use the bucket. |
| `gsutil` / `gcloud storage` | `gs://test-platform-results/…` | Only after `gcloud auth login`; credentials in this workspace were expired. Not needed — use the public bucket. |

**Key point:** spyglass URLs usually name the *private* `test-platform-results`
bucket, but the same object path exists in `test-platform-results-public`. Swap
the bucket name and fetch anonymously. `scripts/prowjob.py` does this for you.

## Build artifact layout

A build lives at one of:

```
pr-logs/pull/<org>_<repo>/<pr-number>/<job-name>/<build-id>/   # presubmit
logs/<job-name>/<build-id>/                                    # periodic
```

Given a job name and build ID, the pointer file resolves the full path:

```
pr-logs/directory/<job-name>/<build-id>.txt   # contains the gs:// URI
```

Inside a build:

| Path | What it gives you |
|---|---|
| `started.json` | start timestamp, `repos` map |
| `finished.json` | `result` (`SUCCESS`/`FAILURE`/`ABORTED`), `passed`, `revision`. **Absent while the job is still running.** |
| `prowjob.json` | full ProwJob spec incl. the ci-operator config used |
| `clone-records.json` | **the commit trace** — per repo: `base_ref` (branch), `base_sha`, and each PR's `sha` |
| `build-log.txt` | top-level ci-operator log |
| `artifacts/ci-operator.log` | ci-operator's own log; step scheduling, timeouts |
| `artifacts/ci-operator-step-graph.json` | step dependency graph and per-step durations |
| `artifacts/junit_operator.xml` | ci-operator's JUnit — which multi-stage *step* failed |
| `artifacts/<test-name>/<step>/build-log.txt` | per-step stdout |
| `artifacts/<test-name>/<step>/finished.json` | per-step `result` — fastest way to find the failing step |
| `artifacts/<test-name>/test/artifacts/test-report.xml` | **the pytest suite's JUnit** — the actual failing test names |
| `artifacts/<test-name>/gather-extra/artifacts/` | cluster dump: `clusteroperators.json`, `pods.json`, `events.json`, audit logs |
| `artifacts/<test-name>/gather-must-gather/` | must-gather tarball and `junit_install.xml` |

A single e2e build holds ~8000 objects, so always list with pagination
(`nextPageToken`) and filter — `prowjob.py ls --grep` handles this.

## Branch naming — do not assume

Three different conventions are in play — this is the single most common source
of a wrong checkout.

| Repo | Default branch | Release branches |
|---|---|---|
| `openshift/insights-operator` | **`master`** (not `main`) | `release-4.12` … `release-4.23`, `release-5.0`, `release-5.1`, `release-5.2`, plus `stage` |
| `openshift/insights-runtime-extractor` | **`main`** | `release-4.18` … `release-4.23`, `release-5.0`, `release-5.1`, `release-5.2` |
| `ccx/insights-operator-tests` (GitLab) | `master` | **bare numeric: `4.7` … `4.22`, `5.0`** — no `release-` prefix |
| `ccx/ccx-ocp-testlib` (GitLab) | `master` | no numeric release branches; feature branches only |
| `app-sre/deployment-validation-operator` | `master` | — (not in OpenShift CI) |
| this harness | `main` | none — the harness has no release branches |

So one OCP release spans two spellings: a `release-4.21` job runs tests from
branch `4.21`. Translate when crossing between them. No repo here uses an
`enterprise-*` prefix; if a user says `enterprise-4.22`, confirm what they mean
rather than guessing.

The branch is encoded in the job name:
`pull-ci-openshift-insights-operator-<branch>-<test>` and
`periodic-ci-openshift-insights-operator-<branch>-<test>`. Confirm it against
`clone-records.json[].refs.base_ref` rather than trusting the name alone.

A user may say `4.21` or `enterprise-4.22`; map those to the real refs above
(`release-4.21`) before checking anything out, and say so if no such branch exists.

## Job names

Presubmits on `insights-operator` master (from the ci-operator config):

```
lint  unit  verify-deps  e2e  e2e-agnostic-upgrade
insights-operator-e2e-tests      # pytest suite, -k "not serial and not periodic_only and not slow"
insights-operator-serial-tests
insights-operator-slow-tests
insights-runtime-extractor-tests
tls-scanner  e2e-metal-ipi-ovn-ipv6  publish-coverage
```

Full job name = `pull-ci-openshift-<repo>-<branch>-<test-as>`.

Authoritative config:
- `https://github.com/openshift/release/tree/main/ci-operator/config/openshift/insights-operator`
  (`openshift-insights-operator-<branch>.yaml`, `…__periodics.yaml`, `…__okd-scos.yaml`)
- same under `.../openshift/insights-runtime-extractor`

Fetch raw with
`curl -s https://raw.githubusercontent.com/openshift/release/main/ci-operator/config/openshift/insights-operator/openshift-insights-operator-<branch>.yaml`.

## The e2e test suite is NOT in this harness

`insights-operator-e2e-tests`, `-serial-tests` and `-slow-tests` all run pytest
from **`gitlab.cee.redhat.com/ccx/insights-operator-tests`**, pulled in as the
ci-operator base image `ci/insights-operator-tests:latest`. Its helper library
`ccx_ocp_testlib` — which appears all over the tracebacks — is a second private
repo, `gitlab.cee.redhat.com/ccx/ccx-ocp-testlib`.

Both are private, so neither can be a submodule of this harness — they must be
cloned manually. The working setup keeps them beside the submodules:

```
projects/insights-operator-tests/   # ccx/insights-operator-tests
projects/ccx-ocp-testlib/           # ccx/ccx-ocp-testlib
```

Both paths are in `.gitignore`: the harness pushes to a public GitHub remote, so
private test code must never be committed into it. `git status` stays clean.

Confirm both are present before relying on them — a clone can be absent or on an
unexpected branch:

```bash
for d in projects/insights-operator-tests projects/ccx-ocp-testlib; do
  [ -d "$d/.git" ] || { echo "$d MISSING"; continue; }
  echo "$d $(git -C "$d" rev-parse --abbrev-ref HEAD) $(git -C "$d" remote | tr '\n' ' ')"
done
```

Three consequences that drive triage:

1. **gitlab.cee.redhat.com needs the Red Hat VPN** and did not resolve from this
   workspace, so `git fetch` against it may fail even when a clone exists. Work
   from what the local clone already has, and say when it may be stale rather
   than silently reasoning from an old checkout.
2. **The ci-operator base image tag is `latest` on *every* branch** — `master`,
   `release-5.0`, `release-4.21`, all of them, verified in the openshift/release
   configs. The job does not pin a test-suite branch. So a change to the test
   repo can break several release branches at once with zero commits in
   `insights-operator`. If failures start across branches at the same time and no
   operator commit lines up, suspect the test image, not the operator.
3. The test repo's own release branches are bare numeric (`4.21`, `5.0`), and
   stop at `4.22` / `5.0` while the operator already has `release-5.2` — so the
   newer branches are not mirrored. **`:latest` is built from `master`, not from
   the matching release branch** — demonstrated by the 4.17 ReportPortal
   breakage: `pytest-reportportal` was dropped from `master` on 2026-04-17
   (`4c6249e`) and the `release-4.17` jobs began failing with
   `unrecognized arguments: --rp_enabled` on 2026-05-11, a month *before* the
   same removal reached the `4.17` branch (`d7ea739`, 2026-06-04). Had the image
   tracked `4.17`, the plugin would still have been present. So read `master`
   first; a numeric branch tells you what that branch's source says, not what CI
   ran. Say which you used.

### Mapping a failing test back to source

Test IDs in `test-report.xml` are dotted module paths — swap dots for slashes:

```
tests.data_downloaded.resource_gatherers.test_secrets::test_gather_support_secret
  -> tests/data_downloaded/resource_gatherers/test_secrets.py
```

Worked example, verified end to end on build 2110339285080084480:

| Step | Evidence |
|---|---|
| JUnit failure | `test_gather_support_secret` — `AssertionError: support secret was not gathered` |
| Test source | `tests/data_downloaded/resource_gatherers/test_secrets.py:30`, asserting `archive.find_files("config/secrets/openshift-config/support/data.json")` |
| Operator source | `pkg/gatherers/clusterconfig/gather_support_secret.go:51`, which writes record `config/secrets/openshift-config/support/data` |

The archive path in the assertion is the join between the two repos — grep it in
the operator to find the gatherer that was supposed to produce it.

## Gatherer failures map into the operator

A failing gatherer test names the archive path it expected, e.g.
`config/secrets/openshift-config/support/data.json`. Grep that path (minus the
`.json`) in the submodule to land on the producing gatherer:

```bash
grep -rn --include='*.go' "config/secrets/openshift-config/support" \
    projects/insights-operator/pkg/gatherers/
# -> pkg/gatherers/clusterconfig/gather_support_secret.go:51
```

Quote the `--include` glob; zsh expands it otherwise and the grep fails.

Gatherers live under `projects/insights-operator/pkg/gatherers/{clusterconfig,
conditional,workloads,common}/`. The archive layout is documented in
`projects/insights-operator/docs/gathered-data.md`, with a worked example tree in
`projects/insights-operator/docs/insights-archive-sample/`.
