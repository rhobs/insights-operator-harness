---
name: prow-failure-investigator
description: Investigate a failed OpenShift Prow CI job for the Insights Operator ecosystem. Use when given a Prow/spyglass job URL, a build ID, or a PR link and asked why CI failed, whether a failure is a flake or a real regression, which commit broke a job, or whether a fix needs backporting to a release branch. Fetches build logs, finished.json, step logs and JUnit results, computes the flake rate from job history, aligns the harness and operator submodules to the branch under test, and traces the failure into gatherer code.
user_invocable: true
---

# Prow failure investigator

Triage a failed OpenShift CI job for `insights-operator` /
`insights-runtime-extractor` end to end: fetch the artifacts, decide flake vs.
regression, find the suspect commit, trace it into the operator source, and
propose a fix or a backport.

`references/ci-layout.md` holds the verified CI topology — bucket paths,
artifact layout, branch names per repo, job names, and which endpoints are dead.
**Read it before improvising any URL**; several plausible-looking Prow endpoints
(gcsweb, `/log?job=`, the private bucket) are 403/404 and will waste turns.

## Tooling

`scripts/prowjob.py` reads the anonymously-public `test-platform-results-public`
bucket. Stdlib only, no auth, no `gcloud login`.

```bash
S=.agents/skills/prow-failure-investigator/scripts/prowjob.py

python3 -I $S resolve <target>            # job, branch, base_sha, PR sha, result
python3 -I $S steps   <target>            # per-step pass/fail -> the failing step
python3 -I $S junit   <target>            # failing testcases + stack traces
python3 -I $S ls      <target> --grep RE  # find artifacts (a build has ~8000)
python3 -I $S cat     <target> <path>     # print one artifact
python3 -I $S history <job> --pages 3     # runs + flake rate (20 runs/page)
python3 -I $S jobs    <pr-url>            # every job on a PR, with results
```

`<target>` is a spyglass URL, a `gs://` URI, or `<job-name>/<build-id>`.
Spyglass URLs naming the private bucket are fine — the script re-points them at
the public one.

Run it with `python3 -I` so the current directory is kept off `sys.path`.

Two **private GitLab repos cannot be submodules here** and live as gitignored
clones under `projects/`. Check they are present and note their branch and
remote name:

```bash
for d in projects/insights-operator-tests projects/ccx-ocp-testlib; do
  [ -d "$d/.git" ] || { echo "$d MISSING"; continue; }
  echo "$d $(git -C "$d" rev-parse --abbrev-ref HEAD) $(git -C "$d" remote | tr '\n' ' ')"
done
# projects/insights-operator-tests master origin
# projects/ccx-ocp-testlib         master origin upstream
```

The remote name matters for the fetch commands in stage 5 — `origin` on a direct
clone, `upstream` on a personal fork. A `MISSING` line means degrade per stage 5
— do not invent test source.

## Workflow

Work through these in order. Report as you go rather than saving everything for
the end — the branch and flake verdict are useful before the root cause lands.

### 1. Input and workspace setup

- Resolve the target: `resolve` for a job URL or build ID; `jobs <pr-url>` first
  if given a PR, then pick the `FAIL` rows.
- Record `job`, `build_id`, `result`, and from `repos[]`: the repo, `branch`
  (`base_ref`), `base_sha`, and the PR head `sha`. This is the commit trace.
- `git submodule status` in the harness. A leading `+` means the checkout does
  not match the recorded pointer — note it, it changes what local greps mean.
- Check the private test clones under `projects/` (snippet above). Do this up
  front: if they are missing, stage 5 is limited and the user should know early.

### 2. Branch and submodule alignment

- Take the branch from `clone-records.json` (`repos[].branch`), not from the job
  name alone.
- **Three naming conventions are in play** — translate, don't assume:

  | repo | this release | default |
  |---|---|---|
  | `insights-operator` | `release-4.21` | `master` |
  | `insights-runtime-extractor` | `release-4.21` | `main` |
  | `insights-operator-tests` | `4.21` (bare) | `master` |

  A `release-4.21` job runs tests from branch `4.21`. No repo uses an
  `enterprise-*` prefix — if the user says that, ask what they mean. If a
  requested branch does not exist, say so instead of guessing.
- The harness itself has only `main` — there is nothing to check out per release.
  Align the submodule of **the repo the job actually built**, which is
  `repos[].repo` from `resolve` — not the operator by default:

  | `repos[].repo` | submodule | default branch |
  |---|---|---|
  | `openshift/insights-operator` | `projects/insights-operator` | `master` |
  | `openshift/insights-runtime-extractor` | `projects/insights-runtime-extractor` | `main` |

  ```bash
  R=projects/<submodule-from-the-table>
  [ -e "$R/.git" ] || echo "$R not initialised"   # then: git submodule update --init -- $R
  ```

  An extractor `base_sha` does not exist in the operator repo, so pointing these
  commands at the wrong submodule fails outright or, worse, greps an unrelated
  tree. If `repos[]` lists more than one repo, the one under test carries
  `pulls[]` on a presubmit and otherwise matches the repo in the job name. If its
  submodule cannot be initialised, say the source is unavailable and reason from
  the artifacts — do not fall back to another repo's tree.

  ```bash
  # periodic / postsubmit: base_sha is the whole story
  git -C "$R" fetch origin <branch>
  git -C "$R" checkout <base_sha>   # the exact CI commit
  ```

  Checking out `base_sha` directly is better than the branch tip: it reproduces
  what CI actually compiled.

  **On a presubmit that is only half the tree.** Prow checks out `base_sha` and
  then merges the PR head, so `base_sha` alone is the branch *without* the change
  under test — grepping it will not show the code that failed. Replay both hops:

  ```bash
  git -C "$R" fetch origin <branch> pull/<pr-number>/head
  git -C "$R" checkout <base_sha>
  git -C "$R" merge --no-edit <pull-sha>   # repos[].pulls[].sha
  ```

  A merge conflict here is itself a finding — CI hit the same one. Leave the
  submodule detached and **tell the user you moved it**, with the command to
  restore: `git submodule update --init --recursive`.
- If the user asked for a plain refresh instead, that same command restores every
  submodule to the harness-recorded pointers.

### 3. Job history and flake assessment

```bash
python3 -I $S history <job-name> --pages 3
```

Classify from the pass/fail ratio *and* the `base=` / `head=` columns:

- **Flake** — failures interleaved with successes on the same or nearby base
  SHAs. The script's heuristic verdict is a starting point only; confirm by
  checking whether a *passing* run exists at the same commit as a failing one.
  That is the strongest flake evidence there is — but on a presubmit the commit
  is `base` **and** `head` together. Two runs of one PR share a base SHA while
  testing different pushes, so a pass and a fail at the same `base=` prove
  nothing; it is a retest of the same `head=` that does.
- **Persistent regression** — every run fails from one base SHA onward. Name the
  first failing build and the base SHA it introduced.
- **Infrastructure** — the failing step is a `gather-*`, `ipi-install-*` or
  `ipi-deprovision-*` step rather than `test`. Treat as infra, not product.

Run `history` on the same test for a *sibling branch* too when deciding scope. If
a failure starts on several branches at once with no operator commit in common,
suspect the shared `ci/insights-operator-tests:latest` image — it is the same tag
on every branch (see `references/ci-layout.md`).

### 4. Failure diagnosis and commit trace

1. `steps <target>` → the failing step. If it is not `test`, the product may be
   innocent. Steps marked `--` were aborted or skipped — on a timed-out build
   most steps look like that; they are collateral, not the cause.
2. `junit <target>` → failing testcase names and stack traces.
3. Step log for timeouts and the surrounding context:
   `cat <target> artifacts/<test-name>/test/build-log.txt | tail -200`.
   For scheduling or step-timeout questions use `artifacts/ci-operator.log`.
4. Correlate with commits in the failure window:

   ```bash
   git -C "$R" log --oneline -n 10 <base_sha>   # $R from stage 2
   git log --oneline -n 10                      # harness itself
   git log -n 5 -p -- "$R"                      # submodule pointer moves
   ```

   The harness pointer and CI are independent: CI clones the branch tip, it does
   not read this harness. A mismatch between `git submodule status` and CI's
   `base_sha` explains "works locally, fails in CI" and is worth stating, but it
   is not itself the regression.

### 5. Codebase cross-reference

The pytest suites (`insights-operator-e2e-tests`, `-serial-tests`,
`-slow-tests`) live in the private `ccx/insights-operator-tests`, with helpers in
`ccx/ccx-ocp-testlib`. Use the clones found in stage 1; both are outside the
harness. If either is `MISSING`, say the test source is unavailable and reason
from the JUnit traceback plus the operator side — **do not invent test file
contents**. The same applies to a clone you cannot fetch: gitlab.cee needs VPN,
so flag a possibly-stale checkout rather than treating it as current.

Go and Rust test failures (`unit`, `e2e`, `rust-unit-tests`) map straight into
`$R` instead.

**The trace has three hops.** Follow all of them before naming a root cause:

1. **JUnit ID → test file.** Dots become slashes:
   `tests.data_downloaded.resource_gatherers.test_secrets::test_gather_support_secret`
   → `tests/data_downloaded/resource_gatherers/test_secrets.py`.
2. **Test file → the archive path it asserts on.** That string is the contract
   between the suite and the operator.
3. **Archive path → the gatherer that writes it:**

   ```bash
   grep -rn --include='*.go' "config/secrets/openshift-config/support" \
       projects/insights-operator/pkg/gatherers/
   # -> pkg/gatherers/clusterconfig/gather_support_secret.go:51
   ```

   Quote the `--include` glob — zsh expands it otherwise and the grep fails.

If the traceback dies inside `ccx_ocp_testlib.*` rather than in an assertion, the
bug is likely in the helper library or the cluster state, not in the operator.
Check the testlib clone before blaming product code.

Check whether a fix already exists upstream before writing one. Do this in
**whichever repo owns the bug**, product repo or tests:

```bash
# repo under test ($R from stage 2; default branch is master for the operator,
# main for the extractor)
git -C "$R" log --oneline origin/<default-branch> -n 20 -- <file>
git -C "$R" branch -r --contains <fix-sha>

# tests repo (branches are bare numeric; $REMOTE is the one noted in stage 1 —
# `upstream` on a personal fork, `origin` on a direct clone)
git -C "$TESTS" log --oneline "$REMOTE/master" -n 20 -- <file>
git -C "$TESTS" branch -r --contains <fix-sha>
```

A commit present on the default branch but absent from the release branch is a missing
backport — that is the finding, and the fix is a cherry-pick, not new code.

### 6. Output

Report in this shape, and keep it tight:

```
## Target
job / build / branch / result / spyglass link
repo under test: <org/repo> @ <base_sha>  (+ PR head sha if presubmit)

## Flake status
N runs: X pass / Y fail  ->  Flake | Persistent regression | Infrastructure
evidence: (passing run at the same commit — base, plus head on a presubmit |
           first failing build + SHA)

## Failure
failing step: <step>
failing tests: <names>
<the few lines of traceback that matter>

## Suspect commits
<sha> <subject>   — why it correlates (or: none correlate, and what that implies)
submodule pointer: harness <sha> vs CI <base_sha>  (note only if they differ)

## Root cause and fix
owning repo: insights-operator | insights-operator-tests | ccx-ocp-testlib | infra
file:line on each hop of the trace that you actually verified
concrete patch, or: cherry-pick <sha> onto <branch>, or: no code fix — flake
```

Name the owning repo explicitly. "The gatherer is broken" and "the test asserts
the wrong path" lead to patches in different repos with different review paths,
and the test repos are private — the user may need to act on them separately.

## Rules

- Distinguish what you verified from what you inferred. "The archive path is
  never written because X" needs a file:line; otherwise call it a hypothesis.
- Do not call something a flake on ratio alone when every failure sits on or
  after one commit — that is a regression with retries. On a presubmit compare
  `base=` and `head=` together; a shared base alone does not make two runs
  comparable.
- Do not push, open PRs, or move submodule pointers in a commit. Propose patches;
  let the user apply them.
- If the job is still running there is no `finished.json`; say so rather than
  reporting a missing-artifact error as a failure.
