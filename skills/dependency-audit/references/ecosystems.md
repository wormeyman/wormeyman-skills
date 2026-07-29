# Ecosystem commands

Read the section for the ecosystems present. All commands are read-only; none
mutate a lockfile or install anything. Run them with absolute paths.

## Contents

- [Detecting what is present](#detecting-what-is-present)
- [npm / pnpm / yarn](#npm--pnpm--yarn)
- [Rust](#rust)
- [Python](#python)
- [Go](#go)
- [GitHub Actions](#github-actions)
- [The toolchain outside any package manager](#the-toolchain-outside-any-package-manager)
- [Automated updating](#automated-updating)

## Detecting what is present

Check for lockfiles before assuming a manager: `package-lock.json`,
`pnpm-lock.yaml`, `yarn.lock`, `Cargo.lock`, `uv.lock`, `poetry.lock`,
`requirements.txt`, `go.sum`, `Gemfile.lock`, `composer.lock`.

A monorepo may hold several. A directory with source but no manifest is a real
finding worth one line - it means that component is outside dependency
management entirely.

## npm / pnpm / yarn

```sh
npm outdated --workspaces --include-workspace-root   # empty output means current
npm audit
npm ls <pkg>                                          # duplicates across the tree
npm view <pkg> dist-tags time versions                # publish dates live in `time`
npm view <pkg> repository homepage
```

`npm outdated` **exits non-zero when it finds something**, which is success, not
failure. Do not read the exit code as an error.

**Publish date** comes from `npm view <pkg> time.<version>`. Worth collecting:
it separates "old because finished" from "old because abandoned", and some
projects enforce a minimum release age before a version may be installed.

**Dist-tags are evidence about maintainer intent.** A tag like `factorio-2.0`
or `legacy` alongside `latest` means the maintainer publishes a supported older
line, which turns "we are behind" into "we are on the sanctioned branch". Always
check `dist-tags` before calling a held version stale.

**Unused dependencies:**

```sh
npx knip --no-progress        # also finds unused exports and files
npx depcheck                  # lighter, dependencies only
```

Report the tool's output. Grep cannot see a package that is declared and never
imported, which is the most common removable thing, and it misses dynamic
imports, re-exports and type-only usage.

**Bundled size**, when the question is weight rather than currency: build with a
sourcemap and attribute bytes per source. `rollup-plugin-visualizer` or an
equivalent gives a treemap. Attribution from `sourcesContent` character counts
is pre-minification and runs roughly 2x the minified figure - say which you are
quoting.

**Types packages**: `@types/x` is redundant if `x` ships its own. Check for a
`types`/`typings` field in the package's own `package.json`, or a bundled
`index.d.ts`. TypeScript prefers the package's own, so a redundant `@types/x` is
already inert - and occasionally *less* precise than the bundled one.

**Overrides and aliases change what "latest" means.** An `overrides` entry that
aliases a package name to a different package (`"vite": "npm:@scope/other@1.2.3"`)
means `npm outdated` is reporting on the alias target, not the named package.
Read `overrides` / `resolutions` / `pnpm.overrides` before trusting any row.

## Rust

```sh
cargo tree --workspace
cargo search <crate>            # latest published
```

Without `cargo-outdated` or `cargo-audit` installed, compare `Cargo.lock`
versions against crates.io by hand rather than installing tooling into a repo
you were asked to inspect.

Advisories: fetch from the RustSec database rather than guessing.

Common supersessions worth checking for: `lazy_static` -> `std::sync::LazyLock`,
`failure` -> `thiserror`/`anyhow`, and older `async`-ecosystem crates. Also check
the declared `edition` against current.

## Python

```sh
uv pip list --outdated          # or: pip list --outdated
pip-audit                       # if already available
```

Note whether the project pins (`==`), floors (`>=`) or ranges, and whether a
lockfile exists at all - an unlocked `requirements.txt` is a different risk
profile from `uv.lock`.

## Go

```sh
go list -m -u all               # -u shows available upgrades
govulncheck ./...               # if already available
```

Go's minimum-version-selection means "outdated" reads differently: a module can
be intentionally behind because nothing requires newer.

## GitHub Actions

Read every file in `.github/workflows/` and any composite actions under
`.github/actions/`.

```sh
gh api repos/<owner>/<repo>/releases/latest --jq .tag_name
```

Check for:

- Actions on a **deprecated Node runtime**. Anything still on node16 will start
  warning and then failing.
- **Deprecated runner images** in `runs-on`.
- **Moving tag vs pinned SHA.** Neither is wrong - a SHA is supply-chain safer,
  a tag gets fixes automatically. Report which the repo uses consistently and
  flag any outlier, rather than pushing a preference.
- A composite action that pins a tool **plus a checksum of its installer**. Those
  must move together, and the checksum is the part people forget.

## The toolchain outside any package manager

Easy to miss and often the most consequential, because nothing reports it as
outdated:

- Version files: `.node-version`, `.nvmrc`, `.tool-versions`, `rust-toolchain.toml`.
- `engines` / `devEngines` / `packageManager` in `package.json`.
- **Vendored binaries checked into the repo**, and any file that must match one
  byte-for-byte (an encoder and its matching decoder, a WASM module and its JS
  loader). These are invisible to every dependency tool, so name them explicitly.
- `compatibility_date` / `compatibility_flags` in `wrangler.jsonc`, and the
  equivalent platform-version fields elsewhere.
- A **meta-package that pins its own toolchain**. If one dependency bundles the
  bundler, linter, formatter and test runner at exact versions, none of those can
  move independently - so "bump vitest" has no answer except "bump the parent".
  State this once, clearly; it saves the next person filing an impossible task.

## Automated updating

Check for `.github/dependabot.yml`, `renovate.json`, `.renovaterc`, or a
Renovate app installation. If none exists, say so and recommend one sized to the
repo: Dependabot for a small dependency count and simple grouping, Renovate when
you want grouped PRs, a minimum release age, or automerge rules.

Where constraints exist (a held major, a coupled binary pair), the automation
config is where they should be encoded - `ignore` entries in Dependabot,
`packageRules` in Renovate - so the hold survives without a human re-explaining
it every quarter. An audit that finds a documented hold and no corresponding
ignore rule has found a real gap.
