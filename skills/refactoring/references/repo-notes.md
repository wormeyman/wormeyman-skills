# Repo-specific refactoring notes

Verification commands and known constraints for repos this skill is used on.
Read the relevant section before proposing changes - each entry records traps
that cost someone real time to find.

Commands and CI facts here were last checked on the date in each section
heading. Each repo's own CLAUDE.md or AGENTS.md is the current source for gate
commands. Read it first, and trust it over this file when they disagree.

All three repos below share one property that dominates everything else:
**they encode facts about a shipped video game that were established by
measurement, not by reasoning.** Code that looks naive is often a transcription,
and "simplifying" it silently replaces a measured fact with a plausible guess.
Where a comment cites a version, a commit SHA, or a probe, treat it as binding.

---

## factorio-blueprint-editor (checked 2026-09-25)

`~/GitHub/factorio-blueprint-editor` - TypeScript monorepo
(npm workspaces) + a Rust exporter. ~24.7k source lines.

### This was a live fork. It is not one any more

When this file was first written, the repo was a GitHub fork of
`teoxoy/factorio-blueprint-editor`, 399 commits ahead, with a stated plan to
send work back upstream. That was the constraint behind every structural
decision here. It no longer holds. Upstream's newest commit is `62d8b92d mark
project as unmaintained` (2026-08-16). The repo then moved to its own owner, and
GitHub no longer lists it as a fork. The checkout has no `upstream` remote.

So "renaming inherited files makes future merges painful" is no longer a cost,
because there are no future merges. What is left is weaker: the
`packages/editor` / `exporter` / `website` split, the `src/core/`
`src/containers/` `src/UI/` shape, and inherited filenames
(`spriteDataBuilder.ts`, `Entity.ts`, `Blueprint.ts`, `bpString.ts`) are what
the project's docs, specs and issue history describe. A large rename is a
documentation cost, not a merge cost. That is a reason not to do it casually,
but not a reason it cannot be done.

The MIT notice keeps teoxoy's copyright line and the README keeps crediting
him. That is attribution and stays either way.

### Verification

```bash
vp check .                  # oxfmt + oxlint + tsc across packages; must be 0
vp test                     # vitest: editor unit tests + scripts/ gate tests
```

**CI runs the Playwright suite now.** Older versions of this file said it did
not, and called that the trap. The `e2e` job in `.github/workflows/ci.yml` runs
it in four shards on PRs and pushes to `wormeyman-space-age-support`, and
`deploy` waits on both `checks` and `e2e`. Both jobs are gated on the `changes`
job's `web` output, which is on for any change outside `packages/exporter/`, or
inside its generated `data/output/`. A change that touches only the exporter
skips both, so its green run proves only the Rust job. Running the suite
locally is still faster feedback:

```bash
npm run localpreview        # terminal 1: Vite :8080 + sprite data :8081
npx playwright test         # terminal 2
```

Do not edit anything under `packages/` while a run is in flight. Vite
hot-reloads the page under the running spec, which then dies with "Execution
context was destroyed" in a spec unrelated to what you edited.

No coverage collection, no thresholds, no mutation tooling anywhere.

### Do not edit

- `packages/editor/src/core/railSignalSpots.ts` - `GENERATED - do not edit by
  hand`. 152 measured placements; regenerate via
  `tools/oracle/generate-rail-signal-spots.mjs`.
- `tools/oracle/fixtures/*.json` - "never hand-edit a fixture to make something
  pass; a mismatch is a finding."
- Fixed-point test fixtures (`tests/__fixtures__/sprite-data.json`,
  `recipe-shapes.json`, `rail-footprints.json`, generators fixtures). A diff
  means behavior changed - these are not refreshable snapshots.
- `packages/editor/src/basis/` (vendored transcoder) and `packages/exporter`
  are lint/format-excluded on purpose.
- The two macOS-only clippy warnings in `packages/exporter/src/setup.rs` - the
  autofix breaks Linux CI.

### Structure that looks redundant and is load-bearing

- **`PaintBlueprintEntityContainer.ts`: `planPlacement` and
  `placeEntityContainer` are two separate loops on purpose.** Collapsing them to
  `container.placeEntityContainer(container.planPlacement())` type-checks and
  reads as a pure simplification - and is a known bug (issue #163). This is the
  canonical example of the "structure encodes ordering" exception.
- `checkBuildable` must delegate to `planPlacement`, not repeat its grid
  questions (#181) - no test can read a sprite tint.
- `railSignalSnapping.ts`: `RAIL_SEARCH_WINDOW` is *derived*, not written down -
  "two limits that must agree are one limit".
- `snapRailSignal` returns the rail key with the position to avoid a second copy
  of the distance test.
- `WireConnections.hash()` sorts `cps` in place; the normalization is
  load-bearing.
- The generated spot table is ordered **by angle**, not by `dir`/`dx`/`dy`.

### Exactness rules - "tidying" these is a bug

- `areArraysEquivalent(undefined, undefined)` is **false**, and `Entity`'s
  setters depend on it.
- `util.duplicate` throws on `undefined`; `duplicate(x) || {}` does not work.
- Accessors returning `| undefined` must not become `[]` or `0` -
  `tests/entity-accessors.spec.ts` pins the difference.
- `History.updateMap/updateValue`: `undefined` is a *value* meaning "delete".
- An empty list in `data.json` is `{}`, not `[]` - read via `Array.isArray`,
  never `?? []`.
- Version checks must be `data.version !== undefined && data.version < X`, not
  `(data.version ?? 0) < X`.

### Where the naive instinct is maximally wrong

The largest files are simultaneously the most-changed, the most
upstream-shared, and the most source-of-truth-constrained:
`spriteDataBuilder.ts` (2,738 lines, 47 commits - a port of Factorio's sprite
selection), `Entity.ts` (1,761 / 41), `factorioData.ts` (1,066 / 33),
`Blueprint.ts` (955 / 31). "Split the biggest file" is the worst available move
here. Rail placement (`PositionGrid.isAreaAvailable`) is explicitly permissive
with measured exceptions - do not generalize its rules; ask the oracle.

---

## FactorioTools (checked 2026-09-23)

`~/GitHub/FactorioTools` - polyglot: ~13.7k C# source, a Vue 3
SPA (~1.8k `.vue` + ~1.6k hand-written TS), and 22.9k lines of **generated**
Lua. Treat all languages as in scope; treat generated output as never-edit.

### The C# is a transpilation source - this bans idiomatic C#

`src/FactorioTools` is transpiled to Lua 5.2 via `submodules/CSharp.lua`. From
CLAUDE.md, these constructs "have all been removed for Lua performance" and must
not come back:

- `yield return`
- LINQ
- named tuples
- `try` / `catch`
- struct dictionary keys

**This is the highest-risk trap in the repo**, because the single most likely
"cleanup" an agent proposes for imperative C# is exactly to rewrite it with
LINQ. It will compile, transpile, and parse cleanly, then fail at runtime inside
Factorio, because `Collections.Linq` is not in the CoreSystem load list. Only a
check that runs the planner catches it: the `transpile-lua` CI job or
`tools/check-lua.sh`.

Two more from the same constraint:
- **The core library must stay serialization-free** - `src/FactorioTools` has no
  JSON dependency by design. Adding `System.Text.Json` breaks the transpile.
- **Determinism**: Factorio overrides `pairs()` and `math.random()`. No
  order-dependent assumptions; stable iteration only.

Similarly, `Containers/` (`LocationBitSet` / `LocationIntSet` /
`LocationHashSet`) are hand-rolled for performance *and* Lua compatibility, and
are selected by build symbol. Replacing them with BCL types breaks the
compile-flag matrix. `Grid/Location.cs` is a documented hot type.

### Verification

```bash
# C# - the two gates CI proves
dotnet build -c Release /p:UseLuaSettings=true && dotnet test --no-build -c Release
dotnet build -c Release                        && dotnet test --no-build -c Release

# CI also compiles nine perf-flag permutations (Debug, build only), e.g.
dotnet build -c Debug /p:UseHashSets=false      # ...and UseBitArray, LocationAsStruct,
                                                # UseSharedInstances, UseVectors, UseStackalloc,
                                                # RentNeighbors, AllowDynamicFluteDegree, EnableGridToString

# TS/Vue, from src/vue (build includes swagger-gen + vue-tsc typecheck)
npm install && npm run build && npm run test

# Lua - same as the transpile-lua CI job: luac 5.2.4 syntax check plus a run of sample.lua, in Docker
tools/check-lua.sh
```

Prereqs: `dotnet workload restore` (wasm-tools) and
`git submodule update --init --recursive`. No local .NET 10? `./docker-build.sh`.

**`dotnet test` passing means 2,748 Verify snapshots (55 MB) still match
byte-for-byte.** Any refactor perturbing iteration order, tie-breaking, or
floating-point shows up as a mass snapshot diff. Update snapshots only through
Verify's received-vs-verified accept flow, never by hand, and never in bulk to
make a refactor pass.

### Do not edit

- `src/lua/**` - 129 files, 22.9k lines, all generated by
  `src/lua/Invoke-LuaBuild.ps1`.
- `src/vue/src/lib/FactorioToolsApi.ts` (757 lines) - generated by
  `npm run swagger-gen` from `src/WebApp/swagger.json`.
- `submodules/` - three pinned forks (`FluteSharp`, `delaunator-sharp`,
  `CSharp.lua`), two on custom `lua-compat` branches. Separate repos; edits do
  not travel with a PR.
- `Score.HasExpectedScore.verified.txt` - the planner-quality scoreboard across
  57 blueprints. `small-list.txt` / `big-list.txt` are normalized only via
  `dotnet run --project src/FactorioTools.Cli -- oil-field normalize`.
- `.github/renovate.json5` comments are "load-bearing, not decoration". The
  Verify family (`Verify`, `Verify.XunitV3`, `Verify.DiffPlex`) must move
  together in one PR. Bumping one alone builds cleanly and then fails most of
  the suite at runtime with `MethodAccessException`.

### Ports pinned to upstream commit SHAs

`OilField/Steps/AddPipes.1.FBE.cs`, `PlanBeacons.1.FBE.cs`, and
`OilField/Helpers.cs:1139` are line-level ports of teoxoy's
factorio-blueprint-editor, each citing a specific upstream SHA. The strategy
names encode it: `FbeOriginal` means "minimal modifications from upstream".
Cleaning up a `*.FBE.cs` file destroys diffability against the cited lines.

Note the consequence: **the two repos in this file are ports of each other in
part.** A change to the algorithm in one may need mirroring in the other, and
neither test suite will tell you.

### A genuine cross-language DRY candidate

`src/vue/src/stores/OilFieldStore.ts:6-48` re-declares every default from
`src/FactorioTools/OilField/OilFieldOptions.cs` - the same pole supply 7x7, wire
reach 9, beacon 9x9/3x3, `medium-electric-pole`, `speed-module-3`. And
`src/vue/src/lib/quality.ts` re-declares the quality level table (including the
skip-hidden-level-4 rule that makes legendary 5) already encoded in
`OilField/Quality.cs`.

These are two copies of one truth kept in sync by hand, across a language
boundary, with nothing that fails when they diverge. It is a real finding - but
the fix is a generated shared source, not a hand-written third copy, and it
should go through the existing swagger/codegen seam rather than a new one.

### Other traps

- **After changing C# planner code, run `npm run build-wasm` in `src/vue`** or
  the SPA runs stale logic.
- The `mkdir -p public` step before `cp -r` is mandatory - without it the bundle
  flattens and `framework/dotnet.js` 404s in production. Documented in two
  places, i.e. it has bitten before.
- `src/vue/public/` is gitignored and absent in a fresh checkout.
- `wasmPlanner.ts` must boot the .NET runtime on the **main thread** - a Web
  Worker deadlocks in `create()`.
- **Zero Vue component tests.** 1,805 lines of `.vue` have no automated
  coverage and are not even in the vitest `include` glob. Refactoring there is
  unguarded - write characterization tests first.
- Lua's gate is `tools/check-lua.sh`. The syntax check alone misses LINQ; the
  `sample.lua` run is the part that catches it.
- Style: hyphens, not em/en dashes.

---

## FactorioMapWebUI

`~/GitHub/FactorioMapWebUI` - Vue 3 + Pinia SPA, ~18.3k source
lines, ~39.8k test lines (2.2:1), 197 spec files. The strongest safety net of
the three.

**Gate:** `pnpm run verify` (about 3.5 minutes on a dev machine as of 2026-09-05; the repo CLAUDE.md has the current breakdown). Never `pnpm vp check --fix` in a deploy
path - a deploy must not rewrite files on its way out.

**Byte-exactness is a hard invariant.** `src/codec/mapExchangeString.ts` must
reproduce the game's zlib@9 stream byte-for-byte;
`test/fixtures/builtin-presets.json` is read-only ground truth.

A full refactor survey was completed 2026-08-04 and filed as **issue #156** -
read it before re-surveying. Its two headline results:

- The Nauvis/Vulcanus "twin" files are **not** duplication (0-2 shared commits
  per pair; ported from separately-versioned Lua files) and must not be merged.
- The real duplication runs *perpendicular* to the planet seam - a `box → pixel`
  block copied verbatim into 5 render files, `isWater` in 5, a byte-identical
  argmax loop in 2.

`cliffPlacement.ts` is out of scope while issue #84 is open - it is under active
measurement.
