#!/usr/bin/env bash
# co-change.sh - rank file pairs that change together in git history.
#
# Answers the one question that decides every DRY call: "would these change
# together?" Similar-LOOKING code that never co-changes is parallel evolution -
# collapsing it couples things that want to move apart. Code that co-changes is
# shared knowledge, whether or not it looks alike.
#
# Usage:
#   co-change.sh [repo] [since] [min-support] [path-filter]
#
#   repo         path to git repo            (default: .)
#   since        git --since window          (default: 12 months ago)
#   min-support  min shared commits to print (default: 3)
#   path-filter  egrep pattern files must match, e.g. '^src/' (default: all)
#
# Examples:
#   co-change.sh                                  # last 12 months, whole repo
#   co-change.sh . "3 years ago" 5 '^src/'        # deeper history, src only
#   co-change.sh ~/code/app "6 months ago" 2      # short window, small repo
#
# Output columns:
#   SUPPORT  commits touching both files
#   JACCARD  support / (commitsA + commitsB - support). Normalized 0..1, so a
#            hot file paired with everything does not dominate the ranking.
#   A, B     the file pair
#
# Reading it: high support AND high jaccard = shared knowledge, look here first.
# High support but LOW jaccard = one file is just busy; probably coincidence.
# Low support = they evolve independently; leave them alone even if they look
# like twins.
#
# Caveats worth knowing before you trust a number:
#   - Renames break the trail. This uses raw --name-only, so a file renamed
#     mid-window looks like two different files with split history. Confirm a
#     surprising pair with: git log --follow -- <path>
#   - Deleted files still appear. Check the pair still exists before acting.
#   - Bulk commits are excluded (see MAX_FILES) because a 300-file formatting
#     sweep would otherwise couple everything to everything.
#   - Merge commits are excluded; they would double-count the branch's work.
#   - A young repo cannot answer this. Under ~50 commits in the window, treat
#     the output as a hint and fall back to reading the code.

set -euo pipefail

REPO="${1:-.}"
SINCE="${2:-12 months ago}"
MIN_SUPPORT="${3:-3}"
PATH_FILTER="${4:-}"

# Commits touching more than this many files are structural (mass rename,
# formatting, dependency bump) and say nothing about which code shares meaning.
MAX_FILES="${MAX_FILES:-25}"
TOP="${TOP:-30}"

# Some file pairs are coupled MECHANICALLY - a lockfile always moves with its
# manifest, a snapshot always moves with the code that generates it. They rank
# at the top and mean nothing about shared knowledge, so they are excluded by
# default. Override with EXCLUDE='' to see everything.
EXCLUDE="${EXCLUDE:-(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock|poetry\.lock|go\.sum|\.verified\.|__snapshots__|\.snap$|baseline\.json|/dist/|/build/|\.min\.)}"

if ! git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: '$REPO' is not a git repository" >&2
  exit 1
fi

total_commits=$(git -C "$REPO" log --since="$SINCE" --no-merges --format=%H | wc -l | tr -d ' ')
echo "# repo:    $(cd "$REPO" && pwd)"
echo "# window:  since $SINCE  ($total_commits non-merge commits)"
echo "# filter:  ${PATH_FILTER:-<none>}   min-support: $MIN_SUPPORT   max-files/commit: $MAX_FILES"
echo "# excluded: ${EXCLUDE:-<none>}"
echo

if [ "$total_commits" -lt 50 ]; then
  echo "# WARNING: only $total_commits commits in this window. Co-change needs"
  echo "#          history to be meaningful - widen --since or read the code instead."
  echo
fi

git -C "$REPO" log --since="$SINCE" --no-merges --format='format:@@C@@' --name-only \
| awk -v minsup="$MIN_SUPPORT" -v maxf="$MAX_FILES" -v filter="$PATH_FILTER" -v excl="$EXCLUDE" '
function flush(   i, j, a, b, key) {
    if (n >= 2 && n <= maxf) {
        for (i = 1; i < n; i++) {
            for (j = i + 1; j <= n; j++) {
                a = f[i]; b = f[j]
                key = (a < b) ? a SUBSEP b : b SUBSEP a
                pair[key]++
            }
        }
    }
    # File totals count every commit the file appears in, including bulk ones,
    # so jaccard denominators stay honest.
    for (i = 1; i <= n; i++) cnt[f[i]]++
    n = 0
    delete seen
}
/^@@C@@$/ { flush(); next }
/^$/      { next }
{
    if (filter != "" && $0 !~ filter) next
    if (excl != "" && $0 ~ excl) next     # mechanically-coupled noise
    if ($0 in seen) next          # same path twice in one commit
    seen[$0] = 1
    f[++n] = $0
}
END {
    flush()
    for (key in pair) {
        s = pair[key]
        if (s < minsup) continue
        split(key, p, SUBSEP)
        denom = cnt[p[1]] + cnt[p[2]] - s
        j = (denom > 0) ? s / denom : 0
        printf "%d\t%.2f\t%s\t%s\n", s, j, p[1], p[2]
    }
}' | sort -rn -k1,1 -k2,2 | head -n "$TOP" \
   | awk 'BEGIN{printf "%-8s %-8s %s\n", "SUPPORT","JACCARD","PAIR"}
          {printf "%-8s %-8s %s\n%-17s %s\n", $1, $2, $3, "", $4}'

echo
echo "# Next step: for a pair that looks like shared knowledge, see what ELSE"
echo "# moves with one of them:"
echo "#   git -C $REPO log --follow --format=%H -- <file> | while read c; do \\"
echo "#     git -C $REPO show --name-only --format= \$c; done | sort | uniq -c | sort -rn | head -20"
