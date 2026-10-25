# Vigilon — Integrated feature audit and login diagnosis

## Mission
Audit the current Vigilon implementation after teammates' feature work, verify integration with the existing Visor UI, and diagnose the user's `Invalid credentials` login failure first. Implement focused fixes for confirmed defects and validate them. Do not merely produce a plan. Do not rebuild completed features or expand product scope.

Communicate findings and the final handoff in Thai; keep shared technical documentation and code identifiers in English. Do not commit, push, merge branches, or deploy.

## 1. Establish the actual baseline
- Read applicable AGENTS.md, README, current implementation/status docs, feature contracts and ownership docs. Respect configured Codex/ECC workflows and available MCP tools; do not reinstall tools or alter global configuration.
- Inspect Git status, current branch, HEAD, local branches and recent history. Preserve all existing work, including task.md. Do not stash, reset, clean, or switch a dirty checkout automatically.
- If clean, create/use `fix/integration-audit` from the current verified integration baseline. Do not assume main contains every teammate feature. Report missing/unmerged features as such, not as code defects; do not merge them automatically. Read other local branches only where necessary to establish delivery status.
- Historical reports only: Map was committed as `4d7cea5`; Live Monitoring branched from it. Map and monitoring were reported to pass 5 and 10 focused tests respectively and 29 backend tests. These are not current test results. Reconcile actual HEAD and migrations instead of trusting these counts.
- Discover actual startup/test commands and installed dependencies. Preserve the existing frontend stack and module boundaries.

## 2. Priority zero: investigate Invalid credentials
Identify the failing layer before changing passwords or data. Never request that the user paste a password into chat, print secrets/password hashes, log login bodies, or expose session cookies.

### Runtime and configuration
1. Identify the UI origin, actual login request URL/method/content type/payload field names, status code, and sanitized response. Verify which local API process/checkout/port serves it. Distinguish backend authentication rejection from validation, network, CSRF, CORS, server, and session-cookie failures incorrectly labelled by the UI.
2. Trace settings precedence through process environment, .env loader, defaults, launch scripts and working directory. Compare API, CLI/bootstrap, worker and migration configuration without dumping .env or full process command lines that may contain secrets.
3. Resolve the effective database target using the application's own configuration: absolute SQLite path, or redacted PostgreSQL host/database/schema. Check for inherited test DATABASE_URL overrides, relative SQLite paths resolving differently, an unintended newly created database, wrong API instance, and stale frontend API configuration. A new terminal does not change an already running API process.
4. Inspect the intended database read-only first. Verify schema revision, expected account existence, identifier matching rules, enabled/locked status and supported password hash format without exposing hash values. Check whether bootstrap is create-only and whether changing bootstrap values in .env affects existing accounts; explain the behavior actually found.
5. Inspect password verification and dependency compatibility, form field mapping, username/email normalization and exception handling. Never trim or otherwise change password semantics to make login pass.
6. If authentication succeeds but the next request fails, investigate cookie domain/path/Secure/SameSite, localhost versus 127.0.0.1, proxy/origin configuration, session persistence and signing-key consistency. Do not weaken security protections as a workaround.

### Corrective action
- Fix confirmed configuration/code defects with the smallest compatible change. Preserve existing users, cameras, plans, incidents, keys and evidence. Do not delete/reseed the database, rotate keys, disable auth, hardcode credentials or add a login bypass.
- Back up operational data with a database-appropriate consistent backup before any necessary migration or data mutation; keep backups out of Git. Test migration changes on a disposable copy first.
- Do not silently reset an existing account or create an operational administrator. If a password is genuinely unknown or the intended account is absent, prepare an exact recovery/bootstrap command using verified existing tooling and a hidden interactive password prompt. If tooling is absent, implement a narrowly scoped local administrative recovery command with identity/target checks and regression tests. Leave execution against the operational account to the user unless explicitly authorized. Respect the established session-revocation policy and document any limitation.
- Verify successful login, authenticated identity, allowed page access, logout, rejected wrong password and unauthorized requests with an isolated test account. Do not claim the user's account was recovered unless that login was actually verified. If user input is needed, continue all independent audit work.
- Provide the root cause with evidence, or a clearly marked unresolved diagnosis plus the exact missing evidence. Do not guess that the password itself is wrong.

## 3. Feature and integration audit
Create `docs/INTEGRATION_AUDIT.md` with a matrix: feature, branch/HEAD availability, implementation evidence, UI entry point, API/persistence, permission checks, test evidence, status, remaining issue and owner. Use PASS / FAIL / PARTIAL / NOT PRESENT / NOT VERIFIED. Separate synthetic/mock coverage from real hardware/model verification.

Inspect and exercise what actually exists:
- **Control Center:** all six panels, synchronized camera/incident selection, correct location/device context; new events must not steal operator selection. Original pages remain reachable.
- **Maps:** plan CRUD, uploads/replacement with keep/clear placements, normalized geometry, zoom/pan/fit, placement Save/Cancel, stale revision conflicts, cross-plan selection, navigation guards, one-plan-per-camera policy if still present, persistence after reload.
- **Monitoring:** shared viewer across Control Center, existing Live Monitoring and camera details; single/2x2 modes, filters/slot selection, bounded preview concurrency, timeout/cancellation/retry, frame-ID freshness, object-URL cleanup, logout/session expiry and no accumulating polling after navigation. Distinguish disabled/offline/stale/worker unavailable states.
- **Devices:** add/edit/test connection, retained or explicitly cleared RTSP credentials, permissions, health and optional metadata. Never return source secrets to the UI.
- **Rules and AI modules:** actual module availability, configuration persistence, normalized zones/lines, supported temporal thresholds/schedules, assignment to the correct source, unavailable weights clearly reported. Verify only scenarios supported by the implementation; do not invent detection capability.
- **Incidents:** filtering/pagination/history, evidence authorization, event-time evidence distinct from live preview, server-validated NEW/ACKNOWLEDGED/RESOLVED/FALSE_ALARM transitions, actor/time/notes and concurrent updates.
- **Notifications:** existing in-app counters/toasts/sound, deduplication and preferences, listener cleanup. External delivery is not implied and must not be sent during QA.
- **Video Analysis:** authorized upload/size/decode checks, FILE job creation/progress/cancel/results/timeline, source/job isolation and explicit synthetic-demo labeling.
- **Settings/auth:** actual roles and backend enforcement, failed save behavior, session expiry, account access and configuration consistency.

For each implemented workflow, check loading/empty/error/offline states, reload persistence, matching IDs/contracts/timestamps, and UI integration. Do not call a feature complete just because a component or endpoint exists. Record missing teammate deliverables without implementing entire absent features in this audit.

## 4. Known worker issue and database integration
- Investigate the previously reported intermittent Windows `PermissionError` when replacing the preview manifest. Reproduce if possible and inspect handle lifetime, atomic publication, reader behavior, frame/manifest consistency and retry bounds. Fix confirmed causes without suppressing failures, serving stale frames as fresh or adding infinite retries. Add targeted regression coverage if changed. If Windows is unavailable, report that reproduction remains blocked.
- Inspect Alembic heads and the combined teammate migration graph, including historical 0004/0005 where present. Do not rewrite shared migration history or blindly stamp the DB. Resolve genuine graph/schema conflicts with appropriate new migrations.
- Test a fresh disposable database and upgrade from the supported pre-integration revision with representative records. Verify records survive upgrades.
- Run PostgreSQL/Compose integration when available, using isolated services/volumes and no operational ports/data. Otherwise mark it NOT VERIFIED; SQLite or Compose config parsing is not equivalent.

## 5. Validation and bounded fixes
Prioritize login blockers, data loss/security problems, broken cross-panel workflows, then reproducible integration regressions. Keep fixes in their owning modules; shared files should remain integration points. Avoid unrelated formatting, framework changes and speculative refactors.

Use repository test commands and meaningful regression tests for each actual fix. Run backend and relevant frontend suites, migrations, syntax/compilation checks and git diff --check. Report current counts and failures honestly.

Use Playwright or an available browser runner against an isolated local API/database/worker:
1. Login, inspect authenticated identity, visit original pages and Control Center.
2. Create a plan, place a controlled camera, save, reload and select it from the map.
3. Inspect live preview and the corresponding existing Monitoring view; switch single/2x2 and navigate repeatedly (at least ten cycles) while checking request cleanup.
4. Use an explicitly synthetic incident to verify event selection -> map/camera/context/detail synchronization -> acknowledge -> history/persistence. Do not attach current live imagery as incident-time evidence.
5. Exercise implemented rule/video/device flows with controlled fixtures and invalid inputs.
6. Verify logout/session expiry and backend role restrictions, including direct API access.
7. Check layouts at 1440, 768 and 375 px, keyboard focus, actionable errors and console/network failures.
8. Observe preview for at least five minutes where a worker can run; record freshness, errors and bounded requests. A synthetic soak is not real-camera validation.

Use isolated environment variables, data directories and ports for tests. Track and stop only processes started by this task. Do not modify physical camera settings or run real inference without configured authorized resources. Never commit generated evidence, uploads, databases, secrets or weights.

## 6. Deliverables and completion criteria
- Focused, validated fixes and regression tests for confirmed in-scope defects.
- `docs/INTEGRATION_AUDIT.md`: tested HEAD/branch, feature matrix, issue severity, reproduction, fixes, current results and explicit blockers.
- `docs/LOGIN_DIAGNOSIS.md`: sanitized runtime/configuration trace, actual cause or unresolved evidence, correction, verified startup steps and exact safe recovery instructions if required. Do not include passwords, hashes, cookies or full database connection URLs containing credentials.
- Update existing README/status/feature contracts only where verified behavior changed. Preserve teammate content.
- Final Thai handoff: what works, what was fixed, whether the user's login is actually restored, tests run, unverified paths, remaining issues ordered by severity with owner, and exact PowerShell commands verified against this checkout.
- State separate readiness outcomes for UI/API integration, synthetic pipeline, real camera, real inference and PostgreSQL deployment. Do not claim overall production readiness from mocks or test counts.
- No commit, push, merge or deployment. Offer a commit message only after reporting the actual final scope.

Start with baseline inspection and login diagnosis, then continue through the integration audit and focused fixes without waiting for approval for ordinary reversible work.
