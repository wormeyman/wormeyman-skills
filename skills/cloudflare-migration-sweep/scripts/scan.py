"""Scan the clones fetch_repos.py made for code that needs a Cloudflare migration.

    python3 scan.py --dest /path/to/scratch/cf-sweep            # summary
    python3 scan.py --dest ... --jsonl > hits.jsonl              # every hit
    python3 scan.py --dest ... --repo owner/name                 # one repo

Each rule carries the entry number from references/catalog.md, so a hit leads
straight to the docs URL, the fix, and the deadline. Tiers:

    required  - removed, past or near a hard end-of-life date, or deprecated
    review    - real pattern, but high false-positive rate; read every hit
    optional  - Cloudflare recommends it; nothing breaks if you wait

The rules were written against the docs as of 2026-09-25. New migrations land
all the time; refresh the catalog before trusting a clean result for long.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".next", ".wrangler", "coverage", "target",
             ".svelte-kit", ".vercel", ".output"}
# Generated from the runtime by `wrangler types`. It lists every Workers AI model,
# deprecated ones included, so scanning it fills the report with fake hits.
SKIP_FILES = {"worker-configuration.d.ts", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock"}
MAX_BYTES = 2_000_000
TEXT_EXT = {".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx", ".json", ".jsonc", ".toml", ".yml",
            ".yaml", ".sh", ".ps1", ".py", ".go", ".rb", ".php", ".tf", ".hcl", ".md", ".txt", ".mod",
            ".vue", ".svelte", ".astro", ".html", ".gs"}
BARE_NAMES = {"Makefile", "justfile", "go.mod", "Dockerfile", "Containerfile"}

R = re.compile
CODE = R(r"\.(ts|mts|cts|tsx|js|mjs|cjs|jsx|vue|svelte|astro)$")
SCRIPTY = R(r"(package\.json|\.sh|\.ps1|Makefile|\.github/workflows/.*\.ya?ml|\.py|\.go|\.rb|\.php|justfile)$")
WRANGLER = R(r"(^|/)wrangler\.(toml|json|jsonc)$")
PKG = R(r"(^|/)package\.json$")
WF = R(r"^\.github/workflows/.*\.ya?ml$")
TSCONFIG = R(r"(^|/)tsconfig[^/]*\.json$")
TESTCFG = R(r"(^|/)(vitest|jest)\.(config|workspace)[^/]*\.[cm]?[jt]s$|(^|/)jest\.config\.json$")
TF = R(r"\.tf$|\.terraform\.lock\.hcl$")
API_CODE = R(r"\.(ts|mts|cts|tsx|js|mjs|cjs|py|go|sh|ps1|ya?ml|rb|php)$")
MCPCFG = R(r"(\.mcp\.json|mcp[^/]*\.json|\.cursor/.*|\.vscode/.*|claude_desktop_config\.json)$")
REQS = R(r"(requirements[^/]*\.txt|pyproject\.toml)$")
GOMOD = R(r"(^|/)go\.mod$")
ANY_CODEISH = R(r"\.(ts|mts|cts|tsx|js|mjs|cjs|jsx|py|json|jsonc|toml|ya?ml)$")
CF_MENTION = R(r"wrangler|cloudflare|workers\.dev|pages\.dev", re.I)
COMMENT_LINE = R(r"^\s*(//|#|\*|/\*|<!--|--)")
# Only these file types have /* */ comments. In YAML or shell, "src/**" is not one.
BLOCK_COMMENTS = R(r"\.(ts|mts|cts|tsx|js|mjs|cjs|jsx|jsonc|json|go|php|css)$")


def has(rx):
    return lambda p: bool(rx.search(p))


def any_of(*rxs):
    return lambda p: any(r.search(p) for r in rxs)


def anywhere(_):
    return True


# (catalog entry, tier, label, file filter, regex)
RULES = [
    ("1", "required", "vitest-pool-workers -> vitest-plugin", any_of(PKG, CODE, TSCONFIG), R(r"@cloudflare/vitest-pool-workers")),
    ("2", "required", "vitest-pool-workers Vitest 3 config", has(TESTCFG), R(r"\b(defineWorkersConfig|defineWorkersProject)\b|@cloudflare/vitest-pool-workers/config|\b(isolatedStorage|singleWorker)\s*:")),
    ("2", "required", "env/SELF/fetchMock from cloudflare:test", has(CODE), R(r"import\s*\{[^}]*\b(SELF|fetchMock|env)\b[^}]*\}\s*from\s*[\"']cloudflare:test[\"']", re.S)),
    ("3", "required", "Miniflare 2 Jest/Vitest environment", has(PKG), R(r"\"(jest|vitest)-environment-miniflare\"")),
    ("3", "required", "Miniflare 2 environment in config", any_of(TESTCFG, TSCONFIG, PKG), R(r"(testEnvironment|environment)\s*:\s*[\"']miniflare[\"']|(jest|vitest)-environment-miniflare/globals")),
    ("3", "required", "Miniflare 2 global helpers", has(CODE), R(r"getMiniflare(Bindings|WaitUntil|FetchMock|DurableObjectStorage|DurableObjectState|DurableObjectInstance|DurableObjectIds)\(|setupMiniflareIsolatedStorage\(|flushMiniflareDurableObjectAlarms\(|runWithMiniflareDurableObjectGates\(")),
    ("4", "required", "unstable_dev", has(CODE), R(r"\bunstable_dev\s*\(|\bUnstableDevWorker\b")),
    ("5", "required", "unstable_startWorker", has(CODE), R(r"\bunstable_startWorker\s*\(")),
    ("6", "required", "Miniflare v2 packages", has(PKG), R(r"\"@miniflare/|\"miniflare\"\s*:\s*\"[~^>=\s]*2\.")),
    ("6", "required", "Miniflare v2 imports", has(CODE), R(r"from\s*[\"']@miniflare/")),
    ("7", "optional", "direct miniflare 3/4 dependency (v5 breaks)", has(PKG), R(r"\"miniflare\"\s*:\s*\"[~^>=\s]*[34]\.")),
    ("8", "required", "Wrangler v1 package", any_of(PKG, WF), R(r"@cloudflare/wrangler\b|cargo install wrangler")),
    ("8", "required", "Wrangler v1 config keys", has(WRANGLER), R(r"(?m)^\s*type\s*=\s*[\"'](webpack|javascript|rust)[\"']|^\s*webpack_config\s*=|^\s*\[build\.upload\]|^\s*entry-point\s*=")),
    ("9", "optional", "Wrangler 0-3 in package.json", has(PKG), R(r"\"wrangler\"\s*:\s*\"[~^>=v\s]*[0-3]\.")),
    ("9", "optional", "wranglerVersion 0-3 in workflow", has(WF), R(r"wranglerVersion:\s*[\"']?[0-3]\.")),
    ("10", "required", "config key removed in Wrangler v4", has(WRANGLER), R(r"(?m)^\s*(node_compat|legacy_assets|usage_model)\s*=|\"(node_compat|legacy_assets|usage_model)\"\s*:")),
    ("10", "required", "--node-compat / --legacy-assets flag", has(SCRIPTY), R(r"--node-compat\b|--legacy-assets\b")),
    ("11", "required", "Wrangler command removed in v4", has(SCRIPTY), R(r"wrangler\s+((pages\s+)?publish|generate|version)\b|wrangler\s+dev\b[^\n]*--(experimental-local|persist)\b")),
    ("12", "required", "getBindingsProxy", has(CODE), R(r"\bgetBindingsProxy\b")),
    ("13", "required", "wrangler kv:* colon syntax", has(SCRIPTY), R(r"wrangler\s+kv:(namespace|key|bulk)\b")),
    ("14", "review", "CF_* env var (count only if wrangler uses it)", has(SCRIPTY), R(r"\bCF_(API_TOKEN|API_KEY|EMAIL|ACCOUNT_ID|API_BASE_URL)\b")),
    ("15", "required", "Workers Sites [site]", has(WRANGLER), R(r"(?m)^\s*\[site\]|\"site\"\s*:\s*\{")),
    ("15", "required", "kv-asset-handler / __STATIC_CONTENT", any_of(PKG, CODE), R(r"@cloudflare/kv-asset-handler|getAssetFromKV|__STATIC_CONTENT")),
    ("16", "required", "legacy_env = false", has(WRANGLER), R(r"(?m)^\s*legacy_env\s*=\s*false|\"legacy_env\"\s*:\s*false")),
    ("17", "review", "service-worker syntax (PWA sw.js looks the same)", has(CODE), R(r"(?<!self\.)\baddEventListener\(\s*[\"'](fetch|scheduled|queue)[\"']")),
    ("18", "optional", "@cloudflare/workers-types (wrangler types recommended)", any_of(PKG, TSCONFIG), R(r"@cloudflare/workers-types(?!/20)")),
    ("18", "required", "workers-types dated entrypoint (removed in v5)", any_of(TSCONFIG, CODE), R(r"@cloudflare/workers-types/20\d\d-\d\d-\d\d")),
    ("19", "optional", "experimental_remote", any_of(WRANGLER, CODE), R(r"\bexperimental_remote\b")),
    ("20", "required", "pipelines binding `pipeline` field", has(WRANGLER), R(r"\[\[pipelines\]\][^\[]*?\n\s*pipeline\s*=|\"pipelines\"\s*:\s*\[[^\]]*\"pipeline\"\s*:", re.S)),
    ("21", "optional", "Cloudflare Pages project", any_of(WRANGLER, SCRIPTY), R(r"pages_build_output_dir|wrangler\s+pages\s+(deploy|publish|dev)|command:\s*pages\s+(deploy|publish)")),
    ("21", "optional", "Pages Functions / advanced mode", any_of(PKG, CODE), R(r"\bPagesFunction<|@cloudflare/pages-plugin-")),
    ("22", "required", "@cloudflare/next-on-pages", any_of(PKG, CODE), R(r"@cloudflare/next-on-pages|\bsetupDevPlatform\b")),
    ("23", "optional", "OpenNext (vinext recommended)", has(PKG), R(r"\"@opennextjs/cloudflare\"")),
    ("24", "required", "cloudflare/pages-action (repo is gone)", has(WF), R(r"uses:\s*cloudflare/pages-action@")),
    ("24", "required", "cloudflare/wrangler-action v1-v3", has(WF), R(r"uses:\s*cloudflare/wrangler-action@(v?[123](\.|\s|$)|[123]\.)")),
    ("25", "required", "@cloudflare/ai package", any_of(PKG, CODE), R(r"\"@cloudflare/ai\"|from\s*[\"']@cloudflare/ai[\"']|\bnew Ai\(")),
    ("26", "required", "deprecated Workers AI model", has(ANY_CODEISH), R(r"@(cf/moonshotai/kimi-k2\.5|hf/meta-llama/meta-llama-3-8b-instruct|cf/meta/llama-3-8b-instruct(-awq)?|cf/meta/llama-3\.1-8b-instruct(-awq)?|cf/meta/llama-3\.1-70b-instruct|cf/meta/llama-2-7b-chat-(int8|fp16)|cf/mistral/mistral-7b-instruct-v0\.1|hf/mistral/mistral-7b-instruct-v0\.2|hf/google/gemma-7b-it|cf/google/gemma-3-12b-it|hf/nousresearch/hermes-2-pro-mistral-7b|cf/microsoft/phi-2|cf/defog/sqlcoder-7b-2|cf/unum/uform-gen2-qwen-500m|cf/facebook/bart-large-cnn)[\"'`]")),
    ("27", "optional", "AutoRAG legacy API", has(API_CODE), R(r"\.autorag\s*\(|/autorag/rags/|\bcreateAutoRAG\b")),
    ("28", "optional", "AI Gateway Universal Endpoint", has(API_CODE), R(r"gateway\.ai\.cloudflare\.com/v1/[^/\s\"'`]+/[^/\s\"'`]+/?[\"'`]")),
    ("29", "required", "agents-sdk / MCP SDK v1 handler", any_of(PKG, CODE), R(r"\"agents-sdk\"|\bexperimental_createMcpHandler\b|\bMcpAgent\b")),
    ("30", "required", "Cloudflare MCP server /sse URL", has(MCPCFG), R(r"\.mcp\.cloudflare\.com/sse")),
    ("31", "review", "@cloudflare/sandbox (check 2026 deprecations)", has(PKG), R(r"\"@cloudflare/sandbox\"")),
    ("32", "review", "DO new_classes (KV-backed; fine as old history)", has(WRANGLER), R(r"\bnew_classes\b")),
    ("33", "optional", "DO migrations array (exports recommended)", has(WRANGLER), R(r"(?m)^\s*\[\[migrations\]\]|\"migrations\"\s*:\s*\[")),
    ("34", "required", "Vectorize V1", has(SCRIPTY), R(r"--deprecated-v1")),
    ("36", "optional", "Global API key auth", any_of(API_CODE, WF), R(r"X-Auth-Key|X-Auth-Email|\bCLOUDFLARE_API_KEY\b|\bCLOUDFLARE_EMAIL\b|\bCF_API_KEY\b")),
    ("37", "required", "Service Key auth (EOL 2026-09-30)", anywhere, R(r"X-Auth-User-Service-Key|origin-ca-issuer")),
    ("38", "required", "legacy KV REST route (EOL 2026-10-15)", has(API_CODE), R(r"/accounts/[^/\s]+/workers/namespaces|workers/namespaces/")),
    ("39", "required", "teamnet CIDR routes (EOL 2026-10-05)", has(API_CODE), R(r"teamnet/routes/network/")),
    ("40", "required", "cloudflared proxy-dns / old image", anywhere, R(r"cloudflared\s+proxy-dns|proxy-dns\s*:\s*true|TUNNEL_DNS_|cloudflare/cloudflared:(20(1\d|2[0-4])\.|2025\.[1-9]\.)|cloudflared-(windows-386|darwin-amd64)")),
    ("41", "optional", "Terraform provider v4", has(TF), R(r"version\s*=\s*\"[~>=<\s]*[0-4]\.[^\"]*\"|resource\s+\"cloudflare_(record|access_application|access_policy|tunnel|argo_tunnel|zone_settings_override)\"")),
    ("42", "required", "legacy WAF resources/APIs", any_of(TF, API_CODE), R(r"resource\s+\"cloudflare_(firewall_rule|filter|rate_limit|waf_group|waf_package|waf_rule|waf_override)\"|/firewall/rules|/firewall/waf/(packages|overrides)|/rate_limits\b")),
    ("43", "optional", "Page Rules", any_of(TF, API_CODE), R(r"resource\s+\"cloudflare_page_rule\"|/pagerules\b")),
    ("44", "required", "zone settings batch (EOL 2027-03-31)", has(API_CODE), R(r"/zones/[^/\s\"'`]+/settings/?([\"'`?]|$)", re.M)),
    ("44", "required", "foundation_dns (EOL 2026-11-23)", has(API_CODE), R(r"\bfoundation_dns\b")),
    ("44", "required", "legacy Registrar (EOL 2026-09-27)", has(API_CODE), R(r"registrar/domains")),
    ("44", "required", "DNS analytics REST (EOL 2026-12-01)", has(API_CODE), R(r"\bdns_analytics\b")),
    ("44", "optional", "Account Roles API", has(API_CODE), R(r"/accounts/[^/\s\"'`]+/roles\b")),
    ("44", "required", "already-dead REST endpoints", has(API_CODE), R(r"analytics/(dashboard|colos)|httpRequests1[md]ByColoGroups|/accounts/[^/\s\"'`]+/tunnels\b|images/v1/direct_upload|settings/(minify|brotli|mobile_redirect|server_side_exclude|mirage)\b|dns_settings/(use_apex_ns|secondary_overrides)|self_hosted_domains")),
    ("45", "optional", "old Cloudflare API SDK major", any_of(PKG, REQS, GOMOD), R(r"(?m)\"cloudflare\"\s*:\s*\"[~^>=\s]*[0-5]\.|^\s*cloudflare[<>=~!]*\s*[0-4]\.|github\.com/cloudflare/cloudflare-go(/v[0-6])?\s")),
]


def text_files(root):
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]) or p.name in SKIP_FILES:
            continue
        if not p.is_file() or p.is_symlink():
            continue
        if (p.suffix not in TEXT_EXT and p.name not in BARE_NAMES and not p.name.startswith(".env")
                and not p.name.startswith("Dockerfile")):
            continue
        if p.name.endswith(".min.js"):
            continue
        try:
            if p.stat().st_size <= MAX_BYTES:
                yield rel.as_posix(), p.read_text("utf-8", "replace")
        except OSError:
            continue


def scan_repo(repo_dir, name):
    hits, mentions = [], False
    for rel, text in text_files(repo_dir):
        if not mentions and CF_MENTION.search(text):
            mentions = True
        lines = None
        for rid, tier, label, want, rx in RULES:
            if not want(rel):
                continue
            for m in rx.finditer(text):
                lines = lines or text.splitlines()
                n = text.count("\n", 0, m.start()) + 1
                line = lines[n - 1] if n <= len(lines) else ""
                in_block = bool(BLOCK_COMMENTS.search(rel)) and \
                    text.rfind("/*", 0, m.start()) > text.rfind("*/", 0, m.start())
                hits.append({"repo": name, "entry": rid, "tier": tier, "label": label, "file": rel, "line": n,
                             "comment": in_block or bool(COMMENT_LINE.match(line)), "text": line.strip()[:160]})
    return hits, mentions


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, type=Path, help="the --dest given to fetch_repos.py")
    ap.add_argument("--repo", action="append", default=[], help="owner/name; repeatable")
    ap.add_argument("--jsonl", action="store_true", help="print every hit as a JSON line")
    args = ap.parse_args()

    manifest = {r["repo"]: r for r in json.loads((args.dest / "repos.json").read_text())}
    clones = args.dest / "clones"
    all_hits, quiet = [], []
    for name, meta in sorted(manifest.items()):
        if args.repo and name not in args.repo:
            continue
        d = clones / name.replace("/", "__")
        if not d.is_dir():
            print(f"MISSING CLONE {name} - rerun fetch_repos.py", file=sys.stderr)
            continue
        hits, mentions = scan_repo(d, name)
        flags = [k for k in ("archived", "fork", "collaborator") if meta.get(k)]
        for h in hits:
            h["flags"] = flags
        all_hits += hits
        if mentions and not hits:
            quiet.append((name, flags))

    if args.jsonl:
        for h in all_hits:
            print(json.dumps(h))
        return

    by_repo, commented = defaultdict(Counter), defaultdict(Counter)
    for h in all_hits:
        key = (h["tier"], h["entry"], h["label"])
        by_repo[h["repo"]][key] += 1
        if h["comment"]:
            commented[h["repo"]][key] += 1
    order = {"required": 0, "review": 1, "optional": 2}
    only_comments = sorted(r for r in by_repo if sum(commented[r].values()) == sum(by_repo[r].values()))
    live = [r for r in by_repo if r not in only_comments]
    for repo in sorted(live, key=lambda r: (min(order[t] for t, _, _ in by_repo[r]), r)):
        flags = [k for k in ("archived", "fork", "collaborator") if manifest[repo].get(k)]
        print(f"\n{repo}" + (f"  [{', '.join(flags)}]" if flags else ""))
        for (tier, entry, label), n in sorted(by_repo[repo].items(), key=lambda kv: (order[kv[0][0]], int(kv[0][1]))):
            c = commented[repo][(tier, entry, label)]
            note = "  <- every hit is a comment line" if c == n else (f"  ({c} in comments)" if c else "")
            print(f"  {tier:8} #{entry:>2} {label}: {n}{note}")
    if only_comments:
        print("\nEvery hit is in a comment - usually a note about a migration already done. Confirm, then drop:")
        for repo in only_comments:
            labels = ", ".join(f"#{e}" for _, e, _ in sorted(by_repo[repo], key=lambda k: int(k[1])))
            print(f"  {repo}: {labels}")
    print(f"\n{len(by_repo)} repos with hits, {len(all_hits)} hits. Use --jsonl for file:line detail.")
    if quiet:
        print("\nMention Cloudflare, wrangler, workers.dev or pages.dev but matched no rule - read these by hand:")
        for name, flags in quiet:
            print(f"  {name}" + (f"  [{', '.join(flags)}]" if flags else ""))


main()
