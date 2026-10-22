#!/usr/bin/env python3
"""Fetch and summarise OpenShift Prow (prow.ci.openshift.org) job artifacts.

Reads the anonymously-readable `test-platform-results-public` GCS bucket, so no
`gcloud auth login` is needed. Stdlib only.

Subcommands:
  resolve <target>              build identity: job, branch, repo SHAs, result
  ls      <target> [--grep RE]  list artifact object paths
  cat     <target> <artifact>   print one artifact (relative path, as from `ls`)
  steps   <target>              per-step pass/fail from each step's finished.json
  junit   <target>              failing testcases across every JUnit XML
  history <job> [--pages N]     recent runs + flake rate for a job
  jobs    <pr>                  every job that ran on a PR, with results

Target forms (all equivalent once resolved):
  https://prow.ci.openshift.org/view/gs/<bucket>/<path>/<build-id>
  gs://<bucket>/<path>/<build-id>
  <job-name>/<build-id>

<pr> forms: https://github.com/<org>/<repo>/pull/<n> | <org>/<repo>#<n>
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BUCKET = "test-platform-results-public"
OBJ = "https://storage.googleapis.com/{bucket}/{path}"
API = "https://storage.googleapis.com/storage/v1/b/{bucket}/o"
DECK = "https://prow.ci.openshift.org"
TIMEOUT = 90


def get(url, binary=False):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"error: HTTP {e.code} for {url}")
    except urllib.error.URLError as e:
        raise SystemExit(f"error: cannot reach {url}: {e.reason}")
    return data if binary else data.decode("utf-8", "replace")


def get_opt(url, probe=False):
    """Fetch, returning None on 404 instead of exiting.

    For GCS objects only 404 means 'absent'; a 403/429/5xx is a transport
    problem and must not be reported as a missing artifact, since that turns
    into a wrong diagnosis. Deck is less disciplined — pass probe=True where
    any error legitimately means 'try the next candidate URL'.
    """
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if probe or e.code == 404:
            return None
        raise SystemExit(f"error: HTTP {e.code} for {url}")
    except urllib.error.URLError as e:
        raise SystemExit(f"error: cannot reach {url}: {e.reason}")


def obj(path):
    return OBJ.format(bucket=BUCKET, path=urllib.parse.quote(path))


# --------------------------------------------------------------------------- #
# target resolution
# --------------------------------------------------------------------------- #


def resolve_path(target):
    """Return the bucket-relative prefix of a build, ending in '/'."""
    # Browser-copied spyglass URLs carry a lens query and/or an anchor
    # (`?lens=build-log`, `#build-log`); either would end up inside the build id.
    t = target.strip().split("#", 1)[0].split("?", 1)[0].rstrip("/")

    m = re.search(r"/view/(?:gs|gcs)/([^/]+)/(.+)$", t)
    if m:
        return m.group(2) + "/"
    if t.startswith("gs://"):
        parts = t.split("/", 3)
        if len(parts) < 4 or not parts[3]:
            raise SystemExit(
                f"error: gs:// target {target!r} names a bucket but no build path"
            )
        return parts[3] + "/"
    if re.match(r"^(pr-logs|logs)/", t):
        return t + "/"

    # <job-name>/<build-id>: ask Prow's pointer file where the build lives.
    m = re.match(r"^([\w.-]+)/(\d+)$", t)
    if m:
        job, build = m.groups()
        for prefix in (f"pr-logs/directory/{job}", f"logs/{job}"):
            ptr = get_opt(obj(f"{prefix}/{build}.txt"))
            if ptr and ptr.startswith("gs://"):
                return ptr.strip().split("/", 3)[3] + "/"
        # Periodics have no pointer file; the canonical path is predictable.
        if get_opt(obj(f"logs/{job}/{build}/started.json")) is not None:
            return f"logs/{job}/{build}/"
        raise SystemExit(f"error: no build {build} found for job {job}")

    raise SystemExit(
        f"error: cannot parse target {target!r}; pass a spyglass URL, a gs:// URI, "
        "or '<job-name>/<build-id>'"
    )


def list_objects(prefix, delimiter=None):
    """Full paginated object listing under prefix."""
    names, prefixes, token = [], [], None
    while True:
        q = {"prefix": prefix, "maxResults": "1000"}
        if delimiter:
            q["delimiter"] = delimiter
        if token:
            q["pageToken"] = token
        d = json.loads(get(API.format(bucket=BUCKET) + "?" + urllib.parse.urlencode(q)))
        if "error" in d:
            raise SystemExit("error: " + d["error"]["message"])
        names += [i["name"] for i in d.get("items", [])]
        prefixes += d.get("prefixes", [])
        token = d.get("nextPageToken")
        if not token:
            break
    return names, prefixes


def build_info(prefix):
    job, build = prefix.rstrip("/").rsplit("/", 2)[-2:]
    info = {
        "job": job,
        "build_id": build,
        "gcs_path": prefix,
        "spyglass": f"{DECK}/view/gs/{BUCKET}/{prefix.rstrip('/')}",
        "kind": "periodic" if prefix.startswith("logs/") else "presubmit",
    }

    finished = get_opt(obj(prefix + "finished.json"))
    if finished:
        f = json.loads(finished)
        info["result"] = f.get("result")
        info["passed"] = f.get("passed")
        info["finished_at"] = f.get("timestamp")
    else:
        info["result"] = "RUNNING (no finished.json)"

    started = get_opt(obj(prefix + "started.json"))
    if started:
        info["started_at"] = json.loads(started).get("timestamp")

    clones = get_opt(obj(prefix + "clone-records.json"))
    if clones:
        info["repos"] = [
            {
                "repo": f"{r['refs']['org']}/{r['refs']['repo']}",
                "branch": r["refs"].get("base_ref"),
                "base_sha": r["refs"].get("base_sha"),
                "pulls": [
                    {"number": p.get("number"), "sha": p.get("sha")}
                    for p in (r["refs"].get("pulls") or [])
                ],
                "clone_failed": r.get("failed"),
            }
            for r in json.loads(clones)
            if r.get("refs", {}).get("repo")
        ]
    # The branch is also encoded in the job name: ...-<repo>-<branch>-<test>.
    m = re.search(r"-(master|main|release-[\d.]+|stage|enterprise-[\d.]+)-", job)
    if m:
        info["branch_from_job_name"] = m.group(1)
    return info


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #


def cmd_resolve(args):
    print(json.dumps(build_info(resolve_path(args.target)), indent=2))


def cmd_ls(args):
    prefix = resolve_path(args.target)
    names, _ = list_objects(prefix)
    rel = [n[len(prefix):] for n in names]
    if args.grep:
        rx = re.compile(args.grep)
        rel = [r for r in rel if rx.search(r)]
    print("\n".join(rel))
    print(f"\n# {len(rel)} object(s) under gs://{BUCKET}/{prefix}", file=sys.stderr)


def cmd_cat(args):
    prefix = resolve_path(args.target)
    body = get_opt(obj(prefix + args.artifact.lstrip("/")))
    if body is None:
        raise SystemExit(
            f"error: no such artifact {args.artifact!r}; run `ls` to see what exists"
        )
    sys.stdout.write(body)


# A step that never got to run is not a failing step: on an aborted or
# timed-out build most steps end up here, and marking them FAIL points the
# investigation at an arbitrary one of them.
OK_RESULTS = ("SUCCESS", "PASSED")
NOT_RUN_RESULTS = ("ABORTED", "SKIPPED", "CANCELLED", "CANCELED")


def cmd_steps(args):
    prefix = resolve_path(args.target)
    names, _ = list_objects(prefix + "artifacts/")
    finals = sorted(n for n in names if n.endswith("/finished.json"))
    if not finals:
        print("no per-step finished.json found (job may have failed before steps ran)")
        return
    not_run = 0
    for n in finals:
        step = n[len(prefix) + len("artifacts/"):-len("/finished.json")]
        try:
            res = json.loads(get(obj(n))).get("result", "?")
        except json.JSONDecodeError:
            res = "?"
        if res in OK_RESULTS:
            mark = "ok  "
        elif res in NOT_RUN_RESULTS:
            mark = "--  "
            not_run += 1
        else:
            mark = "FAIL"
        print(f"{mark}  {res:<8} {step}")
    if not_run:
        print(
            f"\n# {not_run} step(s) marked '--' never completed (aborted/skipped);"
            " they are not the failure",
            file=sys.stderr,
        )


JUNIT_RX = re.compile(r"(junit.*\.xml|.*-report\.xml|.*_report\.xml)$", re.I)


def cmd_junit(args):
    prefix = resolve_path(args.target)
    names, _ = list_objects(prefix)
    reports = [n for n in names if JUNIT_RX.search(n.rsplit("/", 1)[-1])]
    if not reports:
        print("no JUnit XML artifacts found")
        return
    total = 0
    for n in reports:
        rel = n[len(prefix):]
        try:
            root = ET.fromstring(get(obj(n), binary=True))
        except ET.ParseError as e:
            print(f"## {rel}\n  (unparseable: {e})\n")
            continue
        bad = []
        for tc in root.iter("testcase"):
            for kind in ("failure", "error"):
                node = tc.find(kind)
                if node is not None:
                    bad.append((kind, tc, node))
        if not bad:
            continue
        print(f"## {rel}  ({len(bad)} failing)")
        for kind, tc, node in bad:
            total += 1
            cls = tc.get("classname") or ""
            print(f"\n  [{kind.upper()}] {cls}::{tc.get('name')}")
            msg = (node.get("message") or "").strip()
            if msg:
                for line in msg.splitlines()[: args.lines]:
                    print(f"      {line}")
            body = (node.text or "").strip()
            if body:
                print("      --- detail ---")
                for line in body.splitlines()[: args.lines]:
                    print(f"      {line}")
        print()
    print(f"# {total} failing testcase(s) across {len(reports)} report(s)")


def fetch_history(job, pages):
    """Yield build dicts from Prow's job-history pages (public, no auth)."""
    for base in ("pr-logs/directory", "logs"):
        url = f"{DECK}/job-history/gs/test-platform-results/{base}/{job}"
        builds, seen_page = [], 0
        while url and seen_page < pages:
            # Deck answers 500, not 404, for a history path a job does not use
            # (every periodic under pr-logs/directory), so any error means
            # "wrong base, try the next one".
            html = get_opt(url, probe=True)
            if html is None:
                break
            m = re.search(r"allBuilds = (\[.*?\]);", html, re.S)
            if not m:
                break
            page = json.loads(m.group(1))
            builds += page
            seen_page += 1
            nxt = re.findall(r'href="(/job-history/[^"]*\?buildId=[^"]*)"', html)
            url = DECK + nxt[-1] if nxt and seen_page < pages else None
        if builds:
            return builds
    return []


MIN_DECIDED = 5  # below this a failure ratio says nothing useful


def cmd_history(args):
    builds = fetch_history(args.job, args.pages)
    if not builds:
        raise SystemExit(f"error: no history for job {args.job!r} (check the job name)")
    counts = {}
    for b in builds:
        counts[b["Result"]] = counts.get(b["Result"], 0) + 1
    decided = counts.get("SUCCESS", 0) + counts.get("FAILURE", 0)
    print(f"job:     {args.job}")
    print(f"runs:    {len(builds)}  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if decided:
        rate = 100.0 * counts.get("FAILURE", 0) / decided
        line = f"failure: {counts.get('FAILURE', 0)}/{decided} decided runs = {rate:.0f}%"
        if decided < MIN_DECIDED:
            # One failed run is 100%; that is not a regression signal.
            print(f"{line}  -> too few decided runs for a verdict (want {MIN_DECIDED}, try --pages)")
        else:
            verdict = (
                "PERSISTENT REGRESSION" if rate >= 90
                else "FLAKE" if rate > 0
                else "HEALTHY"
            )
            print(f"{line}  -> likely {verdict}")
    print()
    for b in builds:
        # Periodics carry no Refs at all; presubmits carry pulls.
        refs = b.get("Refs") or {}
        pulls = refs.get("pulls") or []
        pr = f"PR#{pulls[0]['number']}" if pulls else (refs.get("base_ref") or "-")
        sha = (refs.get("base_sha") or "")[:9]
        # Presubmit runs of one PR share a base SHA across pushes, so the head
        # sha is what says whether two runs tested the same tree.
        head = (pulls[0].get("sha") or "")[:9] if pulls else ""
        line = f"{b['Result']:<8} {b['ID']}  {b['Started'][:16]}  {pr:<10} base={sha or '-'}"
        print(f"{line}  head={head}" if head else line)


def cmd_jobs(args):
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", args.pr) or re.match(
        r"^([^/]+)/([^#]+)#(\d+)$", args.pr
    )
    if not m:
        raise SystemExit("error: expected a GitHub PR URL or '<org>/<repo>#<number>'")
    org, repo, num = m.groups()
    prefix = f"pr-logs/pull/{org}_{repo}/{num}/"
    _, job_prefixes = list_objects(prefix, delimiter="/")
    if not job_prefixes:
        raise SystemExit(f"error: no CI runs found under gs://{BUCKET}/{prefix}")
    for jp in job_prefixes:
        job = jp[len(prefix):].rstrip("/")
        _, build_prefixes = list_objects(jp, delimiter="/")
        for bp in sorted(build_prefixes):
            build = bp[len(jp):].rstrip("/")
            if not build.isdigit():
                continue
            fin = get_opt(obj(bp + "finished.json"))
            res = json.loads(fin).get("result") if fin else "RUNNING"
            mark = "FAIL" if res == "FAILURE" else "    "
            print(f"{mark}  {res:<8} {job}/{build}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_target(name, fn, **kw):
        s = sub.add_parser(name, **kw)
        s.add_argument("target")
        s.set_defaults(func=fn)
        return s

    with_target("resolve", cmd_resolve, help="build identity, branch and commit SHAs")
    s = with_target("ls", cmd_ls, help="list artifacts")
    s.add_argument("--grep", help="only paths matching this regex")
    s = with_target("cat", cmd_cat, help="print one artifact")
    s.add_argument("artifact")
    with_target("steps", cmd_steps, help="per-step pass/fail")
    s = with_target("junit", cmd_junit, help="failing testcases from JUnit XML")
    s.add_argument("--lines", type=int, default=25, help="max lines per message (default 25)")

    s = sub.add_parser("history", help="recent runs and flake rate")
    s.add_argument("job")
    s.add_argument("--pages", type=int, default=2, help="history pages, 20 runs each (default 2)")
    s.set_defaults(func=cmd_history)

    s = sub.add_parser("jobs", help="all jobs that ran on a PR")
    s.add_argument("pr")
    s.set_defaults(func=cmd_jobs)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Downstream `head`/`less` closed the pipe; that is not an error.
        # Redirect stdout so the interpreter's shutdown flush cannot re-raise.
        import os

        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
