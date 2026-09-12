# Org isolation — one org's staff on one org's stores, across every repo

This is the one plan for the org isolation fix, in every repo. The findings register is the audit report. Each
work item is one PR in one repo, on the same branch name everywhere, `fix/org-isolation`. In cvhome, each phase A–F
is one commit on cvhome-saas/cvhome#352. The *status* column says what has landed. QA cases live in each owning
service's `qa/<service>-qa.md`, never here.

**Where this came from.** The plan began as `cvhome/.agents/plans/org-isolation-audit.md` (#352 at `4d1f13283`),
an audit written from inside cvhome. That file is removed. Its findings and phases are carried here, corrected by
the cross-repo review of 2026-09-13. Bracketed numbers such as [P3] are its original phase numbers. The plan
extends cvhome's `authorization-audit.md`, which covered *which gate an endpoint carries* and never reached *who may
create the principal that passes it*.

**The question.** A pod assigned to org X accepts org X's staff only, and org Y can neither reach it nor create
stores or manage anything of X's. **As built, it does not hold.** Placement is right; the mint is not, and the pods
trust what the mint produces.

## Context — how a pod decides, as built

There is no org header. A pod service is a resource server that believes the `roles`, `org` and `store` claims of
the uaa JWT. uaa copies `org` and `store` from free-form user metadata, which it never validates
(`JwtCustomizerConfig.java:36-41,161-165`). Tenancy is what writes that metadata for store staff. So a pod's
isolation is exactly as strong as the rules on who may create which user with which `org`, `store` and roles.

| Principal | What the pod compares today | Where |
|---|---|---|
| Org admin | The pod's org (if configured), and the store's owner via merchant (`ownsTheStore`) | `StoreRoleAccessChecker.java:138-152`, `:74-94` |
| Store admin / moderator | The pod's org (if configured), and the `store` claim equals `?store=`. **No owner check** | `StoreRoleAccessChecker.java:154-200` |
| `store_core` service | The read tier and STORE-CREATE on any store, by design. Never the manage tier | `PermissionAccessChecker.java:59-73,119,135`; manage `:85-94` |
| Pod service | The `resource` claim equals this pod's name | `StoreRoleAccessChecker.java:266-290` |
| Shopper | Its own pod's cua issuer, and the `realm` claim equals `?store=` | `StoreRoleAccessChecker.java:232-252` |

**"If configured" never happens, on either side:**

- **The pod side is never configured.** `com.asrevo.cvhome.pod-info.pod` carries no `org-id` anywhere:
  - locally: `store-pod-lcl-config.yml:43-49`, `lcl.yml:102-111`;
  - on AWS: cvhome-platform `modules/store-pod/main.tf:75-79` (`var.pod` has no org, `variables.tf:9-18`);
  - in no test.

  So `isPodAllowOrg` (`StoreRoleAccessChecker.java:216-230`) returns true on every running pod, and the pod-org
  branch of STORE-CREATE never runs.
- **The registry side binds, but nothing supplies it.** `pods[n].org-id` reaches `Pod.orgId`
  (`ServiceDomainProperties.java:13-14`, `Pod.java:7`), and a new registry row takes it
  (`PodSeedInitializer.java:87-88`). An existing row drops it (`:90-91`), and `PodServiceImpl.update` ignores it
  (`PodServiceImpl.java:104-117`). No configuration supplies it: the seed on AWS carries id, name and endpoint only
  (`modules/store-core/main.tf:100-107`), and `store-core-lcl-config.yml:4-10` has no org. The other writers of
  `org_id` are `PodEntity.newEntity`, for a pod created through `POST /api/v1/pod`, and the 2026-08-12 migration.

**What holds, verified:**

- Tenancy takes the org for a new store from the token, never the body (`StoreManagerApi.java:113-120`).
- The registry confines an org that has private pods to them, never hands a shared-pool org someone's private pod,
  and does not let a preferred pod escape the candidate set (`PodPlacementService.java:51-101`,
  `PodRepository.java:70-73`).
- Org lifecycle writes are super-admin only (`OrgManagerApi`).
- Members and invitations are scoped by the token's org (`OrgMemberApi`), with the exceptions in O10.
- A foreign store is a 404 on tenancy's store reads, archive and delete (`InternalStoreServiceImpl.java:218-227`),
  except for a token with no org (O6).
- An org admin of Y is refused on X's store on any pod.

**What the cross-repo review changed.** The review made four read-only passes over every checkout, current with
origin: uaa and tenancy; the pods; cvhome-platform and the image repos; the tools and docs repos. Nothing the
original audit cited had changed on `origin/main` (`23b1b76f4`). What it changed:

- **The findings.** Three are new (O7–O9), and O5 is corrected.
- **The phase order.** Platform-wide-by-role moves first, because tenancy's fix depends on it.
- **uaa's guard** keys on the caller's authority, not the caller's type.
- **Blank org values.** A blank or malformed pod `org-id` becomes impossible.
- **The pod test plan** follows the stubs as they actually are.
- **cvhome-platform** gets a new pod-org declaration. It has no pod object to extend.
- **The clean-up** runs through the admin APIs, because AWS gives no SQL access.
- **Two new work items:** the docs site and ideation.

**Exposure.** Every running cvhome is exposed today: dev on AWS (the only environment that has been applied), every
lcl stack, and anyone self-hosting the public repo. Public signup grants `ORG_ADMIN` (`SignUpApi.java:45-49`,
`SignupServiceImpl.java:33,113-114`), so "an org admin" below means "anyone with an email address".

## Findings register, severity-ranked

Severity follows `authorization-audit.md`. A finding stays `open` until the phase that owns it has merged.

| Id | Sev | Where | What an attacker can do | Fix | Owner | Status |
|---|---|---|---|---|---|---|
| O1 | **C** | tenancy `ManagedUserAccountServiceImpl.java:83-101`; uaa-client-impl `UserAccountServiceImpl.java:117-155`; sso-core `AdminService.java:229-234` | An org admin, or a store admin for its own store, creates or updates a user with `roles: ["SUPPORT"]`. A store admin can do it to **its own** account. Tenancy forwards the body's roles, and uaa refuses only `SUPER_ADMIN`. `SUPPORT` reads every org, store and uaa user (`OrgManagerApi.java:84-95,185-189`, `AdminUserController.java:83`, `UaaSecurityConfig.java:94`). It also impersonates any non-platform account with that account's full roles (`ImpersonationExchangeProvider.java:176-184,253-261`); read-only mode was removed. So: sign up → mint `SUPPORT` → impersonate org X's owner → control of org X | Only a super admin grants a platform role (uaa); tenancy grants from a per-caller allow-list | B, C | open |
| O2 | **C** | tenancy `application.yml:24` (`DELEGATED`), `PermissionAccessChecker.java:75-78,138-152`, `ManagedUserAccountServiceImpl.java:86-87`; pods `StoreRoleAccessChecker.java:154-200` | Org Y's admin calls `user-account/create?store=<X's store>`. Under `DELEGATED`, `ownsTheStore` is true, so the gate admits any org admin on any store. The service stamps `org=Y, store=<X's store>` without asking who owns it. The new user's token passes every pod check for a store admin, because those compare only the `store` claim. That is full management of X's catalog, orders, payment settings and customers. Store ids are public: the storefront's PKCE `client_id` is the store id | Tenancy resolves the store through the org-scoped lookup before any uaa call; pods check store staff against the store's owner | C, D | open |
| O3 | H | as O1; `ManagedUserAccountServiceImpl.java:167-180` | Through the same passthrough, a store admin mints an `ORG_ADMIN` in its own org. Writes check the target's org and store but not its rank. So a store admin can reset the password of, disable, or delete any account stamped with its store, whatever roles that account holds | Per-caller allow-list for grants; a write needs every role the target holds to be one the caller could grant | C | open |
| O4 | H | cvhome-platform `modules/store-pod/main.tf:75-79`; `store-pod-lcl-config.yml:43-49`; `PodSeedInitializer.java:85-99` | A pod never learns it is dedicated, so it accepts every org's tokens; only placement keeps other orgs' stores off it. The registry and the pod read the org from different places, and nothing reports when they disagree | One declaration feeds both; the pod binds `pod-info.pod.org-id`; the seed reports a disagreement | E, platform | open |
| O5 | M | tenancy `UserAccountApi.java:74-78`; uaa-client-impl `UserAccountServiceImpl.java:270-281` | Any authenticated caller can call `assignable-roles`. It answers uaa's table minus `USER` and `ORG_ADMIN`; uaa has already dropped `SUPER_ADMIN` (`AdminService.java:404-411`). So `SUPPORT` and every custom role are offered. The console intersects with `OFFERABLE_ROLES` (`team.ts:35`) as defence in depth | Answer the caller's own allow-list | C | open |
| O6 | L | `PodApi.java:84-86`; `InternalStoreServiceImpl.java:157-159`, used at `:110,112,221`; `SecurityUtils.java:154-164` | A staff token with a role but no usable `org` claim parses to an org with a null id, and all three sites read that as platform-wide: every pod, every store. `findStore` (`:221`) is the ownership check phase C reuses. Such a token is reachable: uaa creates an account with no metadata, deletes `org` when an update sends null (`AdminService.java:194-196,237-239`), and parses any org that is not 24 characters to a null id | Platform-wide by role, never by a missing org | A | open |
| O7 | H | sso-core `AdminService.java:166,179,214,241`; `InvitationService`; `BaseException.java:55` | **A refused grant still commits.** The writes are `@Transactional` without `rollbackFor`, and every refusal is a checked exception (`BaseException extends Exception`). The account row and its metadata are saved first (`:186-197`), then roles are added one at a time (`:222-224`). When a later role name fails, Spring commits anyway, and no `user.created` or `user.role.assigned` row is written. So `roles: ["SUPPORT", "<unknown>"]` mints a `SUPPORT` account with no audit trail. `SelfRegistrationService.java:52-57` already sets `rollbackFor` for exactly this reason. Found by reading, not yet run | `rollbackFor = Exception.class` on every write | B | open |
| O8 | M | sso-core `IdentityBrokerService.java:153-164`, `IdentityProviderMapper.java:71`, `RoleService.java:51`, `UaaJwtGrantedAuthoritiesConverter.java:51-55`, `AdminClientService.java:213-233,416` | **uaa's platform-role guard keys on role names and caller type.** Any caller through the `ADMIN` gate can get a platform role granted around it. That gate admits the super admin and `admin-sdk`, a client only tenancy holds. The routes: a provider's `defaultRoles`, granted at every federated login and stored unvalidated; a role that inherits `SUPPORT`; a system role given `users:impersonate`; a role named `ROLE_SUPER_ADMIN`, which the name pattern accepts and the converter turns into the super-admin authority; and an `authorization_code` client with `super_admin` scope. That client's tokens carry a `uid`, so they read as a USER, the actor type the original Phase 1 trusted | Key on the caller's `ROLE_SUPER_ADMIN`; identify platform roles by what they carry, not by name | B | open |
| O9 | blocker | every pod service's `application.yml:12`; cvhome-platform `modules/store-pod/main.tf:165-170,238`, `bootstrap.yaml:295-308` | **Every pod runs as the same service client**, `store-pod-507f1f77@service.store-pod.internal`, resource `pod-507f1f77`, with one secret. A second pod refuses its own service tokens and can act as the default pod. Raising `PodCount` regenerates every extra pod id. No org can exploit this, but it means a dedicated pod cannot run on AWS | Per-pod service identity | own plan (F-010) | open |
| O10 | L | tenancy `OrgMemberApi.java:82,92,114-118` | An org invitation carries a free-form role the inviter chooses, and `accept` is not bound to the invited email. It writes only `tenancy.org_member`, which no authorization check reads | Invitations accept org roles only | C | open |
| O11 | L | tenancy `OrgOwnerBackfill.java:101-106` | The backfill records the first `ORG_ADMIN` carrying `metadata[org]` as an ownerless org's owner. An O3-minted account qualifies | Checked in the clean-up | clean-up | open |

The review also found these. **They are not in this plan**; each needs its own.

| Id | Sev | Repos | What | Where it goes |
|---|---|---|---|---|
| E1 | M | cvhome, caddy-domainlookup (→ saas-gateway → public-dkr) | spg forwards a `Store-Id` header the client sends. `domain_lookup` never deletes the incoming header and fails open: an error, or an unknown host (answered `{}`), passes the client's header through (`domainlookup.go:75-85,133-141`). The Caddyfile strips nothing (`:94-118`). cua trusts the header: it wins over `?store=` (`StoreRealmResolver.java:51-62`) and alone creates a realm row (`EdgeVerifiedRealmFilter.java:40-42` → `RealmRegistry.ensure`, "only for a realm the edge vouched for"). Not a staff hole, because staff tokens come from uaa. `http.Get` also has no timeout | Its own plan: first a Caddyfile strip in cvhome, then the plugin fix through the edge image chain |
| A1 | — | cvhome-platform | Every core service logs in to RDS as the master user (`rds.tf:33-39`). On dev and ephemeral, the default pod's services hold the same secret (`README.md:181-188`). A compromised service can write `uaa.*` directly | cvhome-platform backlog |
| A2 | — | cvhome (lcl only) | Locally, all five `UAA_*_SECRET` values are the same, and tenancy's s2s registration defaults to the `admin-sdk` secret. So any local service secret yields `super_admin`. AWS generates each secret separately | A note in `qa/lcl-qa.md` (phase F) |

**Not findings — recorded so nobody reopens them.**

- `SUPPORT` is platform-wide by design (`user-impersonation.md`), and that includes listing every store's shoppers
  through cua (`CuaSecurityConfig.java:155-161`). The fix is who may become support, not what support may do.
- The shared `store_core` client reading and provisioning any store is on `authorization-audit.md`'s by-design
  register.

## Decisions

Decisions 1–3 came from the original audit; 4–9 come from the review. Confirm them before phase B:

1. **`ORG_ADMIN` is not grantable through `user-account/*`.** That endpoint is store-scoped and stamps a store on
   every account it creates, whereas an org co-owner is an org-level identity. Nothing in the console offers it
   (`OFFERABLE_ROLES` = `STORE_MODERATOR`, `STORE_ADMIN`). A real co-owner flow belongs to `OrgMemberApi`; it is
   ideation F-009.
2. **The grantable set is `STORE_ADMIN`, `STORE_MODERATOR`, `STORE_RETAIL`,** for org admins and store admins
   alike. A store admin granting `STORE_ADMIN` on its own store makes a peer, not a superior. A peer can also reset
   another store admin's password on the same store; that is intended.
3. **Making an existing shared pod dedicated is out of scope.** It is only safe for a pod that hosts no other org's
   stores. Phase E reports the disagreement rather than resolving it. The move itself is F-010.
4. **uaa grants a platform role only to a caller holding `ROLE_SUPER_ADMIN`**, not to any USER caller (O8 lets a
   client produce USER tokens). A platform role is `SUPER_ADMIN`, `SUPPORT`, or any role that carries realm scope
   or a platform permission, or inherits one. Role names starting `ROLE_` are refused, and so is `super_admin` scope
   on a client with an `authorization_code` grant.
5. **A pod `org-id` that is present but malformed, blank included, stops the service at startup.** An absent value
   means shared. A pod that boots and refuses every org is worse than one that does not boot. The platform never
   emits an empty value.
6. **Phase A (platform-wide by role) comes first.** It is the smallest, and phase C's ownership check depends on it.
7. **Dedicated pods on AWS get their own plan**, covering O9 and the move from shared to dedicated (ideation
   F-010). This plan's platform PR adds only the declaration and its guards, and it changes nothing until a second
   pod exists.
8. **E1 gets its own plan.** It is on the shopper side, and its real fix crosses the edge image chain.
9. **The clean-up goes through the uaa and tenancy admin APIs, as the super admin.** AWS has no path to the
   database (no bastion, ECS Exec off, no shell in the images), and this plan does not add one.

## Why the design is what it is

- **One plan, one PR per repo, producers first.** cvhome (the properties, the guards, the refusal codes) goes
  before cvhome-platform (which emits the property), which goes before the release. With the same branch name,
  cvhome-platform's catalog-drift job compares against cvhome's branch while both are open.
- **Fix both the mint and the check.** The mint (tenancy, uaa) is the root cause, because every service believes a
  token uaa issued. The pod check is the second layer. uaa metadata stays writable by any `super_admin` caller, and
  O1, O2 and O7 accounts may already exist.
- **Tenancy stays `DELEGATED`.** Its answer to a foreign store is 404, not 403, because a 403 would confirm that the
  id exists. So the ownership check goes into the service, through `InternalStoreService.findStore(identity,
  store)`. That lookup already answers a foreign store with `StoreNotFoundException`, once phase A makes it
  role-based. No new query is needed.
- **The allow-list lives in tenancy, keyed by the caller's role.** Tenancy knows who is asking. uaa sees a single
  `admin-sdk` client for every caller, so it cannot tell. The console's `OFFERABLE_ROLES` stays as defence in
  depth.
- **A write needs the caller to outrank the target.** Every role the target holds must be one the caller could
  grant. Without that rule, a caller could bypass the grant rule by editing an account that already holds more.
- **uaa checks who the caller is, not what kind of caller it is.** `SUPER_ADMIN` stays never assignable through the
  API (uaa-qa SEC-15). The original Phase 1 made `SUPPORT` assignable when `AuditActorResolver` said USER, but O8
  shows a client can create itself a USER. For a person, `ROLE_SUPER_ADMIN` is what the `ADMIN` gate already means.
  Every grant path goes through `AdminService.assignableRole`: create, `createAccount`, `assignRoles`, update, and
  invite via `InvitationService.invite` → `createAccount`. The only exceptions are O8's side doors, which phase B
  closes.
- **Pods check store staff against the owner, the way they already check org admins.** Every pod service already
  has the lookup, the answer is cached for 30 minutes, and tenancy and billing are `DELEGATED` and unaffected. With
  merchant unreachable and the cache cold, store staff are refused, as org admins already are. A check that cannot
  be made has not passed.
- **A dedicated pod learns its org from the same declaration the registry is seeded from.** `pod-info.pod.org-id`
  already binds to `ManagerOrgId` through its String constructor, as `pod.id` binds to `PodId`. A pod asking the
  registry at runtime was rejected: it would make every pod depend on store-core to authorize a request. A pod's
  org is fixed at creation, because moving a pod strands its stores. So a configuration that disagrees with the
  stored row is an operator error to report, not to apply.
- **Three guards against a blank org.** `ManagerOrgId(String)` turns anything that is not 24 characters into a null
  id, and a pod with a null-id org refuses every real org while admitting tokens with no org. So:
  - the platform validates `^[0-9a-f]{24}$` and omits the variable when unset;
  - the pod fails fast on a malformed value;
  - `lcl.yml` never writes `${env.X}` for it, because lcl resolves an unset variable to `''` (lcl `config.ts:217`).
- **The env var spellings already work, but nothing checks them.** A binder harness on Spring Boot 4.0 bound both of
  the platform's spellings, `COM_ASREVO_CVHOME_POD-INFO_POD_ORG-ID` and `COM_ASREVO_CVHOME_PODS[0]_ORG-ID`, to
  `ManagerOrgId`. Production already relies on the dashed form: cua needs `pod-info.pod.endpoint.endpoint`, and on
  AWS only `COM_ASREVO_CVHOME_POD-INFO_POD_ENDPOINT_ENDPOINT` supplies it. `contract-check.py` cannot see dashed or
  bracketed names, so orchestrator Phase 2 makes pod identity a checked contract.
- **Platform-wide is a role, not an absence.** `UserOrgStoreIdentity.isPlatformWide()` means super admin or
  `SCOPE_STORE_CORE`. It replaces three copies of `org() == null || org().id() == null`.
- **The clean-up reads current state, not only history.** O7's mints leave no audit row. The audit log is the
  history; the user list is what is true now.

## Work items and order

| # | Repo | Branch / PR | Deliverable | Depends on | Gates |
|---|---|---|---|---|---|
| 1 | orchestrator | `fix/org-isolation` | this plan (Phase 1); pod identity as a checked contract (Phase 2); a status commit per merged item | — | `scripts/contract-check.py`, `scripts/impact.py` |
| 2 | cvhome | #352 | phases A–F, one commit each | decisions 4–9 confirmed | per phase, then `extra/scripts/verify-before-push.sh`; end to end on `lcl --stack org-isolation` |
| 3 | cvhome-platform | `fix/org-isolation` | `pod_org_ids` with its guards | merges after 2 (phase E makes a malformed value fail fast) | `scripts/verify.sh` (fmt, validate, tflint, catalog drift, cfn) and a `.tftest.hcl` for the guards |
| 4 | orchestrator | Release workflow | `releases/vX.Y.Z.yaml` pairing 2 and 3 | 2 and 3 merged | release validation (`references/qa.md` § 3) |
| 5 | cvhome-platform (operator) | — | deploy to each environment (`envs/<env>.tfvars` `image_tag`), then the clean-up | 4 | the clean-up below |
| 6 | cvhome-saas.github.io | `fix/org-isolation` | the isolation claims match what is built | 2 and 3 merged | `npm run docs:build` |
| 7 | ideation | `fix/org-isolation` | F-009 org co-owners, F-010 dedicated pods on AWS | — | none |

Item 7 has no dependencies and can run alongside item 2; item 6 waits for 2 and 3. The orchestrator PR stays open
until the last item merges. Each PR records its own deviations in its body as they happen; this plan collects them
when that item merges.

**Not touched, with the evidence:**

- **load-testing.** Its only call is `user-account/list`, as org1-admin on org1-store1
  (`selftest.js:104,133,174`). No journey uses store staff. Only super-admin lacks an `org`, and phase A keeps it
  platform-wide by role. Its stack sets no `org-id` (`stack/docker-compose.yml:52-61`). `STORES=all` already pairs
  org1-admin with org2's stores and fails there today (`env.js:109-111`); phase C adds one more 404 on that path.
- **lcl.** Nothing changes in the runner, and services inherit the caller's environment (`proc.ts:16`).
- **e2e-testing.** Still a scaffold. An O1/O2 spec would first need a helper that logs in through the stack.
- **assets.** The 1.0.x layout; it seeds nothing.
- **dot-github, saas-gateway, certmagic-s3, aws-otel-collector, public-dkr.** Nothing, apart from E1.

## Orchestrator

**Phase 1 — the plan (commit 1).** This file. The org-router and cross-repo-change skills now say that a change
spanning repos keeps its one plan here, and each repo's PR carries that repo's phases as commits.

**Phase 2 — pod identity becomes a checked contract (commit 2).**

- **`scripts/contract-check.py`, new check `pod-identity`,** registered in `CHECKS` with its paths bound in
  `bind_paths`. It checks three things:
  - each name the platform emits under `COM_ASREVO_CVHOME_POD-INFO_POD_*` (`modules/store-pod/main.tf:75-79`) and
    `COM_ASREVO_CVHOME_PODS[n]_*` (`modules/store-core/main.tf:100-107`) maps, by relaxed binding, to a field of
    cvhome's `Pod` record;
  - `org-id` is emitted to both modules or to neither, and only under a condition, never as a bare `""`;
  - `pod-info.pod` and `pods[0]` agree in `cvhome/lcl.yml` and in `load-testing/stack/docker-compose.yml`.
- **`scripts/impact.py`, new rules.** Today all of these files come back "local to cvhome".
  - cvhome `Pod.java`, `PodInfoProperties`, `ServiceDomainProperties`, `PodSeedInitializer` and
    `store-*-lcl-config.yml` → cvhome-platform's `main.tf` pod locals and both modules, `lcl.yml`, the load stack.
  - cvhome `StoreRoleAccessChecker`, `PermissionAccessChecker`, `UaaConstants`, sso-core `AdminService` and tenancy
    `ManagedUserAccountServiceImpl` → load-testing's fixtures and journeys (which roles they log in as), and the docs
    site's claims.
  - cvhome-platform's pod locals → cvhome `Pod`.
- **References.** `references/cross-repo-contracts.md` gains the row "A pod's identity and org".
  `references/repo-map.md:24` stops saying a pod has its own database; that is false on dev and ephemeral
  (`cvhome-platform/flavours.yaml:82,291`).
- **Gates.** `contract-check.py` is OK on every current `main` and FAILs on a platform copy that sets `org-id` on
  one module only, or without a condition. `impact.py cvhome --files <the pod files>` names the consumers.

## cvhome — #352, one commit per phase

### Phase A [P3] — platform-wide is a role, not a missing org (commit 1)

Add `UserOrgStoreIdentity.isPlatformWide()` in `store-commons/commons`: true for the super admin or
`SCOPE_STORE_CORE`. The authorities converter upper-cases scopes (`UaaJwtGrantedAuthoritiesConverter.java:52-54`).
It replaces the missing-org test at all three sites:

- `PodApi` (`listPods`, `findAllPods`);
- `InternalStoreServiceImpl.findAll`;
- `InternalStoreServiceImpl.findStore` (`:221`).

An identity that is neither platform-wide nor carries an org id gets an explicit empty list, or
`StoreNotFoundException` from `findStore`, and never a query with a null org parameter. `store_core` must stay
platform-wide: the gateway replaces its route table with any successful answer, an empty one included
(`PodClient.java:108-116`).

- **Tests.** An identity unit test. `PodApi`: an `ORG_ADMIN` with a missing or malformed `org` gets an empty list (a
  store admin never reaches `POD.READ`). `InternalStoreServiceImplTest`: the same identity gets an empty list, and
  `findStore` on a foreign store returns 404. The super admin and `store_core` see everything.
- **QA.** `tenancy-qa.md` SEC-04 and `pod-registry-qa.md` PDR-06 gain the no-org line. The seeded `support` user
  (metadata `{}`, uaa `data-test-stores.sql:36-38`) lets it run live: support still lists every store through
  `findAll(ManagerOrgId)` (`OrgManagerApi.java:185-189`).
- **Gates.** `:store-commons:commons:test`, `:store-core:pod-registry:pod-registry-service:test`,
  `:store-core:tenancy:tenancy-service:test`, checkstyle.

### Phase B [P1] — uaa grants platform roles only to a super admin (commit 2)

All changes are in `store-commons/sso/sso-core`.

- **`UaaConstants.PLATFORM_ROLES`** moves from `ImpersonationExchangeProvider.java:98`, and both classes use it. A
  role is a platform role if it is named there, carries realm scope or a platform permission (`users:impersonate`
  and the like), or inherits one.
- **`AdminService.assignableRole`** never assigns `SUPER_ADMIN` through the API. It assigns any other platform role
  only when the caller holds `ROLE_SUPER_ADMIN` (decision 4). Otherwise it throws `RoleNotAssignableException` (403
  `UAA.ROLE.NOT_ASSIGNABLE`; the exception lives in `store-commons/uaa-client`, `UaaErrors:61`).
  `getAssignableRoles()` leaves out platform roles for anyone else.
- **O8's side doors go through the same rule:**
  - provider `defaultRoles` are validated when written (`IdentityProviderMapper.java:71`) and filtered at login
    (`IdentityBrokerService.java:153-164`);
  - role create and update refuse a name starting `ROLE_` (`RoleService.java:51`), and refuse to give a
    non-platform role a platform permission or a platform parent;
  - client create and update refuse `super_admin` scope on a client with an `authorization_code` grant
    (`AdminClientService.java:213-233`).
- **O7:** `rollbackFor = Exception.class` on every write in `AdminService` and `InvitationService`, as
  `SelfRegistrationService.java:57` already does.
- **Stale comment:** `AdminUserController.java:80-82` still says impersonation is read-only; it is not.

- **Tests.** In `AdminServiceTest`:
  - a caller without `ROLE_SUPER_ADMIN` grants `SUPPORT` on create, update, `assignRoles` and invite → refused;
  - a super admin → granted;
  - `getAssignableRoles`, by caller;
  - a provider with default role `SUPPORT` → refused on write, and dropped at login if already stored;
  - `ROLE_SUPER_ADMIN` as a role name → refused;
  - an auth-code client with `super_admin` → refused.

  Integration, because the rollback happens in the proxy: `["SUPPORT", "<unknown>"]` and
  `["STORE_ADMIN", "<unknown>"]` leave no account and no role. In the admin-user API suite, an `admin-sdk` token
  plus `SUPPORT` → 403.
- **`.http`.** Refusal blocks in `store-core/uaa/http/admin-user-api.http` and the matching role, client and
  provider files.
- **QA.** `uaa-qa.md` SEC-15 gains the `SUPPORT` line. New cases: SEC-18 "Platform roles are granted by a super
  admin" and SEC-19 "A refused grant leaves nothing behind".
- **Gates.** `:store-commons:sso:sso-core:test`, `:store-core:uaa:integrationTest`, checkstyle.

### Phase C [P2] — tenancy: user writes stay inside the caller's store and rank (commit 3)

`ManagedUserAccountServiceImpl` gains `InternalStoreService`. There is no dependency cycle: that service depends
only on repositories, mappers and billing (`InternalStoreServiceImpl.java:47-53`). Every method first calls
`findStore(identity, store)`, as phase A made it: `list`, `findOne`, `createUser`, `updateUser`, `resetPassword`,
`deleteUser`, `enableUser` and `disableUser`. A foreign store is the existing `StoreNotFoundException` (404), and
nothing reaches uaa. Then:

- **Grant rule** (`createUser`, `updateUser`): every requested role must be in `grantable(identity)`.
  - For an org admin or a store admin, that is `STORE_ADMIN`, `STORE_MODERATOR` and `STORE_RETAIL`; for anyone
    else, nothing.
  - Otherwise a new `RoleNotGrantableException` (`TenancyErrors.USER_ROLE_NOT_GRANTABLE`,
    `CONTROL_PLANE.USER.ROLE_NOT_GRANTABLE`, `FORBIDDEN`), shaped like `ForeignOrgUserAccessException`.
  - A caller updating its own account is not exempt (O1).
- **Rank rule** (`updateUser`, `resetPassword`, `deleteUser`, `enableUser`, `disableUser`): after
  `validateUserAccess`, every role the target holds must be in `grantable(identity)`, or the same exception.
- **`assignableRoles()`** answers `grantable(identity)` intersected with uaa's roles, and takes
  `@OrgStorePrincipalInfo`. It stays on the `AUTHENTICATED_ONLY` list (`TenancyArchitectureTest.java:38-45`,
  `TenancyApisTest.java:96-101`, `authorization-audit.md:191`): the answer is scoped by the caller, so a token would
  be decoration.
- **uaa's refusal reaches tenancy intact.** `UserAccountServiceImpl.java:129-133` (uaa-client-impl) turns every
  error except a conflict into `UaaApiUnavailableException` (a 5xx). Map a 403 from uaa to a 403, so phase B's
  refusal shows if tenancy's own rule is ever bypassed.
- **Invitations** (`OrgMemberApi.invite`, `resend`) accept only roles in `grantable(identity)` (O10).

- **Tests.** In `ManagedUserAccountServiceImplTest`:
  - a foreign store → 404 before any uaa call;
  - `SUPPORT` and `ORG_ADMIN` refused on create and update;
  - a store admin updating itself to `SUPPORT` → refused;
  - a store admin cannot reset an `ORG_ADMIN` stamped with its store;
  - the peer grant is allowed.

  In `UserAccountApiIntegrationTest`:
  - org 2's admin calls `create?store=<org 1 store>` → 404;
  - `SUPPORT` → 403 `CONTROL_PLANE.USER.ROLE_NOT_GRANTABLE`;
  - `STORE_MODERATOR` on its own store → 200;
  - `assignable-roles` for an org admin → exactly the three store roles;
  - an invitation with `SUPPORT` → 403.
- **`.http`.** Refusal blocks in `store-core/tenancy/tenancy-service/http/user-account-api.http` and the org-member
  file.
- **QA.** In `tenancy-qa.md` §PERM:
  - PERM-05 "A user cannot be created on another org's store" (critical);
  - PERM-06 "No caller grants `SUPPORT` or `ORG_ADMIN`" (critical);
  - PERM-07 "A store admin cannot act on an account that outranks it" (high);
  - PERM-08 "`assignable-roles` answers what this caller may grant" (high).
- **Gates.** `:store-core:tenancy:tenancy-service:test integrationTest`, `:store-commons:uaa-client-impl:test`,
  checkstyle. The console needs no change, because it already offers a subset of the new answer.

### Phase D [P4] — pods: store staff belong to the store's owner (commit 4)

`StoreRoleAccessChecker.isStoreAdmin` and `isStoreModerator` end with
`ownsTheStore(identity.org(), requestedStoreId)`, exactly as `isOrgAdmin` does. Every pod service already has the
owner lookup:

- merchant through its own `ExternalMerchantStoreApi`;
- content, catalog, inventory, checkout, payment and cua through an `ExternalMerchantStoreService` bean, which
  `MerchantStoreOrgOwnerAutoConfiguration` turns into the retriever (`@ConditionalOnBean` `:20`,
  `@ConditionalOnMissingBean` `:24`).

Answers are cached for 30 minutes per store (`MerchantStoreOrgOwner.java:34`). `DELEGATED` services are unaffected
by construction.

The cost is in the tests, not the code:

- **`Tokens.staff(role, store)`** (`store-commons/test-support`) derives the org from the store by value: STORE_1
  and STORE_2 → ORG_1, STORE_3 and STORE_4 → ORG_2. uaa's `data-test-stores.sql:4-35` and merchant's
  `init-sql/stores/*/01-store.sql` agree on that. Any other id falls back to ORG_1, because merchant signs staff
  tokens for a store it creates at runtime (`MerchantStoreApiIntegrationTest.java:124,281-282`). Today it always
  signs ORG_1 (`Tokens.java:85-87`).
- **A store→org `StoreOrgOwnerRetriever`** over the same map, in test-support. Each suite adds it to its **existing**
  shared test configuration, because a new `@Import` splits the context cache. The stubs today:

  | Suite | Owner lookup in tests today | Change |
  |---|---|---|
  | content (`ApiTestSupport`) | none | add the retriever |
  | inventory | none | add the retriever |
  | payment (`PaymentApiTestSupport`) | none | add the retriever |
  | catalog (`ExternalClientsTestConfiguration.java:46-55`) | stub sets no `org`, so the owner is null and staff are refused | answer by store |
  | checkout (`:79`) | stub answers ORG_1 for every store | answer by store |
  | merchant | its own seeded rows, which already carry the owning org | none |
- **Blast radius.** Eight files sign staff tokens, and 29 depend on them: merchant 2, content 7 (five use STORE_3),
  catalog 9, inventory 2, checkout 5, payment 4, cua none.
- **The owner cache** lives as long as the test context and keeps only owners it found. So "an unknown owner
  refuses" needs a store id no test has resolved. Merchant's post-delete 404 (`:307-309`) passes today only because
  the owner is cached.
- **Unit.** `StoreRoleAccessCheckerTest.StoreStaff` and `PermissionAccessCheckerTest`:
  - another org's store admin and moderator are refused on a shared pod;
  - the owning org's staff are admitted;
  - an unknown owner refuses.

  Their fixtures already pair each store with its owner.
- **Integration.** Catalog and merchant each gain "a store admin whose `org` does not own the store → 403".
- **QA.** `catalog-qa.md` SEC-03 and `merchant-qa.md` SEC-02 gain the case of a token minted before phase C,
  cross-referencing `tenancy-qa.md` PERM-05.
- **Gates.** `:store-commons:autoconfigure:test`, `:store-commons:test-support:test`, then `integrationTest` with
  Docker for merchant, content, catalog, inventory, checkout, payment and cua.

### Phase E [P5] — a dedicated pod knows its org (commit 5)

- **Binding.** `pod-info.pod.org-id` and `pods[n].org-id` already bind to `ManagerOrgId` through its String
  constructor (`PodInfoProperties.java:7-8`, `ServiceDomainProperties.java:13-14`). No converter and no pod code are
  needed.
- **Malformed values** (decision 5). An `org-id` that is present but does not parse, blank included, fails startup
  in every pod service and in the registry seed, naming the property. The implementer picks where; the test decides
  whether it works.

  Today such a value binds to `ManagerOrgId(null)`, with these effects:
  - the pod refuses every real org and admits tokens with no org;
  - `PermissionAccessChecker.java:67` throws on store create;
  - the registry marks the pod PRIVATE, and `JdbcConfig.java:30-34` throws outside `reconcile`'s catch.
- **`PodSeedInitializer.reconcile`** (`:85-99`). When a configured pod's org differs from the stored row's, log an
  error naming both and keep the stored value. `newEntity` already takes the configured org for a new row.
- **Config.** Document `org-id` in `store-pod-lcl-config.yml` (`:43-49`) and `store-core-lcl-config.yml` (`:4-10`).
  Unset means shared, which lcl stays: one pod, both demo orgs.
- **Binding test** in autoconfigure. The property spelling and both env spellings the platform emits,
  `COM_ASREVO_CVHOME_POD-INFO_POD_ORG-ID` and `COM_ASREVO_CVHOME_PODS[0]_ORG-ID`, bind to `ManagerOrgId`, and blank
  or malformed values fail. It must use a `SystemEnvironmentPropertySource` named `systemEnvironment`; any other
  source silently fails the dashed names.
- **Integration:**
  - catalog with `pod-info.pod.org-id = ORG_1`: org 2's store admin on org 2's store → 403, org 1's → 200, and a
    shopper's public read is unaffected;
  - merchant STORE-CREATE: a foreign org → 403, the pod's own org → 200, `store_core` → 200. This last case cannot
    live in catalog, whose manage tier never admits `store_core`;
  - pod-registry: a seed with a disagreeing org logs the error and keeps the row.
- **QA.** `catalog-qa.md` SEC-06 "A dedicated pod refuses every other org's staff" (critical).
  `pod-registry-qa.md` PLC-07 "Configuration and registry disagree on a pod's org".

  Running it locally: the pod side takes `COM_ASREVO_CVHOME_PODINFO_POD_ORGID=<org 1>` from the environment of
  `lcl start`, which services inherit. The registry side does not: lcl.yml's `SPRING_APPLICATION_JSON` already
  defines `pods[0]`, and Spring binds a list whole from one source. So PLC-07 edits that JSON in the worktree and
  starts on a fresh database. Org 2's logins then fail on org 2's stores, which is the point.
- **Gates.** autoconfigure `:test`, pod-registry `:test`, catalog and merchant `integrationTest`.

### Phase F [P6] — docs (commit 6)

- **`project-structure` references.** In `.agents/skills/project-structure/references/authentication.md`, the
  principal table says store staff are checked against the store's owner, and who may grant which role.
  `multi-tenancy.md` covers how a pod learns it is dedicated, and the isolation table. The
  `.claude/skills/project-structure` copy gets the same changes (authorization-audit A16).
- **Console.** Close `store-core/console-ui/lessons.md:2293`. The `store-core/console-ui/src/app/models/team.ts:25-35`
  comment says the server now answers per caller, the intersection stays as defence in depth, and `SUPER_ADMIN` was
  never in the answer. Rewrite `uaa-qa.md` ACC-02 to match.
- **Audit pointer.** `authorization-audit.md` gains one line pointing at this register.
- **A2.** `qa/lcl-qa.md` notes that the local uaa secrets are identical, and what that allows.

**When the code lands:** #352 is labelled `type/documentation`. Relabel it `type/bug`, so the release notes list it
under bug fixes rather than documentation.

## cvhome-platform — the pod org declaration

- **`variables.tf`:** add `pod_org_ids = map(string)`, default `{}`, keyed by pod id and set in tfvars only. Orgs do
  not exist yet when the bootstrap runs, and `pod_ids` must stay `list(string)` for the SSM `coalesce`
  (`main.tf:70`).
- **`terraform_data.guards` (`main.tf:151-189`):**
  - every key is a known pod id;
  - the default pod is never dedicated: it hosts every org, and `PodServiceImpl.update` would never change its
    registry row;
  - every value matches `^[0-9a-f]{24}$`.
- **Wiring:** `local.pods` and `local.pod_summaries` (`main.tf:97-116`) gain `org_id`. Both object types
  (`modules/store-pod/variables.tf:9-18`, `modules/store-core/variables.tf:81-94`) gain `org_id = optional(string)`;
  a typed object silently drops any attribute it does not declare.
- **The env entries,** emitted only when set:
  - `modules/store-pod/main.tf`, after `:79`: `COM_ASREVO_CVHOME_POD-INFO_POD_ORG-ID`;
  - `modules/store-core/main.tf`, after `:105`: `COM_ASREVO_CVHOME_PODS[n]_ORG-ID`.

  The pod list also reaches store-core-gateway and tenancy (`needs_pod_list`, `services.yaml:61,121,144`). They bind
  the new field and ignore it.
- **Docs and QA:** update `README.md:398-409`. Add a `qa/platform-qa.md` case: a declared org reaches both modules,
  and the default pod refuses one. It stays `[not verified]` until an environment has a second pod, which waits on
  O9. The repo has no `.tftest.hcl` yet; the guards get the first one.
- **When to set `org_id`:** only in the same apply that adds the pod. On an existing pod the registry row stays
  shared (decision 3) while the pod refuses other orgs' staff on their own stores. Phase E makes the seed report
  that mismatch, and the README says so.

## cvhome-saas.github.io and ideation

- **Docs site.** Correct the isolation claims only; the rest of the site's staleness is known drift.
  - `guide/core-concepts.md:29-31` says a dedicated pod gives "High isolation". Say what is built: a pod declared for
    one org refuses every other org's staff, and on AWS a second pod waits on per-pod service identity.
  - `:21` says every pod has its own database; that depends on the flavour, and it is false on dev and ephemeral.
  - `guide/introduction.md:17` says dedication is per store; it is per org.
  - `introduction.md:35` and `index.md:28` claim more than is built.
- **Ideation.** Two entries in the repo's format (`features/F-NNN-kebab-name.md`, with a README row):
  - **F-009, org co-owners through `OrgMemberApi`:** member roles, and invitations bound to the invited email.
  - **F-010, dedicated pods on AWS:** per-pod service identity (O9), `pod_org_ids` in use, moving a shared pod to
    dedicated, and `PodCount` no longer regenerating pod ids.

## Release, deploy, clean-up

1. **Release.** Once #352 and the platform PR have merged, run `release-product.yml` (`docs/releasing.md`).
   Validate on the load-testing stack with `LOAD_TAG`, per `references/qa.md` § 3. `make selftest` calls
   `user-account/list` as org1-admin, which must still return 200. The release deploys nothing.
2. **Deploy.** This is cvhome-platform's job: `envs/<env>.tfvars` `image_tag`, dev first.
3. **Clean-up.** O1, O2 and O7 may already have been used. Run this after the deploy, in every environment that has
   had users, through the admin APIs as the super admin (decision 9). Record counts in Verification, never names.
   1. **`SUPPORT` holders,** from the uaa user list. A genuine one was created by a person and has metadata `{}`;
      one with `org` or `store` metadata was minted. Cross-check the audit export (`/api/v1/admin/audit`, types
      `user.created`, `user.updated` and `user.role.assigned`, client `admin-sdk`). O7 accounts have no audit row,
      so the user list is what counts. For each account, read its `user.impersonation.started` rows: `actor_id` is
      the account, and `target_id` is whom it acted as.
   2. **`ORG_ADMIN` holders with a `store` key** (`metadata[store]=`). Signup never writes one; only the
      store-scoped endpoint does.
   3. **Store staff whose `metadata.org` does not own their store.** Compare tenancy's store list (store id → org)
      with the uaa users under each `metadata[store]`. After phase D these accounts are refused everywhere; remove
      them anyway.
   4. **Orgs whose owner is one of the accounts above** (`OrgOwnerBackfill`, O11).
   5. **Remove them.** Strip the minted role or the foreign metadata, or delete the account, and revoke its sessions.
      Only disabling it is not enough: the admin who minted it can re-enable it wherever a pre-fix image still runs.
      List the owners each account impersonated, for follow-up.

## Deviations, as built

Filled in as each work item merges.

## Verification

- **The original audit, 2026-09-12, before any fix.** Each case asserted the secure behaviour, so a red case was a
  verified hole. The three test files were not committed, because they were red by design; their cases come back
  as the regression tests of phases A–D.
  - `OrgPodIsolationTest` (autoconfigure): 5 green, 2 red. Another org's store admin and moderator were admitted on
    a shared pod.
  - `OrgUserEscalationTest` (tenancy): 2 green, 5 red. A user created on another org's store, `SUPPORT` granted on
    create and on update, and `ORG_ADMIN` minted by a store admin.
  - `PodPlacementServiceTest`: 10 green.
- **The cross-repo review, 2026-09-13.** Read-only; no build or test ran. Four passes covered every checkout,
  current with origin: cvhome at `23b1b76f4`, cvhome-platform, load-testing, lcl, e2e-testing, the image repos and
  the docs repos.
  - O7 is read from `AdminService.java:160-235` and `BaseException.java:55`, not run.
  - The env binding was run: a binder harness on Spring Boot 4.0.0 (the repo pins 4.0.1).
  - `scripts/standard-check.py cvhome-platform`: the standard is adopted, with one WARN (a stale
    `.githooks/pre-push`).
  - `scripts/impact.py` on the pod files: "local to cvhome". That is the gap orchestrator Phase 2 closes.
- **Per work item.** Each runs the gates in its row, and the orchestrator runs `cross-repo-review` before each PR
  opens.
- **End to end, before the release,** on #352's `lcl --stack org-isolation`:
  - O1: a store admin tries to mint `SUPPORT` → 403.
  - O2: org 2's admin calls `create?store=<org 1 store>` → 404, and a token minted before the fix → 403 on catalog.
  - O7: a refused grant leaves no account.
  - O4: a pod given org 1 refuses org 2's staff on org 2's own store.
