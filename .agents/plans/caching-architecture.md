# Caching architecture — `:store-commons:cache`, one library for every service

The one plan for this change, in every repo (cvhome carries the code, load-testing the dashboard docs). Each cvhome PR
lists its phases; a phase is one commit.

## Context

The load-bottlenecks work proved that response caches are what keep catalog, content and checkout under their
CPU caps (failed requests 6.5% → 2.8% on warm JVMs). It also produced the caches the wrong way: PR #364
(`perf/storefront-caches`) has four copies of `CacheConfig`, three copies of `CachedExternalMerchantStoreService`,
three incompatible cache APIs (`@Cacheable`, `CacheManager → native Caffeine getAll` with unchecked casts, raw
Caffeine fields), string-literal cache names, TTLs as compile-time constants, an eviction listener that registers
itself in its constructor and scans every key on every write, entity→store resolution as a 16-arm `switch` per
pod where a missed arm clears every tenant, and no way to move a cache to another provider.

The user wants one architecture for caching across the application: standard Spring annotations, Micrometer,
configurable TTL and provider per cache (Caffeine now, Redis for some caches later), typed key building
(store+lang, store+lang+sku, product id, variant id), eviction on commit, refresh events through the outbox
with the cross-service transport left as a port, and clear naming of what is cached and where.

**Decisions taken with the user:** Caffeine now with a provider per region from config; cross-service refresh
via typed outbox events with a pluggable transport (no-op/logging now); PR #364 is superseded and closed; typed
ids `ProductId`, `CategoryId`, `ManufacturerId`, `VariantId` are minted; Spring `@Cacheable` on our own
`CacheManager` rather than a custom annotation; regions declared as one enum per service in `-core`.

Starting point: cvhome `origin/main` (has the Java load fixes and the uncached `GET /api/v1/cart-lines`).
`SqlStatements` from the load branch is on main (test-support). Nothing from #364 is merged.

## Design

### Module `:store-commons:cache` (`store-commons/cache`, package `com.asrevo.cvhome.cache`)

```
CacheRegion            interface: name(), valueType(), ttl(), maxSize(), scope() (STORE | GLOBAL)
CacheRegions           record over List<CacheRegion>: the per-service bean
CacheKey               record(StoreMerchantId store, LanguageCode language, List<Object> parts) + factories, render()
KeyPart                marker interface (in commons/domain): String cacheKeyPart()
QueryHash              record(String sha256) implements KeyPart; of(String normalised)
StoreScopedKeyGenerator   Spring KeyGenerator bean "storeScopedKeys": typed params → CacheKey; refuses ShopperId,
                       CustomerId, raw Long/String ids, mutable criteria; requires a StoreMerchantId unless GLOBAL
RegionCache<V>         port: getIfPresent, get(key, loader), getAll(keys, bulkLoader), put, evict, evictAll,
                       evictStore(store) [O(1) version bump], clear, stats()
CacheProvider          port: name(); <V> RegionCache<V> create(RegionSpec)
CaffeineCacheProvider  the only provider now; NoOpCacheProvider for enabled=false (still metered)
StoreVersions          per-region ConcurrentHashMap<StoreMerchantId, AtomicLong>; a Redis provider does INCR
CacheRegistry          resolves CacheRegion → RegionCache by CacheProperties at run time (memoised)
CvhomeCacheManager     implements org.springframework.cache.CacheManager: getCache(regionName) → RegionSpringCache
RegionSpringCache      implements org.springframework.cache.Cache over RegionCache (get/put/evict/clear/nativeCache)
RegionCacheMeterBinderProvider   CacheMeterBinderProvider<RegionSpringCache> → Boot's CacheMetricsAutoConfiguration
                       binds cache_gets_total{cache,result}, cache_puts_total, cache_evictions_total, cache_size
eviction/StoreScoped   interface in commons/domain: StoreMerchantId scopedStore()
eviction/EvictionRules builder bean per service: entity classes → regions; onEvent(EventType) → regions
eviction/CacheEvictionIntegrator   Hibernate Integrator via HibernatePropertiesCustomizer (no self-registration)
eviction/CommitEvictionListener    post-commit insert/update/delete + collection callbacks on success only
eviction/EvictionRulesValidator    SmartInitializingSingleton: unmapped entity → WARN, mapped but not StoreScoped → fail
eviction/AfterCommitEviction       evictStoreAfterCommit(store, regions) for bulk JPQL / native refresh
event/CacheEvent       sealed: ProductChanged, VariantChanged, CategoryChanged, ManufacturerChanged, StockChanged,
                       PriceChanged, StoreChanged, ContentChanged (records, @OutboxEvent(key = store))
event/CacheEventOutboxHandler      @OutboxHandler per type → CacheEventApplier (local evict) + CacheEventTransport
event/CacheEventTransport          port: publish(CacheEvent); LoggingCacheEventTransport is the default bean
config/CacheProperties @ConfigurationProperties("com.asrevo.cvhome.cache")
config/CacheAutoConfiguration      @Configuration @ConditionalOnClass(Caffeine) @EnableCaching; own
                       META-INF/spring/…AutoConfiguration.imports (not CvhomeSharedConfig: gateway/uaa must not load it)
```

Beans always exist; switches (`enabled`, `provider`, `ttl`) are read inside `CacheRegistry` at run time, the
pattern of `MetricsAutoConfiguration.outboxMetrics` (never `@ConditionalOnProperty`, which the build forbids).
Optional beans use `@ConditionalOnClass` (Hibernate integrator, outbox handler, meter binder) and
`@ConditionalOnMissingBean` (transport).

### Keys

```java
CacheKey.of(store)                       merchant.store, payment.types
CacheKey.of(store, lang)                 content.site; .with(pageable), .with(MenuHandle)
CacheKey.sku(store, sku)                 inventory.sku (no language)
CacheKey.sku(store, lang, sku)           catalog.cart-line, catalog.detailed-product
CacheKey.product(store, lang, ProductId) catalog.related
CacheKey.variant(store, lang, VariantId) reserved for variant reads
CacheKey.slug(store, lang, slug)         catalog.category, catalog.product, content.page
CacheKey.query(store, lang, QueryHash)   catalog.listing/search, content.posts; .with(pageable)
CacheKey.global(lang)                    checkout.country (scope GLOBAL, sentinel store "*")
render() → "store|lang|part|part"       the Redis key form
```

Allowed parts: `KeyPart`, `String`, `Integer`, enums, `Pageable` (normalised `p<page>s<size>:<sort>`). Refused with
an exception naming the type: `Long`, `ShopperId`, `CustomerId`, `ProductFilter`, `ProductSearchCriteria`. The
criteria classes gain `String normalised()` and the facade keys them with `QueryHash.of(normalised)`; suggest
normalisation (lower, trim, cut at 64) moves inside the facade method so no caller has to remember.

**Per-store eviction is a version bump, not a key scan.** `CaffeineRegionCache` stores entries under
`VersionedKey(key, storeVersion)`; `evictStore(store)` increments the store's counter for that region; old
entries die by TTL or size. One reason: it is O(1) on every provider (Redis: one INCR) and needs no key index.
Consequence to document: `cache_evictions_total` counts provider evictions only, not store bumps.

### Configuration (`common-config.yml`, replacing `spring.cache.*`)

```yaml
com.asrevo.cvhome.cache:
  default-provider: caffeine
  regions:
    merchant.store-client: { ttl: 5m, max-size: 10000 }
# a service overrides by region name in its application.yml:
com.asrevo.cvhome.cache.regions:
    catalog.listing: { ttl: 60s, max-size: 5000 }
    catalog.suggest: { enabled: false }
    catalog.product: { provider: redis }   # later; an unknown provider fails start-up
```

`CacheProperties(String defaultProvider, Map<String, Region> regions)`, `Region(provider, ttl, maxSize, enabled)`.
Code defaults come from the enum; YAML wins. `spring.cache.cache-names` / `caffeine.spec`, the per-service
`@EnableCaching` and `spring-boot-starter-cache` declarations go away (the library brings the starter).

### Eviction flow (same task)

```
save Product → POST_COMMIT_UPDATE → EvictionRules.regionsFor(Product) = [catalog.product, listing, search, related,
cart-line, detailed-product, group] → store = ((StoreScoped) entity).scopedStore() → registry.evictStore(store, regions)
collection change → callback on session.getTransactionCompletionCallbacks(), runs only on success
bulk JPQL / native search-index refresh → AfterCommitEviction.evictStoreAfterCommit(store, regions)
```

`EvictionRules.in("com.asrevo.cvhome.catalog.entity").on(Product.class, ProductDescription.class, ProductImage.class,
ProductVariant.class, ProductVariantOptionValue.class).evict(PRODUCT, LISTING, …).on(Category.class, …).evict(HIERARCHY,
CATEGORY, LISTING, BRANDS)…`. Descriptions and option values implement `StoreScoped` by delegating to their owner.
The validator walks the metamodel: an unmapped entity logs one WARN and evicts nothing (never a global clear).

### Refresh events (PR 4)

```
aggregate.registerEvent(new ProductChanged(store, productId))  → outbox row in the same transaction
→ CacheEventOutboxHandler (one replica) → CacheEventApplier.apply(event)  (local evict by EvictionRules.onEvent)
                                        → CacheEventTransport.publish(event)
LoggingCacheEventTransport  now
HttpFanOutCacheEventTransport  later: POST /internal/cache-events to each consumer's replicas via the discovery client
BrokerCacheEventTransport  later: RabbitMQ / Redis pub-sub, every replica subscribes and calls the applier
Shared cache  later: the applier's REFRESH mode reloads and puts instead of evicting; publish becomes a no-op
```

The receiving endpoint `POST /internal/cache-events` is designed in `caching.md` (s2s scope, body polymorphic
by `eventType`) and not built in this plan. Consumers map foreign events with the same builder:
`rules.onEvent(StockChanged.class).evict(...)`.

### What is cached

| Service | Region | Key | TTL | Evicted by | Facade |
|---|---|---|---|---|---|
| catalog | catalog.hierarchy, .category, .brands, .group, .related, .product, .listing, .search, .suggest | see keys | 60 s | Category*, Manufacturer*, ProductGroup*, Product*, ProductVariant*, ProductOption* | `StorefrontCatalogReads` |
| catalog | catalog.cart-line, catalog.detailed-product | sku(store, lang, sku), bulk getAll | 60 s | Product*, ProductVariant* | `CartLineReads` (programmatic) |
| content | content.site, .layout, .menu | of(store, lang) (+PageKind / MenuHandle) | 10 s | SiteSettings, PolicyVersion, Menu*, Content*, PageLayout, SectionPreset | `StorefrontReads` |
| content | content.page, .post, .posts, .post-categories, .banners, .faq, .policy, .sitemap, .redirects | slug / query / of(store, lang) | 60 s | Content*, ContentRevision, PostCategory, FaqGroup, Redirect, PolicyVersion | `StorefrontReads` (preview requests bypass) |
| inventory | inventory.sku | sku(store, sku), bulk | 5 s | Inventory, InventoryPrice; reservation commit `evictAll(skus)` | `SkuInventoryReads` in inventory-core, behind GET and POST availability |
| merchant | merchant.store | of(store) | 5 min | MerchantStore + descriptions, StoreDomain | `MerchantStoreReads` behind `/api/v1/store`, `store/{code}`, `store/languages` |
| merchant-external-api | merchant.store-client | of(store) | 5 min | TTL now, StoreChanged in PR 4 | one `CachedExternalMerchantStoreService`, auto-configured `@ConditionalOnBean(ExternalMerchantStoreService)`; `MerchantStoreOrgOwner` reads through it |
| checkout | checkout.country | global(lang) | 1 h | Country/Zone commit | `ReferenceReads` |
| payment | payment.types | of(store) | 60 s | PaymentConfiguration commit | `PaymentTypeReads` |

Checkout's `CachedSkuInventory` copy is not carried over: inventory caches its own data for 5 s and checkout
reads it live. Never cached, enforced by the key generator and an ArchUnit rule: anything with a `ShopperId`,
`CustomerId` or principal (cart, order, customer), content preview requests, reservations, payment intents and
webhooks, per-user `/private/` reads. HTTP `Cache-Control` headers and landing-ui's caches stay as they are.

### Naming

- Facades `<Area>Reads` in `-core/…/reads/`; the class is the cached surface, the service behind it stays uncached.
- Regions `<service>.<read>` lowercase, hyphen inside a read: the Grafana `cache` label reads `catalog.product`.
- Events past tense `<Aggregate>Changed`. Region enums `<Service>Regions`, rules beans `<service>EvictionRules`.
- Load-testing impact: label values `STORE → merchant.store-client`, `CATALOG_* → catalog.*`, `STOREFRONT_* →
  content.*`, `INVENTORY_SKU → inventory.sku`; `dashboards.spec.mjs` uses `{{cache}}` so queries stay; the KPI and
  dashboard docs that name `STORE` are reworded (separate load-testing PR).

## PRs and phases (one commit per phase)

**PR 1 `feat(cache): the store-commons cache library, typed ids and docs`** — no behaviour change
1. `feat(commons): ProductId, CategoryId, ManufacturerId, VariantId, KeyPart, StoreScoped` in
   `store-commons/commons/src/main/java/com/asrevo/cvhome/commons/domain/` (records over Long, `@JsonValue`, a
   `Reader`, converters registered where `Sku` binds); tests.
2. `feat(cache): region, key and provider model with the Caffeine provider` (`settings.gradle` include,
   `build.gradle` from `store-commons/errors`; libs already have caffeine and the cache starter).
3. `feat(cache): CvhomeCacheManager, RegionSpringCache and the store-scoped KeyGenerator` (+ `@EnableCaching` in
   the auto-configuration, start-up check that every `@Cacheable` name is a declared region).
4. `feat(cache): post-commit store eviction through a Hibernate integrator, EvictionRules and the validator`
   (port the listener logic from `EntityCommitCacheEviction` on branch `perf/storefront-caches`).
5. `feat(cache): Micrometer binder provider and the com.asrevo.cvhome.cache properties` (common-config.yml block
   replaces `spring.cache`).
6. `feat(test-support): cache architecture rules` in `CvhomeArchitectureRules`: no `@Cacheable` method with a
   `ShopperId`/`CustomerId` parameter, first parameter `StoreMerchantId` unless the region is GLOBAL, no
   `Caffeine`/`CacheManager` use outside `store-commons/cache`, no Spring cache annotation outside a `*Reads` class.
7. `docs: references/caching.md` (regions, keys, adoption in five steps, what never to cache, the event design),
   `configuration.md`, `shared-libraries.md`, `service-to-service.md` (the decorator lives once in
   `merchant-external-api`), `events-outbox.md`, `SKILL.md` "where do I cache a read" row, `AGENTS.md` reject-on-sight
   rows, PR template "Caching" row; both `.agents/skills` and `.claude/skills` copies.

**PR 2 `perf(catalog,content): storefront reads through the cache library`**
1. `refactor(catalog): typed ids in the storefront api` (`category/{id}/manufacturer`, `products/{id}/relationship`,
   `ProductFilter.normalised()`, `ProductSearchCriteria.normalised()`).
2. `perf(catalog): StorefrontCatalogReads, CartLineReads, CatalogRegions, EvictionRules; entities implement StoreScoped`
   (the search-index outbox handler calls `AfterCommitEviction`).
3. `perf(content): StorefrontReads for all twelve storefront reads, ContentRegions, preview bypass`.
4. `test|qa: <Area>ReadsIntegrationTest with SqlStatements; catalog and content QA cases`.

**PR 3 `perf(inventory,merchant,checkout,payment): the remaining cached reads`**
1. `perf(inventory): SkuInventoryReads`, evicted by its own commits and reservation commits.
2. `perf(merchant): MerchantStoreReads; one CachedExternalMerchantStoreService in merchant-external-api`
   (removes the copies in catalog, checkout, payment and `MerchantStoreOrgOwner`'s own Caffeine).
3. `perf(checkout): ReferenceReads for countries`.
4. `perf(payment): PaymentTypeReads`.
5. `test|qa: integration tests and QA cases`.

**PR 4 `feat(cache): typed cache events through the outbox and the transport port`**
1. `feat(cache): CacheEvent records, CacheEventOutboxHandler, CacheEventTransport, LoggingCacheEventTransport`.
2. `feat(catalog,content,inventory,merchant): aggregates register ProductChanged/ContentChanged/StockChanged/
   PriceChanged/StoreChanged` (content, inventory, merchant add the outbox starter and tables in `schema.sql`).
3. `docs: events-outbox.md and caching.md event section`.

**Other repos.** load-testing: KPI and dashboard docs rename (`docs/monitoring/kpis.md`, `dashboards.md`), one PR.
Orchestrator: `.agents/plans/caching-architecture.md` holding this plan and the cross-repo order. PR #364 closed
with a comment pointing at PR 1.

**Reused from branch `perf/storefront-caches`:** the post-commit listener logic with collection callbacks,
`evictAfterCommit` for bulk writes, the per-sku `getAll` shape, the sku inventory cache (moved to inventory),
the two integration tests' shape, the QA entries. **Deleted:** `StoreScopedKey`, `StoreScopedKeyGenerator`,
`EntityCommitCacheEviction`, `CatalogEntityStore`, `ContentEntityStore`, `CachedStorefrontCatalog`,
`CachedCartLines`, `CachedStorefront`, `CachedSkuInventory`, the four `CacheConfig` cache beans, the three
`CachedExternalMerchantStoreService` copies.

## Verification

- `./gradlew :store-commons:cache:check :store-commons:commons:check :store-commons:test-support:check`
  (checkstyle, `verifyNoConfigurationSwitchedBeans`, the shared domain's 0.95 unit floor).
- Per PR: `checkstyleMain checkstyleTest checkstyleIntegrationTest`, `build -x test -x check`, `test`, the touched
  services' `integrationTest` with Docker; `extra/scripts/verify-before-push.sh` on the committed tree before push.
- Unit tests in the module: `CacheKeyTest` (factories, refusals, render), `StoreScopedKeyGeneratorTest`,
  `CaffeineRegionCacheTest` (real Caffeine with a fake Ticker: partial getAll, evictStore bumps one store),
  `CacheRegistryTest` (YAML override, disabled → NoOp, unknown provider fails), `CommitEvictionListenerTest`,
  `EvictionRulesValidatorTest`, `RegionCacheMeterBinderProviderTest`, `CacheEventOutboxHandlerTest`.
- Integration assertions per service: `SqlStatements.during(() -> reads.product(A, en, slug)).count() == 0` on
  the second call; after a write in store A the A read pays statements and the B read still pays none.
- On an lcl stack: `/actuator/prometheus` shows `cache_gets_total{cache="catalog.product",result="miss"}` then
  `hit`; a merchant save in the console shows on the storefront at once on that task; start-up logs list every
  region with provider, TTL, size and any unmapped-entity warning.
- On the load stack: the Bottlenecks dashboard's Caches row with the new labels; one production-mix spike
  compared with the 2026-09-15 report.

## Out of scope (later, onto the same library)

billing `StoreEntitlements` / `EntitlementServiceImpl`, `CachingSecretCryptoProvider`, sso `RateLimiter` /
`RealmRegistry` / `SettingsService`, tenancy `CachingPodDirectory`; the Redis provider module
`:store-commons:cache-redis` and its infrastructure; the HTTP or broker transport implementations.

## Deviations as built

- **PR 1, configuration:** a region's override is `regions.<service>.<read>` (nested maps), not `regions.<service.read>`:
  Boot's binder splits a dotted map key, and the bracket escape (`"[catalog.product]"`) reads badly in YAML.
- **PR 1, `spring.cache` stays** in `common-config.yml` beside the new block until PR 3 removes the last
  `@Cacheable("STORE")` copy: catalog, checkout and payment still run it on Boot's Caffeine manager.
- **PR 1, `CacheRegion.regionName()`** rather than `name()`: an enum's `name()` is final.
- **PR 1, the meter binder** is a `CacheMeterBinderProvider` for the library's Spring cache type, so Boot's own
  `CacheMetricsAutoConfiguration` binds every region; no binder of our own is registered by hand.

- **PR 1, an integration test in the library:** the module applies `java-integration-test-conventions` (a library may,
  when it owns real infrastructure) and `CacheIntegrationTest` runs the auto-configuration on a Testcontainers Postgres.
  Without it the shared domain's integration coverage fell from 69% to 58%: the library's lines are exercised by a
  service's integration tests only once a service adopts it.

- **PR 2, the merchant client phase moved here from PR 3:** with `:store-commons:cache` on every consumer's classpath
  through `merchant-external-api`, the three `@Cacheable("STORE")` copies would have named a region nobody declared
  and stopped checkout and payment at start-up; the one decorator (`CachedMerchantStoreReads`) and the removal of
  `spring.cache` ship with the catalog/content PR.
- **PR 2, the registry merges every `CacheRegions` bean:** a library a service uses (the merchant client) declares
  the regions of its own reads as a bean of its own, so a consumer registers nothing.
- **PR 2, `QueryKey` and `CacheKey.ABSENT`:** a criteria object rides in the key as its canonical text's hash, and
  an optional argument left null keys as `-`, both in the library.
- **PR 3, no `checkout.country` region:** the country list is an ISO list computed once per language and held for
  the task's life; nothing writes it and no store owns it, so a region would cache a cache.
- **PR 3, merchant's server side is three regions** (`merchant.store` for the peers' read, `merchant.store-by-language`
  for the storefront's, `merchant.languages`), all dropped by a save of the store.
- **PR 4, `ContentChanged` carries the content kind** (`PAGE`, `POST`, …), not an item id: content is read as a
  whole, and the kind is what a consumer could narrow on.
- **PR 4, `VariantChanged` and `CategoryChanged` are raised by nobody yet:** the family is complete for a read keyed
  by variant or category; today a category save evicts through its entity rule and no other service caches one.
- **PR 4, a managed row is `save()`d for its events to leave:** Spring Data publishes on `save`, not on flush, so
  the reservation paths save the inventory rows they decrement. Every event costs the outbox an insert and a select;
  a bulk upsert of N skus writes 2N rows, and the bulk-upsert statement test leaves the outbox's reads out.
- **PR 4, `EvictionRules.onEvents()`** starts the rules of a service with no tables of its own (a consumer mapping
  foreign events); the `EvictionRules` default bean lives outside the Hibernate-only configuration so the applier
  exists without Hibernate.
- **PR 4, consumers map nothing yet:** `merchant.store-client` everywhere and `catalog.cart-line` in checkout keep
  their ttl until a transport carries `StoreChanged` and `StockChanged`; the mapping is one `onEvent` line then.

## Status

- cvhome PR 1 (`feat/cache-library`): **cvhome #365**, eight commits, verify green (shared integration 71.5%).
- cvhome PR 2 (`feat/cache-catalog-content`, stacked on #365): **cvhome #366**, six commits, verify green.
- load-testing docs: **load-testing #16**, verify green.
- cvhome PR 3 (`feat/cache-services`, stacked on #366): **cvhome #367**, four commits, verify green.
- cvhome PR 4 (`feat/cache-events`, stacked on #367): **cvhome #368**, three commits, verify green.
- **Spike on the whole stack (2026-09-15, `tmp/cache-all` = main + #365–#368, report
  <https://claude.ai/code/artifact/fff9b136-2e01-4eec-abe6-83cd72b12386>):** the first run refused 151 cart calls
  with 422 `PRODUCT_NOT_PURCHASABLE` on skus in stock. `CaffeineRegionCache.getAll` stamped rows loaded during a
  store eviction with the new version, so Caffeine returned nothing for the keys asked and checkout took the sku as
  unknown. Fixed on `feat/cache-library` (`fix(cache): a bulk load that crosses a store eviction keeps the rows it
  loaded`, regression test) and merged up the stack; the rerun had zero 422s, catalog 725 × 5xx against v5's 1,301,
  checkout 800 against 845, 69 orders against 62. The headline failure rate (9.9% against v5's 6.1%) is landing-ui
  at its cap for 90 s: v5 ran with the page-cache branch, which is not on main. The cache events flowed on the stack
  (427 ProductChanged, 216 StockChanged, 112 PriceChanged, 1 StoreChanged, all drained).
- Next, in order: merge #365 → retarget #366 to main → merge → retarget #367 → merge → retarget PR 4 → merge; then
  a transport (HTTP fan-out or a broker) and the consumers' `onEvent` mappings, and the Redis provider module.
