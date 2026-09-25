# Cloudflare migration catalog

Built on 2026-09-25 from `developers.cloudflare.com/llms.txt`, all 106 product
`llms.txt` files, every migration and deprecation page they list, the API
deprecations page, and the changelog feed. Items the docs do not state outright
were checked against npm `deprecated` flags and the GitHub API, marked
"(measured)". Entry numbers match the `#` column in `scan.py` output.

**This goes stale.** To refresh, re-read
`https://developers.cloudflare.com/changelog/` from the build date forward and
`https://developers.cloudflare.com/fundamentals/api/reference/deprecations/`,
then add rules to `scan.py` and entries here.

## Hard dates

| Date | What stops working | Entry |
| --- | --- | --- |
| 2026-09-27 | Legacy Registrar endpoints | 44 |
| 2026-09-30 | Service Key auth (`X-Auth-User-Service-Key`) | 37 |
| 2026-10-05 | teamnet CIDR route endpoints, tunnel `connections` field | 39 |
| 2026-10-15 | Legacy KV REST routes (`/workers/namespaces`) | 38 |
| 2026-11-23 | `foundation_dns` field | 44 |
| 2026-12-01 | DNS analytics REST | 44 |
| 2027-03-31 | Zone settings batch GET/PATCH | 44 |

## Testing

**1. `@cloudflare/vitest-pool-workers` -> `@cloudflare/vitest-plugin`.**
[Guide](https://developers.cloudflare.com/workers/testing/vitest-integration/migration-guides/migrate-to-vitest-plugin/).
Renamed at 1.0 on 2026-08-19, same API. Run
`npx @cloudflare/codemods vitest:pool-workers-to-vitest-plugin` (use the repo's
package manager). The codemod replaces the name inside comments too, which can
leave comments claiming versions that never existed - read its diff. It also sets
the range to `^1.0.0`; pin what you tested. If `allowScripts` lists `workerd@<exact
version>`, the new workerd needs its own entry. Plugin 1.2.8 still requires
`vitest ^4.1.0` (Vitest 5 is cloudflare/workers-sdk#15500).

**2. vitest-pool-workers 0.12 (Vitest 3) -> 0.13+ (Vitest 4).**
[Guide](https://developers.cloudflare.com/workers/testing/vitest-integration/migration-guides/migrate-from-vitest-3-to-vitest-4/).
`defineWorkersConfig`/`defineWorkersProject` and `fetchMock` are removed. Use a
`cloudflareTest()` plugin inside `defineConfig`, drop `isolatedStorage` and
`singleWorker`, mock `globalThis.fetch` or use `@msw/cloudflare`. `env` and `SELF`
from `cloudflare:test` still work but are deprecated: import `env` (and
`exports`) from `cloudflare:workers`. Keep `runInDurableObject`,
`createExecutionContext`, `waitOnExecutionContext` on `cloudflare:test`. After the
switch, a `ProvidedEnv` augmentation of `cloudflare:test` types nothing; `env` is
`Cloudflare.Env` from `wrangler types`.

**3. Miniflare 2 Jest/Vitest environments -> Vitest plugin.**
[Guide](https://developers.cloudflare.com/workers/testing/vitest-integration/migration-guides/migrate-from-miniflare-2/).
Removed; both packages are npm-deprecated (measured). Move Jest to Vitest first.
The plugin does not support service-worker syntax (entry 17).

**4. `unstable_dev` -> Vitest plugin or `createTestHarness`.**
[Guide](https://developers.cloudflare.com/workers/testing/vitest-integration/migration-guides/migrate-from-unstable-dev/).
Deprecated, no date. Unit tests: `exports.default.fetch()` from
`cloudflare:workers`. Integration tests: `createTestHarness()` from `wrangler`.

**5. `unstable_startWorker` -> `createTestHarness`.**
[Docs](https://developers.cloudflare.com/workers/testing/unstable_startworker/).
Deprecated, no date.

**6. Miniflare v2 API -> current Miniflare.**
[Guide](https://developers.cloudflare.com/workers/testing/miniflare/migrations/from-v2/).
Removed; `@miniflare/*` npm-deprecated (measured). One `miniflare` package,
`workers: []`, `queueBindings` -> `queueProducers`, `cfFetch` -> `cf`.

**7. Miniflare v4 -> v5 (direct dependency only).**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-09-08-miniflare-v5/).
Breaking only when you bump it: new config shape, `/cdn-cgi` routes move under
`/cdn-cgi/local`. Nothing to do if Miniflare only comes in through wrangler, Vite
or the Vitest plugin.

## Wrangler and config

**8. Wrangler v1 -> current.**
[Guide](https://developers.cloudflare.com/workers/wrangler/migration/v1-to-v2/update-v1-to-v2/).
Removed; package npm-deprecated (measured). `type = "webpack"`, `[build.upload]`
and friends become `main` and `rules`.

**9. Wrangler v3 -> v4.**
[Guide](https://developers.cloudflare.com/workers/wrangler/migration/update-v3-to-v4/).
Recommended; no v3 end-of-life stated. KV and R2 data commands now default to
local - add `--remote` where they should hit production.

**10. Config keys removed in v4: `node_compat`, `legacy_assets`, `usage_model`.**
Same guide. Use the `nodejs_compat` flag (on by default from compatibility date
2026-08-04), `[assets]`, and delete `usage_model`.

**11. Commands removed in v4.**
[Deprecations](https://developers.cloudflare.com/workers/wrangler/deprecations/#wrangler-v3).
`publish` -> `deploy`, `pages publish` -> `pages deploy`, `generate` ->
`npm create cloudflare@latest`, `version` -> `--version`.

**12. `getBindingsProxy` -> `getPlatformProxy`.** Removed in v4; same arguments.

**13. `wrangler kv:*` -> `wrangler kv *`.**
[Docs](https://developers.cloudflare.com/kv/reference/kv-commands/#deprecations).
Deprecated since 3.60.0.

**14. `CF_*` env vars -> `CLOUDFLARE_*`.**
[Docs](https://developers.cloudflare.com/workers/wrangler/system-environment-variables/#deprecated-global-variables).
Deprecated. High false-positive rate: flarectl, lego, acme.sh, Traefik, certbot
and external-dns use the same names. Only counts where wrangler reads it.

**15. Workers Sites -> Workers Static Assets.**
[Docs](https://developers.cloudflare.com/workers/static-assets/). Deprecated in v4.
`[site]` becomes `[assets]`; drop `@cloudflare/kv-asset-handler` from your own
code. Wrangler depends on kv-asset-handler itself, so a lockfile hit means
nothing.

**16. Service environments (`legacy_env = false`).** Deprecated in v4. Only
`false` counts. Worker names change to `<name>-<env>`.

**17. Service-worker syntax -> ES modules.**
[Guide](https://developers.cloudflare.com/workers/reference/migrate-to-module-workers/).
Deprecated but supported; required for Durable Objects, D1, Workers AI, the Vitest
plugin and more. Browser PWA service workers look identical - check the file is
the Worker's `main`.

**18. `@cloudflare/workers-types` -> `wrangler types`.**
[Docs](https://developers.cloudflare.com/workers/languages/typescript/#migrating-from-cloudflareworkers-types-to-wrangler-types).
Switching is recommended only. But v5 REMOVED the dated entrypoints
(`@cloudflare/workers-types/2023-07-01`), so those imports break on a v5 bump.

**19. `experimental_remote` -> `remote`.** Low urgency; wrangler 4.37.0+.

**20. Pipelines binding `pipeline` -> `stream`.**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-05-27-pipeline-binding-stream-field/).
Deprecated, still accepted with a warning.

## Pages, frameworks, CI

**21. Pages -> Workers with Static Assets.**
[Guide](https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/).
Recommended, not deprecated. Things that bite:
- Pages guessed SPA vs 404 behavior from `index.html`/`404.html`. Workers needs
  `not_found_handling` set on purpose, and `single-page-application` returns 200
  where a Pages 404.html shell returned 404.
- An advanced-mode `_worker.js` becomes `main`; move it out of the asset folder.
- A Worker never receives requests for a `*.pages.dev` host, so redirects keyed
  on that host die with the Pages project.
- `_headers` and `_redirects` carry over. Check headers such as CSP on a live
  response afterwards, because a dropped header fails silently.
- A custom domain that is a CNAME to `<project>.pages.dev` becomes a Custom
  Domain on the Worker. Touch only that record.
- wrangler-action runs Pages deploys as `command: pages deploy ...`, with no
  `wrangler` in front.

**22. `@cloudflare/next-on-pages` -> vinext or OpenNext.**
[Docs](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/).
Effectively removed; npm-deprecated, repo archived (measured).

**23. OpenNext -> vinext.** Recommended only.

**24. GitHub Actions.**
[Docs](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/).
`cloudflare/pages-action` returns 404 (measured) - those workflows are broken.
Use `cloudflare/wrangler-action@v4` with `apiToken` and `accountId`. v1/v2 used
Global API key auth that v3+ dropped.

## AI

**25. `@cloudflare/ai` package -> `env.AI` binding.**
[Docs](https://developers.cloudflare.com/workers-ai/configuration/bindings/).
Package npm-deprecated (measured).

**26. Deprecated Workers AI models (2026-05-30).**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-05-08-planned-model-deprecations/).
Past the date. Replacements: `@cf/zai-org/glm-4.7-flash`,
`@cf/google/gemma-4-26b-a4b-it`, `@cf/moonshotai/kimi-k2.6`. A generated
`worker-configuration.d.ts` lists every model; `scan.py` skips it.

**27. AutoRAG -> AI Search binding and routes.**
[Guide](https://developers.cloudflare.com/ai-search/api/migration/workers-binding/).
Legacy, still works.

**28. AI Gateway Universal Endpoint.**
[Docs](https://developers.cloudflare.com/ai-gateway/usage/universal/). Deprecated,
no date.

**29. `agents-sdk` -> `agents`; MCP SDK v2.**
[Guide](https://developers.cloudflare.com/agents/model-context-protocol/guides/migrate-to-mcp-sdk-v2/).
`agents-sdk` npm-deprecated; v1 server handlers go in the next major.

**30. Cloudflare-hosted MCP `/sse` -> `/mcp`.**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-07-28-cloudflare-mcp-servers-mcp-2026-07-28/).
Clients that force SSE transport break.

**31. Sandbox SDK 2026 deprecations.**
[Guide](https://developers.cloudflare.com/sandbox/guides/2026-deprecation/). Use
the RPC transport, `sandbox.tunnels.get()`, `createSession()`.

## Durable Objects, Vectorize, D1

**32. New DO classes: `new_classes` -> `new_sqlite_classes`.**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-07-09-restrict-new-kv-backed-namespaces/).
New KV-backed classes fail to deploy on accounts without one. Never rewrite an
existing migration tag - an old `new_classes` entry is normal history.

**33. DO `migrations` array -> declarative `exports`.**
[Docs](https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/).
Recommended for new Workers; `migrations` stays supported.

**34. Vectorize V1.**
[Docs](https://developers.cloudflare.com/vectorize/reference/transition-vectorize-legacy/).
Mostly invisible in repos; check indexes in the dashboard.

**35. D1 alpha databases.** Dead since 2024-08-22; not visible in repos
(`wrangler d1 info`).

## Auth, tunnels, Terraform, REST

**36. Global API key -> API tokens.**
[Docs](https://developers.cloudflare.com/fundamentals/api/get-started/keys/).
Legacy, no date.

**37. Service Key auth.**
[Deprecations](https://developers.cloudflare.com/fundamentals/api/reference/deprecations/).
**End of life 2026-09-30.**

**38. Legacy KV REST routes.**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-07-15-kv-legacy-namespace-routes-deprecation/).
`/workers/namespaces/` -> `/storage/kv/namespaces/`, same payloads. **End of
life 2026-10-15.**

**39. teamnet CIDR routes and tunnel `connections`.**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-07-09-tunnel-routes-and-connections-api-changes/).
**End of life 2026-10-05.**

**40. cloudflared.** `proxy-dns` gone since 2026-02-02; each release supported
for a year; 32-bit Windows and Intel Mac builds stop in 2027.
[Changelog](https://developers.cloudflare.com/changelog/post/2026-09-18-cloudflared-architecture-deprecation/).

**41. Terraform provider v4 -> v5.**
[Changelog](https://developers.cloudflare.com/changelog/post/2026-04-24-tf-migrate-tool-released/).
Use `tf-migrate`. Strongly recommended, no v4 end of life.

**42. Legacy WAF (Firewall Rules, Filters, old rate limiting, old managed
rules).** [Guide](https://developers.cloudflare.com/waf/reference/legacy/firewall-rules-upgrade/).
No longer supported since 2025-06-15. Use `cloudflare_ruleset`.

**43. Page Rules -> Rules.**
[Guide](https://developers.cloudflare.com/rules/reference/page-rules-migration/).
Deprecated; auto-migration planned.

**44. Other REST deprecations.**
[Deprecations](https://developers.cloudflare.com/fundamentals/api/reference/deprecations/).
Dated ones are in the table at the top. Also: changing a DNS record's `type` in
place (ended 2026-06-30, not greppable), Account Roles -> `iam/permission_groups`,
and already-dead endpoints (Zone Analytics, `httpRequests1*ByColoGroups`, the Argo
Tunnel API, Images v1 direct upload, minify/brotli/mirage settings).

**45. Cloudflare API SDK majors.** Optional. TypeScript v6, Python v5, Go v7 are
current.

## Not migrations

- Old `compatibility_date` values are "supported forever". Raising one is a
  runtime behavior change to production, not a migration - see SKILL.md.
- `wrangler dev --local`. The Wrangler v3 deprecations page still calls it
  unnecessary, but in Wrangler 4 (checked on 4.141.0) `--local` means "run
  locally with remote bindings disabled". It does something again, so leave it.
- Browser Rendering -> Browser Run is a rename only.
- Competitor-to-Cloudflare guides (Netlify, Vercel, S3) are not required work.
- Pages build image versions, AI Gateway legacy logs and SSL for SaaS v1 leave
  nothing in a repo.
