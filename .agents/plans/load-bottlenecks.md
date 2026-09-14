# Where cvhome breaks — the nine bottlenecks of the heavy spikes, fixed

This is the one plan for this change, in every repo. Every work item is one PR in one repo, on the same branch name,
`fix/load-bottlenecks`. In cvhome, each phase is one commit on one PR, easiest first, so any one fix can be reverted
alone. QA cases live in each service's `qa/<svc>-qa.md`, never here.

The findings are the load-test report *Where cvhome Breaks* (artifact
`https://claude.ai/code/artifact/6a901437-b6d9-4b55-b186-a360eff4d46b`, 2026-09-14, cvhome `main` at `c0f7ea358`),
whose numbers go into load-testing `docs/baseline.md` → *Heavy spikes* on the report's own branch
`docs/heavy-spike`. It follows [`landing-ui-cpu-memory.md`](landing-ui-cpu-memory.md), which put landing-ui on
Node 24 and left the full-page cache as "the biggest lever left".

## What the spikes showed

Every service at its dev Fargate size (CPU × 0.45 on the load stack), a one-minute spike of 300 and then 500
shoppers with Chromium measured before, during and after, then the production mix at 20× a normal day. Postgres never
passed 11 % CPU: none of these limits is the database server.

| # | Bottleneck | Evidence | Owner |
|---|---|---|---|
| 1 | landing-ui CPU: every page rendered per request | at its cap for 2m15s at 5×; home median 42 s; 4.4 % hit the 60 s timeout; ~7 pages/s per 0.5 vCPU at 70 ms a render | landing-ui, platform |
| 2 | checkout's pool: cart transactions hold a connection across HTTP calls | 3/3 held, 199 waiting, 2,562 timeouts after 30 s; 94 % of purchases failed in the mix | checkout |
| 3 | catalog CPU: facets on every search, Criteria plans recompiled, fetch joins ~20 rows a product, no cache | 79 % of cap at 3×, 91 % at 5×, 90 s at 100 % in the mix; a search is 9.8 statements, ~83 ms JVM, 6.6 ms SQL | catalog |
| 4 | catalog's pool: open-in-view holds the connection until the response is serialised | 135 waiting while Postgres idled | catalog, platform |
| 5 | missing indexes, full scans, duplicate uniques | `product_image` 59k full scans / 53.2M rows; `inventory.product_price` 94 % full scans | catalog, inventory DDL |
| 6 | N+1 outside catalog | admin orders list 42 statements; placing an order 22; content site 12; inventory bulk 21 for 20 SKUs | checkout, content, inventory |
| 7 | no timeouts, no load shedding | landing-ui at its cap 53–75 s after the spike; spg 69 × 502 | all services, landing-ui |
| 8 | uaa sign-ins: bcrypt on a quarter vCPU | 61–72 % of cap in the mix; 1.8 s Fargate CPU a sign-in; p95 5.6 s | uaa, platform |
| 9 | connection budget at scale-out | prod: 11 services × 12 tasks × 6 = 792 pooled connections against ~190 on db.t4g.small | platform |

## Decisions

- **The full-page cache lives in landing-ui's `start.mjs`** (the person chose it, 2026-09-14). The server render reads
  no per-shopper state: store, theme and languages come from spg's headers, the locale from the URL, and cookies only
  for the dev/QA theme and colour overrides (`proxy.ts`, `get-theme.ts`, `merchant-tokens.ts`) and on `/login`. So a
  GET with no cookie that changes the render is a function of host, spg's store headers and URL. The entrypoint
  serves it from an in-process cache: 30 s fresh, then stale-while-revalidate, a bounded size, never a response with
  `Set-Cookie` or a non-200, never a request with an override cookie, an `Authorization` header or a non-GET method.
  `STOREFRONT_PAGE_CACHE_TTL_SECONDS=0` turns it off. Each task warms its own copy; a catalog edit shows within the TTL.
  The alternatives were Next's `cacheComponents` (the store id into the `/t` path and every header-reading page
  refactored, across twelve themes) and a Caddy cache plugin in saas-gateway (four repos). Neither is done.
- **No 503 shedding at spg** (the person chose it). `landing-ui-cpu-memory.md` measured a render cap without refusal
  and it changed nothing; refusing would fail shoppers the cache can now serve. Instead a render stops when its shopper
  disconnects (the request's abort reaches every backend `fetch`), and every backend call has a 3 s budget.
- **No RDS Proxy.** The budget is met by arithmetic: a per-service pool (catalog 8, the rest at the flavour's
  default) and a cap on the tasks each database service may scale to, checked at max scale-out, not only mid-deploy.
  landing-ui has no database and keeps scaling to 12. RDS Proxy (~$22/month at prod's size) stays the next step if the
  caps bind.
- **Fail fast instead of queueing:** Hikari waits 3 s, not 30 s, on Fargate; every `RestClient` has a 1 s connect and
  3 s read timeout. A spike then produces quick errors that recover, not minutes of queue.
- **`ddl-auto: validate`.** `schema.sql` owns the schema (`AGENTS.md`), and `update` added a second copy of
  `product_variant`'s two unique indexes. The pre-release database may be dropped and recreated
  (no migration is written). If a service's entities do not validate against its own `schema.sql`, the mismatch is
  fixed in that service, not hidden by `update`.
- **Verification is per fix, then per spike.** A statement count per route is a property of the code, so each SQL fix
  is proven by an integration test that counts statements (and by traces on the worktree's lcl stack), not by a load
  run. Load numbers are re-measured on the load-testing stack after the person builds the images from this branch
  (images are their pre-step; this plan never builds them).

## Work items

Order: cvhome and cvhome-platform are independent and run in parallel (the platform only sizes and budgets; it reads
no new env var the app does not already take). Then the person builds the load stack's images from cvhome
`fix/load-bottlenecks`, and load-testing re-measures.

### cvhome — one PR, `fix/load-bottlenecks`, one commit per phase

Paths are relative to `cvhome/`. Every phase runs the touched modules' `test` and `integrationTest`;
`extra/scripts/verify-before-push.sh` runs once on the final tree.

1. **Hibernate and JPA defaults** — `store-commons/autoconfigure/src/main/resources/common-config.yml` `spring.jpa`:
   `open-in-view: false`; `properties.hibernate.default_batch_fetch_size: 50`;
   `hibernate.criteria.plan_cache_enabled: true`; `hibernate.query.in_clause_parameter_padding: true`;
   `hibernate.jdbc.batch_size: 50`, `order_inserts: true`, `order_updates: true`. In tests,
   `hibernate.query.fail_on_pagination_over_collection_fetch: true`, so HHH90003004 fails a build. Every service's
   integration tests must pass with open-in-view off: a `LazyInitializationException` is fixed where it is thrown
   (map inside the transaction), never by turning it back on. *(findings 3, 4, 2; batches `Category.parent`, order
   totals and inserts)*
2. **Fail fast** — `fargate-config.yml`: `spring.datasource.hikari.connection-timeout: 3000`. The shared
   load-balanced `RestClient.Builder` (`store-commons/…/WebClientServicesConfig.java:132–142`) and checkout's own
   (`store-pod/checkout/…/ClientsConfig.java:41–50`) get a request factory with a 1 s connect and 3 s read timeout,
   from properties in `common-config.yml`. *(findings 2, 7)*
3. **A bounded `STORE` cache** — `common-config.yml` `spring.cache.caffeine.spec`: `maximumSize` and
   `expireAfterWrite` beside `recordStats`. *(finding 3)*
4. **Indexes, and `schema.sql` owns the schema** — `store-pod/catalog/catalog-service/src/main/resources/init-sql/schema.sql`:
   `product_image (product_id)`, `category_description (sef_url, language_code)`,
   `category (store_merchant_id, lineage varchar_pattern_ops)`, `product (store_merchant_id, manufacturer_id)`,
   `product (product_type_id)`, `product_group_product (product_id)`; inventory's `schema.sql`:
   `product_price (product_avail_id)`. `ddl-auto: validate` in `common-config.yml`, and whatever does not validate is
   fixed in its entity or DDL. Proven with `EXPLAIN` on a seeded store. *(finding 5)*
5. **Inventory bulk in one read** — `/api/v1/private/inventory/bulk`: one `WHERE sku IN (…)` instead of a read per
   SKU. An integration test counts the statements. *(finding 6)*
6. **Checkout's cart holds no connection across HTTP** — `store-pod/checkout/checkout-core/…/services/cart/CartServiceImpl.java`
   (`create`, `upsert`, `get`, `removeLine`): the catalog + inventory snapshot
   (`…/services/catalog/ProductSnapshotServiceImpl.java:33–40`) is taken before the transaction opens; the cart write
   is a short transaction of its own; `get` is read-only and saves nothing. A test proves no connection is held while
   the snapshot runs. *(finding 2)*
7. **Checkout's orders** — `OrderServiceImpl.list` stops calling `customerOf` per row when `detail=false`, and totals
   and lines load in batches (phase 1's batch size, `@BatchSize` where a collection needs it); `listForShopper`
   the same; placing an order reuses the order it loaded instead of re-reading `sales_order` four times.
   Integration tests pin the statement counts (admin list 42 → ≤ 5). *(finding 6)*
8. **Content's storefront reads** — `StorefrontApi` `/api/v1/storefront/site` loads each content type in one query;
   layout, menu and site are read-only transactions behind a Caffeine cache keyed by store and language, evicted when
   an editor publishes. *(finding 6)*
9. **Catalog pages categories in SQL** — `CategoryRepository` (`:43, :48`) and `ManufacturerRepository` (`:24, :29`)
   drop `left join fetch …descriptions` from paged queries; `@BatchSize` loads them. *(finding 3, HHH90003004)*
10. **A facets-only search** — `ProductSearchServiceImpl.runSearch` (`:125`): `count=1&facets=true` skips the page,
    `COUNT` and hydrate. ~18 statements → ~3 per category render. *(finding 3)*
11. **Fetch joins that do not multiply** — `ProductRepository` (`:27–49`, `:63–70`): fetch only to-one associations;
    descriptions and images load by `@BatchSize`. *(finding 3)*
12. **Store units once per request** — `ProductMapper` (`:148–162`): the units lookup is resolved once per mapping
    call, not through a SpEL-keyed `@Cacheable` per product. *(finding 3)*
13. **Catalog response caches** — Caffeine caches for the DTOs of groups, category hierarchy, category by URL,
    manufacturers, product by URL, suggest and facets, keyed by store, language and arguments; 30–60 s TTL and a
    `maximumSize`; evicted per store on the catalog's change events. Price and stock come from inventory and are not
    cached here. *(finding 3)*
14. **landing-ui stops work nobody waits for** — `start.mjs` ties an `AbortController` to each request's close and
    keeps it in `AsyncLocalStorage`; `libs/services`' `apiFetch` combines that signal with `AbortSignal.timeout(3000)`.
    A render for a shopper who left stops at its next backend call; a slow backend fails a call in 3 s.
    *(findings 1, 7)*
15. **landing-ui serves anonymous pages from a cache** — `start.mjs` as decided above; a unit-tested module next to it
    (key, admission rules, TTL, SWR, size bound), headers `x-storefront-cache: hit|miss|stale`. *(finding 1)*

QA: each phase adds or updates a case in the owning service's `qa/<svc>-qa.md` (catalog, checkout, content,
inventory, landing-ui), tagged `[verified]` with what verified it.

### cvhome-platform — one PR, `fix/load-bottlenecks`

1. **uaa off a quarter vCPU** — uaa sized at ≥ 0.5 vCPU in every flavour (`services.yaml`, a size in `flavours.yaml`
   if none fits). *(finding 8)*
2. **The storefront gets 1 vCPU in prod** — `flavours.yaml` `prod.sizes.ssr: { cpu: 1024, memory: 2048 }`.
   *(finding 1)*
3. **A pool per service** — `services.yaml` may set a service's own Hikari pool (catalog 8); the flavour's
   `rds.db_pool_size` stays the default. `modules/store-core/main.tf:118` and `modules/store-pod/main.tf:125` pass the
   service's value. *(finding 4)*
4. **The budget holds at max scale-out** — database services get an autoscaling ceiling of their own (prod: catalog 4,
   the rest 2); landing-ui keeps 12. `main.tf`'s check (`:122–186`) counts every database service's pool × its maximum
   tasks, plus a rolling deploy's doubling, against the instance's limit. *(finding 9)*
5. **Pre-scaling for campaigns** — a worked `schedules` example in `prod` that raises the floor for a known event,
   commented out. *(finding 9)*

Gates: `terraform fmt -recursive -check`, `terraform validate` per root/module, `tflint --recursive`,
`python3 scripts/check-catalog-drift.py` (`APP_REF=fix/load-bottlenecks`).

### load-testing — after the person builds the images

The report's own branch, `docs/heavy-spike` (two commits, not yet pushed), goes first. Then on `fix/load-bottlenecks`:

1. **Sizes and pools follow the platform.** Re-run `scripts/sync-fargate-sizes.mjs` against cvhome-platform
   `fix/load-bottlenecks` (uaa moves to `auth`, prod `ssr` to 1 vCPU), and teach it a service's own `db_pool_size`, so
   the load stack runs catalog at 8 like dev will.
2. **Re-measure.** The 3× and 5× browser spikes, the production mix × 20 and the SQL-per-route sample, on the load stack
   built from cvhome `fix/load-bottlenecks` (JVM images, and landing-ui's image, whose `start.mjs` now carries the page
   cache). Add *After the fixes* beside *Heavy spikes* in `docs/baseline.md`: CPU per container against its cap, SQL per
   route, pools, and what shoppers saw. Read `x-storefront-cache` in the storefront journeys: a browse journey that
   repeats pages will mostly hit, so say which numbers are cache hits.

## Deviations as built

### cvhome (`fix/load-bottlenecks`, 17 commits: the 15 phases, one inventory fix, one test fix)

- **Phase 1 surfaced three bugs open-in-view had hidden**, fixed in the same commit, all found by the integration
  tests: checkout's `OrderSignalServiceImpl.applyPayment/applyExpiry` were `@Transactional` methods called from their
  own class, so they ran with no transaction at all (now a `TransactionTemplate`); `OrderStepRunner` kept its
  pre-refusal copy of an order after a payment refusal, so the RELEASE waited for the recovery job; merchant's
  `StoreFacadeImpl` had no transactions and handed DTOs the entity's lazy collections.
- **Phase 2:** Hikari's 3 s wait is in `common-config.yml`, not `fargate-config.yml`, so the load stack (lcl profile)
  measures what Fargate runs. payment gets a 10 s read timeout (it waits on Stripe; an unanswered initiate already
  means "nothing was decided" to checkout). checkout's `ClientsConfig` needed nothing: every client comes from
  `RestClientBuilder`.
- **Phase 4:** eight Hibernate-generated duplicate unique constraints in catalog, not two, plus content's `code_idx`;
  `schema.sql` drops them. Every service validates against its DDL. The outbox duplicates the load database holds
  (uaa, cua, payment, catalog) come from an old library schema init, not from this repo, and a fresh database does not
  get them.
- **Phase 5** added `SqlStatements` to test-support (a thread-scoped Hibernate `StatementInspector` every JPA test
  annotation registers), which phases 7–13 pin their counts with.
- **Phase 6 fixed placement too:** `OrderPlacementTransaction.createOrResume` priced the cart inside its transaction,
  the same flaw as the cart. `get` writes only when a line has to be pruned, so placement never refuses a line the
  shopper was not shown.
- **Phase 7:** placing an order still reads the order once per step; that is `OrderStepRunner`'s design (a fresh load
  in a short transaction per remote step).
- **Phase 8:** content's site N+1 is left; the site, layout and menus are cached for 10 s instead (inside the
  responses' own `max-age=60`), and any content write clears the cache.
- **Phase 9** found four paged fetch joins (categories and brands, by store and by name) and one `limit` over a fetch
  join in inventory's `findBySku`, fixed in its own commit when the new test guard
  (`fail_on_pagination_over_collection_fetch`) caught it.
- **Phase 10 went further than planned:** `facetGroups` as well as `rows=false`, because the category rail draws only
  the option facets. 17 statements → 4.
- **Phase 12:** the store lookup lost its SpEL key instead of the mapper threading the store through every call; a
  lookup is now a map read.
- **Phase 13:** the post-commit eviction listener moved into store-commons (`EntityCommitCacheEviction`), shared by
  content and catalog. It also handles collection-only changes (a product added to a group), which Hibernate reports
  as a flush-time collection event, clearing after commit.
- **Phase 14:** `start.mjs` wraps the listener of the `http.Server` Next's `startServer` creates (one synchronous
  `createServer` call, patched for that call only), rather than replacing `startServer`. Writes get no time budget.
- **QA** cases went into each service's QA file in one closing commit, after the lcl run, not per phase.

### cvhome-platform (`fix/load-bottlenecks`, 5 commits)

- uaa gets a size of its own, `auth` (0.5 vCPU / 1 GB in every flavour), not `medium`, which would have given prod
  1 vCPU / 2 GB.
- The budget is enforced per flavour with `rds.db_max_tasks` (dev 1, staging 2, prod 2, ephemeral 1) and a service's
  `max_factor` (catalog 2, so 4 tasks). The scaling arithmetic moved from the two modules into the root so the check
  counts what is deployed. Peak pooled connections: dev 76/~80, staging 104/~190, prod 176/~190 (was up to 504 for one
  prod pod).
- **Follow-up for load-testing:** `scripts/sync-fargate-sizes.mjs` must be re-run after this merges (uaa → `auth`,
  prod `ssr`), and it copies only the flavour-wide pool, so the load stack keeps catalog at 3 until it learns
  `db_pool_size`.

## Verification

### cvhome

- Every phase: the touched modules' checkstyle, unit and integration tests; the whole `./gradlew integrationTest` after
  phases 1, 4 and 9 (the global changes).
- Statement counts pinned by integration tests: inventory bulk upsert of 20 skus 21 → 1 select; the console's order
  list 42 → ≤ 3; the category rail 17 → ≤ 4; a cached site/layout/menu or group/tree/suggest read 0, and a write sends
  the next read back to the database. Each new assertion was run against the old code and failed there.
- Checkout: the integration tests' catalog and inventory stubs record whether a transaction is open when they are
  called; through a cart's life and a card placement it never is (with the old code, both fail).
- Indexes: a throwaway Postgres 15 (en_US.utf8) with both `schema.sql` files and a synthetic 20k-product catalogue;
  every hot lookup plans an index scan on its new index.
- landing-ui, on this branch's production build: a shopper who leaves at 1 s aborts the render's four backend calls
  at 929 ms; each slow read is aborted at 3.0 s. Against the load stack's backend, a 223 KB home page: miss 156 ms, hit
  ~1 ms, the same bytes; 100 views cost 40 ms of CPU cached against 1,650 ms uncached; 20 shoppers on a cold page cause
  one render. libs/services 13/13, storefront 22/22, typecheck clean, lint 0 errors.

- **lcl stack `lb`** from this branch, with landing-ui's production build swapped in for `next dev`: every Java service
  boots under `ddl-auto: validate`; 24 shopper checks through spg pass (the page cache's miss/hit/bypass and spg's gzip
  on a hit, the category rail, the tree, the product page and another store's 404, the merchant store, the content
  reads, a cart, a refused over-maximum update that writes nothing, a guest COD order CONFIRMED with its stock
  COMMITTED, the spent cart's 409). The console's paths were not driven in a browser; their integration suites cover
  them through HTTP.
- `extra/scripts/verify-before-push.sh` on the final tree: see the PR.
- Cross-repo: `scripts/impact.py cvhome` names no moved contract (no service, port, route, env var or telemetry change;
  the search's two new parameters are optional); `scripts/contract-check.py` with both branches substituted: every
  check OK, the warnings pre-existing.

### cvhome-platform

- `terraform fmt -check`, `terraform validate` (root, `prereq`, five modules), `check-catalog-drift.py` (no drift),
  `scripts/verify.sh` green; the budget arithmetic read from `terraform console`. tflint and cfn-lint are not installed
  here and did not run.
