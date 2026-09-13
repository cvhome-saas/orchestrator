# landing-ui render cost — the storefront saturates its own task

This is the one plan for this fix, in every repo. Every work item is one PR in one repo, on the same branch name,
`fix/landing-ui-render-cost`, except the write-up, which joins the load test that found the problem
(cvhome-saas/load-testing#12). In cvhome, each phase is one commit on one PR, easiest first. QA cases live in
`cvhome/store-pod/landing-ui/qa/landing-ui-qa.md`, never here.

## What was found (2026-09-13)

A load test against dev on AWS (`TARGET=aws STORES=org1-store2 make storefront-browse PROFILE=load PEAK_VUS=30
DURATION=3m`, testid `browse-load-20260913T073013Z`) served 2,442 requests with 0 failures, but every storefront page
had a p95 of 21–24 s against a 3 s SLO. The APIs behind the pages answered with p95 128–644 ms, about 110 ms of which
is the network from the load generator to eu-north-1. The console's store settings screen, tested the same way, passed
every threshold (`store-settings-load-20260913T073725Z`).

CloudWatch (ECS service CPU, one-minute maximum) during the storefront runs:

| Service | CPU | Task |
| --- | --- | --- |
| landing-ui | 97–100 % every minute | one task, 0.25 vCPU / 512 MB, no autoscaling (dev `ui` size) |
| catalog | ≤ 42 % | |
| content, spg | ≤ 19 %, ≤ 15 % | |
| merchant, payment, gateway, tenancy | ≈ 1 % | |

Ruled out: OpenTelemetry (`OTEL_SDK_DISABLED=true` on dev's task definition), errors (82 log lines in 25 minutes),
backend latency.

## Why a render costs so much

landing-ui on cvhome `main` (`23b1b76f4`), built as CodeBuild builds it (`npm install && npm run build`, Next
16.0.0), run in a container capped at 0.25 CPU / 512 MB with its server-side calls going to dev's pod. CPU per render
is the container's cgroup `usage_usec` over 20 sequential renders of each page:

| CPU per render | Home | Category | Product | Search | Weighted as the test |
| --- | --- | --- | --- | --- | --- |
| As built (`inlineCss` on, gzip in Node) | 271 ms | 204 ms | 148 ms | 155 ms | 204 ms |
| `inlineCss` off | 195 ms | 138 ms | 96 ms | 94 ms | 140 ms (−31 %) |
| `inlineCss` off, no gzip in Node | 143 ms | 121 ms | 85 ms | 86 ms | 114 ms (−44 %) |

Dev agrees: 0.25 vCPU × 360 s of saturated CPU ÷ 437 pages served ≈ 206 ms per page. At ~200 ms a page, one quarter
vCPU renders about 1.2 pages a second; the test offered ~1.5, so requests queued (Little's law gives the 17–20 s seen).

The causes, largest first:

1. **Every page carries the CSS of all 12 themes, twice.** `experimental.inlineCss: true`
   (`storefront/next.config.ts:22-24`) inlines the stylesheets, and Next builds the `<style>` elements inside the RSC
   tree (`next/dist/server/app-render/render-css-resource.js:30-36`), so the CSS goes out as HTML and again as
   escaped strings in the flight payload. All themes ship because the registry imports every theme into the
   `[locale]` layout's entry (`themes/registry.ts:10-21`; each theme's `index.ts` imports its `tokens.css` and
   `fonts.ts` calls `next/font`), and Tailwind scans every theme folder (`storefront/src/app/themes.css:5-16`).
   The home page is 864 KiB, 67–79 % of it CSS; with inlining off it is 265 KiB.
2. **Node gzips every page on the same quarter vCPU** (Next's default `compress: true`,
   `next/dist/server/lib/router-server.js:108-111`). spg's Caddy already compresses API responses and deliberately
   passes landing-ui's HTML through (`store-pod/spg/Caddyfile:24-30`).
3. **Nothing is cached between requests.** Every page reads `headers()`/`cookies()` and every fetch is uncached
   (`libs/services/src/http-utils.ts:143`), so the layout re-fetches the store, the category tree and the site
   document on every page (`storefront/src/shell/loaders/layout.ts:18-22`).
4. **The category page loads its data twice.** `generateMetadata` and the page both call
   `loadCategory(url, await query(searchParams))` (`category/[url]/page.tsx:22,32`). `parseListingQuery` returns a
   new object each time, and React `cache()` compares arguments by identity, so the memo misses and the listing,
   facets, inventory merge and price formatting all run twice.

A CPU profile of 30 home renders agrees: of the busy time, React rendering and flight serialisation take ~19 %,
garbage collection ~19 %, app code ~14 %, gzip ~11 %, streams/encoding/escaping ~15 %. GC and escaping scale with
the bytes produced.

## Decisions

- **`inlineCss` off, not a per-theme CSS split.** Turning inlining off removes the CSS from every render: it is
  served as static, cacheable stylesheet files (13 links on the home page). Shipping only the store's own theme CSS
  would also shrink what a browser downloads on a first visit, but it needs every theme's CSS and fonts moved out of
  the JS module graph and Tailwind built per theme. It no longer affects server CPU once inlining is off, so it is a
  separate, browser-side follow-up. The trade-off: stylesheet links are render-blocking on a first visit, which is
  why `inlineCss` was turned on (the `next.config.ts` comment cites Lighthouse).
- **Compression moves to spg's Caddy.** `compress: false` in Next; spg's `encode zstd gzip` then compresses the HTML
  (it already skips only responses that carry `Content-Encoding`). Caddy flushes responses without a
  `Content-Length` immediately, and the encoder flushes with them, so Next's streamed HTML stays streamed. spg
  idled at ≤ 15 % CPU in the test.
- **The three layout reads are cached across requests for 30 s.** `StoreService.getStore`,
  `CategoryService.getCategories` and the content `site` document use `get()` without `{auth: true}`, which on the
  server never carries a credential (`http-utils.ts:209-211`), and their URLs carry `store=` and `lang=`. Next's
  fetch cache keys on the URL, so one store's data cannot reach another. A merchant's edit to the store record,
  the category tree or the site document shows on the storefront within 30 s instead of immediately. Nothing else is
  cached: product, listing, search, inventory and page content stay per request.
- **A storefront size of its own.** The `ui` size is shared with console-ui, which idled at 0–5 % CPU. A new `ssr`
  size gives the storefront CPU without paying for the console.

## Work items

### cvhome — one PR, `fix/landing-ui-render-cost`, one commit per phase

Each phase is measured with the 0.25-CPU render harness above (CPU per render, all four pages, gzip and none) and
gets a case in `store-pod/landing-ui/qa/landing-ui-qa.md`.

1. **The category page loads its data once.** Memoise on a stable key: `loadCategory(url, queryString)` with the
   `ListingQuery` parsed inside the cached function, so `generateMetadata` and the page share one call.
   Files: `storefront/src/app/(storefront)/[locale]/category/[url]/page.tsx`, `storefront/src/shell/loaders/category.ts`.
2. **Stylesheets as files, not inlined into every page.** `experimental.inlineCss: false`, with the comment
   rewritten to say why (the measured cost) and what it costs (render-blocking links on a first visit).
   File: `storefront/next.config.ts`.
3. **spg compresses the storefront's HTML, not Node.** `compress: false` in `storefront/next.config.ts`; the
   `store-pod/spg/Caddyfile` comment at lines 24-27 updated to say Caddy now compresses landing-ui's HTML. Verified
   through spg: `Content-Encoding: gzip` from Caddy with `Accept-Encoding: gzip`, identity without, and the home
   page's first bytes (the `loading.tsx` skeleton) arriving as early as before.
4. **The store, the category tree and the site document are fetched once per store every 30 s.** A
   `publicCachedGet(seconds)` beside `publicGet()` in `libs/services/src/http-utils.ts` returning
   `{method: 'GET', headers: {}, next: {revalidate: seconds}}`, used by those three reads only
   (`store-service.ts`, `category-service.ts` `getCategories`, `content-service.ts` site). Verified: two renders
   within 30 s make one backend call for each; a different store gets its own data.

Gates: `npm run lint`, `npm run typecheck`, `npm test` in `store-pod/landing-ui`; `extra/scripts/verify-before-push.sh`.

### cvhome-platform — one PR, `fix/landing-ui-render-cost`

1. **An `ssr` size, and autoscaling for landing-ui everywhere.** In `flavours.yaml`, a new `ssr` size in all four
   flavours: dev `{cpu: 512, memory: 1024}` (from the `ui` 256/512 it used), staging and prod `{cpu: 512, memory:
   1024}` (what `ui` gives them today), ephemeral `{cpu: 256, memory: 512}` (unchanged). In `services.yaml`,
   landing-ui takes `size: ssr` and `autoscaling: {enabled: true, cpu_target: 55, memory_target: null}`: dev and
   ephemeral scale 1–3 tasks (the modules' `desired_count × 3` ceiling), staging and prod keep their flavour's
   min/max. `cpu_target: 55` is prod's own target; server-side rendering queues well before 75 %. Dev runs on Spot.

Gates: `terraform fmt -recursive -check`, `terraform validate` per root/module, `tflint --recursive`,
`python3 scripts/check-catalog-drift.py`.

### load-testing — cvhome-saas/load-testing#12

The write-up in `docs/monitoring/performance-improvements.md`: the finding, the method (the 0.25-CPU render
harness and the CloudWatch reading), and per fix the cause, the change and the measured effect.

## Order, release and clean-up

The cvhome and cvhome-platform PRs are independent and can land in either order. Nothing here deploys: CodeBuild
builds the images from cvhome and Terraform applies cvhome-platform, both run by the owner. After both are deployed,
re-run the dev test (`TARGET=aws STORES=org1-store2 make storefront-browse PROFILE=load PEAK_VUS=30 DURATION=3m`)
and record it in load-testing's baseline. Remove the worktrees once the PRs merge.

## Not in this plan

- Per-theme CSS (see Decisions).
- Smaller costs the analysis found: a new `Intl.NumberFormat` per amount (`libs/services/src/inventory-service.ts:173`),
  the whole locale file and full product objects serialised into the RSC payload.
