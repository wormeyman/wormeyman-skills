"""Shallow-clone every repo the signed-in `gh` account can see into one folder.

    python3 fetch_repos.py --dest /path/to/scratch/cf-sweep
    python3 fetch_repos.py --dest ... --owner some-org --owner someone-else

Owners default to the signed-in user plus every org they belong to, plus
other people's repos the user was added to as a collaborator. Writes
<dest>/repos.json (flags per repo: archived, fork, private, default branch) for
scan.py to read, and clones into <dest>/clones/<owner>__<name>.

Re-running refreshes existing clones to the current default branch, so a second
sweep never reads last week's code. It only does that inside a dest it created
itself (marked by <dest>/.cf-sweep), because refreshing means `git reset --hard`.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MARKER = ".cf-sweep"


def gh_json(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gh {' '.join(args)} failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def owners(explicit):
    if explicit:
        return explicit
    me = gh_json("api", "user")["login"]
    orgs = [o["login"] for o in gh_json("api", "user/orgs", "--paginate")]
    return [me, *orgs]


def list_repos(owner_list, collaborator):
    fields = "nameWithOwner,isArchived,isFork,isPrivate,isEmpty,defaultBranchRef,diskUsage"
    out = []
    for o in owner_list:
        for r in gh_json("repo", "list", o, "--limit", "2000", "--json", fields):
            if r["isEmpty"] or not r["defaultBranchRef"]:
                continue
            out.append({
                "repo": r["nameWithOwner"],
                "archived": r["isArchived"],
                "fork": r["isFork"],
                "private": r["isPrivate"],
                "collaborator": False,
                "branch": r["defaultBranchRef"]["name"],
                "kb": r["diskUsage"],
            })
    if collaborator:
        # Someone else's repo you were added to. Worth scanning, but a finding
        # there is theirs to act on, so scan.py marks it.
        seen = {r["repo"] for r in out}
        for r in gh_json("api", "user/repos?affiliation=collaborator&per_page=100", "--paginate"):
            if r["full_name"] in seen:
                continue
            # REST has no isEmpty, and `size` can read 0 for a tiny repo that has commits.
            if gh_json("repo", "view", r["full_name"], "--json", "isEmpty")["isEmpty"]:
                continue
            out.append({
                "repo": r["full_name"],
                "archived": r["archived"],
                "fork": r["fork"],
                "private": r["private"],
                "collaborator": True,
                "branch": r["default_branch"],
                "kb": r["size"],
            })
    return out


def sync(clones, repo):
    target = clones / repo["repo"].replace("/", "__")
    if target.exists():
        cmds = [["git", "-C", str(target), "fetch", "--quiet", "--depth", "1", "origin", repo["branch"]],
                ["git", "-C", str(target), "reset", "--quiet", "--hard", "FETCH_HEAD"]]
    else:
        cmds = [["gh", "repo", "clone", repo["repo"], str(target), "--", "--depth", "1", "--quiet"]]
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True)
        if r.returncode != 0:
            return repo["repo"], r.stderr.strip()[-300:]
    return repo["repo"], None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, type=Path)
    ap.add_argument("--owner", action="append", default=[], help="repeatable; default: you + your orgs")
    ap.add_argument("--no-collaborator", action="store_true",
                    help="skip other people's repos you are a collaborator on")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    dest = args.dest.resolve()
    if dest.exists() and any(dest.iterdir()) and not (dest / MARKER).exists():
        sys.exit(f"{dest} is not empty and was not made by this script; pick a new --dest")
    (dest / "clones").mkdir(parents=True, exist_ok=True)
    (dest / MARKER).touch()

    repos = list_repos(owners(args.owner), collaborator=not args.owner and not args.no_collaborator)
    (dest / "repos.json").write_text(json.dumps(repos, indent=1))
    per_owner = Counter("(collaborator)" if r["collaborator"] else r["repo"].split("/")[0] for r in repos)
    print(", ".join(f"{o}: {n}" for o, n in per_owner.items()), file=sys.stderr)
    print(f"{len(repos)} non-empty repos; syncing into {dest / 'clones'}", file=sys.stderr)

    failed = 0
    with ThreadPoolExecutor(args.jobs) as ex:
        for name, err in ex.map(lambda r: sync(dest / "clones", r), repos):
            if err:
                failed += 1
                print(f"FAILED {name}: {err}", file=sys.stderr)
    print(f"done: {len(repos) - failed} synced, {failed} failed", file=sys.stderr)
    sys.exit(1 if failed else 0)


main()
