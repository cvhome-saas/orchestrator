# landing-ui CPU and memory — the runtime, the hot spots, and what a spike does to one task

This is the one plan for this change, in every repo. Every work item is one PR in one repo, on the same branch name,
`fix/landing-ui-cpu-memory`. In cvhome, each phase is one commit on one PR, easiest first. QA cases live in
`cvhome/store-pod/landing-ui/qa/landing-ui-qa.md`, never here.

It follows [`landing-ui-render-cost.md`](landing-ui-render-cost.md): cvhome#353 and #356 took a home render from
271 ms to ~95 ms of CPU. cvhome-platform#11 gave landing-ui its own `ssr` size, 0.5 vCPU / 1 GB, with CPU autoscaling.

## What dev still shows (2026-09-13/14)

- **At 30 shoppers** (`browse-load-20260913T214244Z`), landing-ui sat at 90–96 % of its 0.5 vCPU, ~95 ms of CPU
  per page. Pages p95 were 2.1–4.2 s against a 3 s SLO, and catalog was next at 81 %.
- **A spike from 8 to 300 shoppers** drove landing-ui to 100 % CPU and its memory from 10 % to 59 % of 1 GB, and
  4.8 % of requests timed out. The task survived and recovered within seconds. The memory rise first read as ~1.7 MB
  held per waiting request; the measurements below show it is the V8 heap filling, not request state.
- **Autoscaling never fired.** Target tracking needs three one-minute datapoints over target, plus metric lag and
  a task start, so a spike shorter than about 4 minutes never gets a second task.

## How it was measured

- **Build and image:** cvhome `main` at `113caa92b` (after #356), built as CodeBuild builds it, on production's base
  image (`gcr.io/distroless/nodejs20`, the image `public.ecr.aws/b2i4h4k9/nodejs20` mirrors).
- **Container:** dev's size, `--cpus=0.5 --memory=1g`, telemetry on and exporting over OTLP.
- **Backend:** org1-store2's real responses, recorded once from the load stack and replayed from memory. This makes
  runs repeatable and keeps them off the shared stack. The same renders against the live load stack average
  41.0 ms, against 39.4 ms here.
- **CPU per render:** the container cgroup's `usage_usec` over 20 sequential renders of each of home, a category, a
  product and a search, in 2–3 interleaved rounds. It is read from a sidecar, so no reader runs inside the measured
  cgroup.
- **Memory:** the cgroup's `anon` and its working set (`memory.current` − `inactive_file`, what ECS reports),
  sampled every 0.2 s during a burst. The cgroup's `memory.peak` is not used: it counts the page cache of the build's
  files.
- **Machine:** an arm64 laptop, where a render costs about 0.45× what it costs on a Fargate x86 vCPU. The load
  stack's calibration agrees: 41.6 ms here against ~95 ms on dev. **Ratios carry to dev; absolute milliseconds do
  not.**

| CPU per render (mean of 4 pages) | Home | Category | Product | Search | Mean | vs today |
| --- | --- | --- | --- | --- | --- | --- |
| **Node 20, today** | 58.9 | 44.5 | 27.3 | 27.1 | 39.4 ms | — |
| Node 22 | 50.2 | 35.3 | 25.1 | 23.0 | 33.4 ms | −18.5 % |
| **Node 24** | 35.8 | 25.9 | 15.9 | 20.8 | 24.6 ms | **−37.6 %** |
| Node 20, backend responses gzipped (what spg does today) | 60.4 | 49.3 | 27.7 | 27.9 | 41.3 ms | +4.8 % |
| Node 20, telemetry off | 51.6 | 42.3 | 24.1 | 25.3 | 35.8 ms | −9.2 % |
| Node 20, only the `http`/`undici` instrumentations | 56.9 | 42.7 | 25.6 | 27.9 | 38.2 ms | −3.0 % |
| Node 20, `formatAmount` memoised (own A/B, its base 36.7 ms) | 52.6 | 39.9 | 26.8 | 25.9 | 36.3 ms | −1.2 % (home −4.2 %, category −5.0 %); −4.1 % on Node 24 |
| Node 20, listing payload trimmed (cards whitelist) | 60.2 | 48.8 | 27.8 | 25.4 | 40.6 ms | −1.0 %, HTML −15–17 % |
| Node 20, `--max-semi-space-size=32/64` | | | | | | ±4 %, +60–120 MiB |
| Node 20, `preloadEntriesOnStart: false` | | | | | | +6 %, −17 MiB |

Node 22 and 24 were first measured on `node:*-alpine` with the same result (−17 %, −32 %), so the gain is not an
artefact of one image.

| 60 home renders in flight at once, 3 waves | CPU per render | Renders per second when saturated |
| --- | --- | --- |
| Node 20 | 49–51 ms | 9.7–10.1 |
| **Node 24** | 28–29 ms | **17.1–17.4 (+72 %)** |

**Where a render's time goes.** A V8 CPU profile of 300 Node 24 home renders, busy time only:

- **Next's compiled server:** 33 %. This is React's Fizz and Flight.
- **Node internals:** 19 %, mostly Web Streams in Next's render pipeline.
- **The app bundle:** 18.5 %.
  - `InventoryService.formatAmount`: 3.9 %. It builds a `new Intl.NumberFormat` for every price of every product on
    every render.
  - JSON parsing of the API responses: 1.3 %.
  - next-intl message lookup: 1.3 %.
- **Garbage collection:** 12.7 %.

Only `formatAmount` is ours to fix; the rest is the framework and the runtime.

**Memory, and why a spike fills it.** V8 sizes its heap from the container. In a 1 GiB container it picks a
`heap_size_limit` of 524 MiB on Node 20 and 560 MiB on Node 24. Under a burst it lets the heap grow toward that limit
rather than collect early. So the working set rises with the allocation *rate*, not with the number of requests held.

The test below proves it. A plain Caddy (as spg) sits in front of one task, and a burst of 300 shoppers arrives at
once, each giving up after 30 s. Anon memory and the working set (what ECS reports) are sampled every 0.2 s.
`max_conns_per_host` holds Node to exactly the cap: 8 established connections for the whole burst, against up to
300 without it. Yet memory and goodput barely move.

| 300 shoppers at once, 30 s patience, 2 rounds | Served | p50 / p95 | Anon idle → max | Working set max | CPU per served page |
| --- | --- | --- | --- | --- | --- |
| Node 20, no cap | 291–297 | 16.2–16.3 / 28.9–29.4 s | 114 → 386–393 MiB | 404–410 MiB | 51–53 ms |
| Node 20, `max_conns_per_host 8` | 288–300 | 15.6–16.2 / 27.6–29.0 s | 110 → 395–399 MiB | 413–417 MiB | 49–54 ms |
| Node 20, `max_conns_per_host 32` | 300 | 17.5–17.7 / 29.6–30.0 s | 112 → 403–409 MiB | 422–427 MiB | 50–51 ms |
| **Node 24, no cap** | **300** | **9.0–9.7 / 15.9–17.3 s** | 143 → 209–210 MiB | **222–223 MiB** | 28–30 ms |
| Node 24, `max_conns_per_host 8` | 300 | 8.5–8.6 / 14.9–15.3 s | 147 → 208–214 MiB | 220–225 MiB | 26–27 ms |

The runtime is what changes a spike: Node 24 halves the burst's latency, serves every shopper and peaks at half the
memory, because the same burst is cleared in half the CPU time. The cap changes neither.

So dev's spike (10 → 59 % of 1 GB, ≈ 600 MiB) is the heap filling toward its limit. It is not a leak and not held
state, and it cannot take a 1 GB task down: the limit plus code and buffers stays under the task's memory. An earlier
reading of "MB per waiting request" divided `memory.peak`, page cache included, by the requests in flight. It is
withdrawn.

## Decisions

- **Node 24 LTS, for the runtime and the build.** It is the largest lever measured:
  - −38 % CPU per render, and +72 % pages per second when the task is saturated;
  - it costs ~30–40 MiB more at idle, which a 1 GB task does not notice.

  Node 20 has been end-of-life since 2026-04-30. The Node landing-ui is *built* with (`node.version = '23.8.0'` in
  `build-logic/.../com.asrevo.ui-conventions.gradle`) has been end-of-life since mid-2025. Distroless publishes
  `gcr.io/distroless/nodejs24:latest` under the same name the mirror already uses for 20. The standalone output
  carries no ABI-bound native module on the render path, so the output of one Node runs on another; the build moves
  to 24 anyway, so the two match.
- **One `Intl.NumberFormat` per locale and currency, not per price.** A module-level cache in `InventoryService`.
  The profile makes it 3.9 % of a home render. The A/B puts it at 4–5 % on home and category pages, the ones with
  many prices, and nothing on the others: −1.2 % overall on Node 20, −4.1 % on Node 24. It ships because it is
  small and safe, not as a lever.
- **landing-ui's server-side calls ask spg for identity encoding.** Node's `fetch` sends `accept-encoding: gzip,
  deflate`. spg's `encode zstd gzip` (the `(routes)` snippet) then gzips every API response on an internal hop,
  and landing-ui inflates it: +4.8 % CPU per render on Node 20, +4.5 % on Node 24, plus spg's own compression CPU.
  A browser's requests are untouched and stay compressed.
- **Memory needs no change.** The heap is bounded by V8's container-derived limit, and a spike's peak is that heap
  filling. The idea this plan started with, spg capping landing-ui's concurrent renders, was built and measured. It
  holds Node to the cap and changes neither memory nor goodput, because Node already serves a burst roughly in
  arrival order. It is not proposed. A 1 GB task is also Fargate's minimum at 0.5 vCPU, so there is no memory to give
  back.
- **Telemetry stays on at 100 %.** It costs 9 % of a render. Trimming the auto-instrumentations recovers 3 %, and
  sampling at 10 % recovers about a third of the cost. Neither is worth the lost traces on dev. A flavour can set
  `OTEL_TRACES_SAMPLER` later without code.
- **Not now:**
  - **The listing payload trim.** It measured as noise on CPU. It is a bytes change (−15–17 % HTML on listing
    pages) and belongs to a page-weight change, not this one. The prototype is `toListingProduct` as a whitelist
    plus the menu tree without SEO copy.
  - **The two V8/Next knobs.** Semi-space tuning and `preloadEntriesOnStart` were both measured and rejected.
- **Out of scope, and the biggest lever left: not rendering the page.** The server render reads no per-shopper
  state. Cookies are read only for the dev/QA theme and colour overrides and on `/login`; cart and customer data
  come from the browser. So an anonymous page is a function of store, theme, colour theme, locale and URL, plus
  catalog data. A short-lived full-page cache would take most renders off the CPU. Where it lives is a decision of
  its own and deserves its own plan:
  - spg, with a Caddy cache plugin, means a saas-gateway rebuild;
  - landing-ui, an in-process cache in `start.mjs`;
  - Next's `cacheComponents`, which means refactoring header-reading pages.
- **Autoscaling is revisited after Node 24 is on dev, not before.** Doubling a task's capacity changes where
  `cpu_target: 55` sits. cvhome-platform then decides between a second minimum task and a step policy for spikes,
  from the new numbers.

## Work items

Order: public-dkr (the image must exist) → cvhome → the person's deploy → the dev verification.

### public-dkr — one PR, `fix/landing-ui-cpu-memory`

1. **Mirror distroless Node 24.** A matrix entry beside `nodejs20`: `registry: gcr.io/distroless`, `image:
   nodejs24`, `tag: latest`. Merging to `main` publishes it to `public.ecr.aws/b2i4h4k9/nodejs24:latest`. That is
   the person's merge, and cvhome's phase 3 waits for it.

### cvhome — one PR, `fix/landing-ui-cpu-memory`, one commit per phase

Each phase is measured with the harness above: CPU per render on four pages, telemetry on, three rounds, distroless.
Each gets a case in the QA file it names.

1. **One currency formatter per locale and currency.** `libs/services/src/inventory-service.ts`: `formatAmount`
   reads a module-level `Map<string, Intl.NumberFormat>` keyed `locale|currency`. An unknown currency still falls
   back to `toFixed(2)`, and a failed construction is not cached. There is a unit test beside the service, and the
   harness numbers go in the commit.
2. **Server-side calls to spg ask for identity.** `libs/services/src/http-utils.ts`: every request built for the
   server (the `INTERNAL_SPG` base) carries `Accept-Encoding: identity`. Verified through the load stack's spg:
   - landing-ui's calls come back without `Content-Encoding`;
   - a browser's API call and a page still come back gzip/zstd;
   - CPU per render moves as measured.
3. **Node 24.**
   - `store-pod/landing-ui/Dockerfile`: `FROM public.ecr.aws/b2i4h4k9/nodejs24:latest`. This waits for public-dkr.
   - Node 24.21.0, the current 24 LTS, wherever the build downloads Node:
     - `build-logic/src/main/groovy/com.asrevo.ui-conventions.gradle`, for console-ui and landing-ui;
     - `store-commons/ui-kit/build.gradle` and `store-core/uaa/build.gradle` (`uaa-fe`), which pin their own.

     Every UI module is rebuilt and checked.
     console-ui's runtime image (`node:20.15.0-alpine`) is also end-of-life. It is named under Deviations and not
     changed here.
   - The QA case in `landing-ui-qa.md` for the storefront's capacity is re-measured on the new image.

Gates: `npm run lint`, `npm run typecheck`, `npm test` in `store-pod/landing-ui`; `./gradlew :store-core:console-ui:check`
for the build-version change; `extra/scripts/verify-before-push.sh`.

### cvhome-platform — no change in this plan

The image name does not change (`store-pod/landing-ui`), so nothing in `services.yaml` moves. The autoscaling
revisit above is cvhome-platform's, after the verification run.

### load-testing — the verification, no change

After the person deploys, run `TARGET=aws STORES=org1-store2` against dev:

- the storefront browse at 30 shoppers;
- the spike with its recovery probe;
- `make aws-report` for ECS CPU, memory and task counts (cvhome-saas/load-testing `feat/perf-detection`).

**Expected:**

- landing-ui's CPU per page falls from ~95 ms to ~55–60 ms: −38 % from Node 24, about −5 % from identity encoding,
  and a little from the formatter.
- Its CPU at 30 shoppers falls under the 55 % target.
- The spike's memory stays under V8's heap limit plus overhead, well inside 1 GB.

The Fargate vCPU is x86, and every ratio here was measured on arm64. If dev shows a materially smaller gain, that is
the first thing to say in the verification.

## Deviations as built

- **Three build pins, not one.** `com.asrevo.ui-conventions` builds console-ui and landing-ui, but
  `store-commons/ui-kit/build.gradle` and `store-core/uaa/build.gradle` (for `uaa-fe`) each pin their own Node
  23.8.0. All three move to 24.21.0, so no module keeps building on an end-of-life Node. Both copies of the
  project-structure docs that quote the version follow.
- **The formatter remembers a rejected code, and its map is bounded.** The plan said a failed construction would
  not be cached. Caching it as rejected is cheaper and just as safe, since `Intl` rejects a code deterministically.
  The bound (256 entries, then start over) exists because the locale comes from the request's route.
- **The identity header sits in `apiFetch`,** the one `fetch` call site, rather than in the request builders. That
  covers all 55 service calls. A caller's own `Accept-Encoding` wins, and the caller's `RequestInit` is not mutated.
- **public-dkr's README** listed 2 of the matrix's 9 images; the PR lists all ten.
- **Found on the way, not fixed here:**
  - `extra/scripts/verify-before-push.sh` runs no landing-ui lint, typecheck or tests, and no CI workflow mentions
    landing-ui. They were run by hand for this PR, as they were for #353 and #356. A gate for them is a follow-up.
  - **landing-ui pins `next` 16.0.0 and `react` 19.2.0.** `npm audit` reports 31 advisories against that `next`,
    including a critical unauthenticated RCE in the React flight protocol (GHSA-9qr9-h5gf-34mp), which the
    storefront's App Router with Server Components is exposed to. It also lists high-severity middleware/proxy
    bypasses; the storefront routes every request through `proxy.ts`. The fixed range starts at `next` 16.3.3;
    `react` 19.2.8 or 19.3.0 is the patched line. This is a separate, urgent upgrade with its own QA, not a line in
    this plan.
  - console-ui's runtime image (`node:20.15.0-alpine`) is end-of-life too. It needs its own mirror entry.

## Verification

- **cvhome PR, measured on production's base image** (distroless, 0.5 vCPU / 1 GiB, telemetry on). The backend
  replay gzips as spg does. Three interleaved rounds, CPU per render in ms:

  | Build | Home | Category | Product | Search | Mean | vs `main` |
  | --- | --- | --- | --- | --- | --- | --- |
  | `main` (Node 20) | 63.4 | 50.5 | 27.3 | 27.0 | 42.0 | — |
  | + formatter | 63.0 | 49.9 | 29.5 | 24.7 | 41.8 | −0.7 % (noise) |
  | + identity encoding | 59.4 | 44.2 | 23.2 | 26.8 | 38.4 | −8.6 % |
  | + Node 24 (the whole PR) | 35.9 | 24.8 | 14.4 | 19.8 | 23.7 | **−43.6 %** |

- **Pages are unchanged.** On every build, the four pages carry the same prices (110 / 70 / 17 / 45) as `main`,
  and the HTML differs only in chunk hashes and the build id. The logs show 0 errors.
- **The identity encoding reaches spg's `encode` line** (a Caddy with that line in front of the backend):
  - before: 24 calls asked for `gzip, deflate` and got gzip;
  - after: 18 asked for `identity` and got it uncompressed;
  - a browser still gets zstd or gzip.
- **The build:** `./gradlew :store-commons:ui-kit:build :store-core:console-ui:build :store-pod:landing-ui:build
  :store-core:uaa:build` succeeds, and each module downloaded `node-v24.21.0`.
- **landing-ui checks:** `npm run lint` shows 0 errors and 4 warnings, all pre-existing in files the PR does not
  touch. `npm run typecheck` is clean. `libs/services` tests pass 9 of 9.
- **Cross-repo:** `scripts/contract-check.py --cvhome <pr> --public-dkr <pr>` is OK, `public-ecr` included. Against
  public-dkr's `main`, `public-ecr` FAILs on `nodejs24:latest`, which is why public-dkr merges first.
- **QA:** landing-ui-qa.md PERF-05 is [verified]. PERF-06 and PERF-07 are split, and their not-verified halves are
  named: the full spg image; the image built on the mirror; dev's x86 Fargate.
- **Not verified:** dev. That is the load-testing verification above, after the person's deploy.
