# 51 — Multi-user login with per-user OpenRouter credentials

| | |
|---|---|
| **Status** | Draft 0.2 — candidate, not commitment |
| **Date** | 2026-07-21 |
| **Scope** | v2 backlog B1 only |
| **Intended scale** | Approximately 12 trusted colleagues |
| **Governance** | Requires an ADR before implementation |

## 1. Summary

Add authenticated, program-scoped access to the Rulebook Workbench and let
each user fund AI activity through a dedicated key attached to their own
OpenRouter account.

The MVP will use two distinct connections:

1. **Workbench sign-in:** one existing organizational identity provider, such
   as Google Workspace or Microsoft Entra ID, establishes who the colleague is.
2. **OpenRouter connection:** OpenRouter's PKCE authorization flow provisions a
   dedicated, user-controlled API key for that colleague.

These connections answer different questions:

- Workbench authentication answers, "Who is this person?"
- A recorded authority basis answers, "Why may this person act in this program
  role?"
- OpenRouter authorization answers, "Which account pays for this model
  request?"

None may substitute for another. Possessing an OpenRouter key is not evidence
that someone is a Program Owner, Principal, Policy Reviewer, or other governed
role.

The application will remain a single-team, single-server system. This is not
general-purpose SaaS multi-tenancy.

## 2. Definitions

| Term | Definition |
|---|---|
| **Workbench identity** | The stable internal user identity bound to an organizational identity-provider issuer and subject. Names and email addresses are attributes, not identity keys. |
| **Authority basis** | The documented source establishing why a Workbench identity may exercise a program role—for example, a program charter, sponsor designation, ratified artifact, or Principal delegation. |
| **Identity assurance** | The method by which the Workbench knows who performed an action: `legacy_self_asserted` for pre-authentication records or `oidc_authenticated` for post-cutover organizational sign-in. |
| **Role assignment** | A program-specific record connecting a Workbench identity to a governed role and its authority basis. An administrator records a role assignment but does not create the underlying authority. |
| **OpenRouter credential** | A dedicated user-controlled API key provisioned through OpenRouter and stored by the Workbench in encrypted form. |
| **Producer** | The human accountable for producing or materially editing an artifact subject to an independence rule. Model authorship and the human operator who initiated or accepted model output are recorded separately. The ADR must fix the exact producer rule for each governed action. |
| **Run handoff** | An explicit transfer of paused AI work from one authorized user to another, creating a new run segment and billing source without silently changing the credential used by an existing segment. |
| **Break-glass access** | Exceptional, time-limited access to restricted content, supported by a recorded reason, approval or incident basis, and a security event. |

## 3. Problem

The current application is single-user:

- It holds one process-wide `OPENROUTER_API_KEY`.
- API endpoints are unauthenticated.
- A user types their name and selects a role when taking a governed action.
- Some ratification artifacts mark that client-supplied identity as verified.
- Model overrides, spend totals, and recent run records are process-global.
- Anyone who can reach the server can list and access every program.
- Decision-log identifiers are calculated from the current line count and are
  unsafe under simultaneous writes.

See the current
[model router](../../workbench-app/src/workbench/router.py),
[server state](../../workbench-app/src/workbench/server.py), and
[ratification path](../../workbench-app/src/workbench/server.py).

This prevents reliable enforcement of identity, authority, reviewer
independence, per-user spending, restricted-store access, or concurrent program
use.

It also creates a provenance boundary at authentication cutover: historical
decisions were made under a self-asserted identity system, while future
decisions will be authenticated. Those assurance levels must not be silently
conflated.

## 4. Product decision

### Recommended MVP

- Deploy one shared Workbench instance behind HTTPS.
- Use one organizational OpenID Connect provider for login.
- Permit access only to an administrator-maintained allowlist.
- Use identity-provider issuer and subject—not name or email—as the external
  identity key.
- Give users program-specific memberships and role assignments with authority
  bases.
- Connect OpenRouter through its PKCE flow using S256.
- Exchange the OpenRouter authorization code on the Workbench server.
- Encrypt each resulting API key before storing it.
- Resolve the OpenRouter credential from the authenticated initiating user for
  each model request.
- Do not retain a shared application-wide fallback key once multi-user mode is
  enabled.
- Preserve the existing governed artifact filesystem, adding a small SQLite
  control database for accounts, sessions, credentials, membership, and usage.

OpenRouter supports PKCE with S256 and exchanges the resulting authorization
code for a user-controlled API key. The exchange also returns the associated
OpenRouter user ID. See the
[OpenRouter OAuth PKCE documentation](https://openrouter.ai/docs/guides/overview/auth/oauth).

### Explicitly rejected for the MVP

- Building Workbench passwords, password resets, or multifactor authentication.
- Asking users to paste existing raw API keys into a browser form.
- Storing an OpenRouter key in browser local storage.
- Using a shared OpenRouter key for all colleagues.
- Accepting or retaining OpenRouter Management API keys.
- Using OpenRouter authorization as the Workbench identity system.
- Supporting multiple organizational identity providers in the first release.
- Giving application administrators blanket access to restricted content.
- Treating role assignment as proof of the underlying governance authority.
- Silently switching an AI job to another user's credential.

If the organization uses Google Workspace, configure Google only. If it uses
Microsoft 365, configure Entra ID only.

## 5. Goals

The MVP must:

- Let an allowlisted colleague sign in without receiving a Workbench password.
- Bind governed actions to an authenticated, stable user identity.
- Bind governed roles to explicit authority bases.
- Enforce program membership and program-specific roles on the server.
- Enforce only the action-specific independence rules required by the governing
  specification.
- Preserve legitimate one-person-many-roles pilot operation where no
  independence rule applies.
- Let each user connect, inspect, replace, test, and disconnect their own
  OpenRouter credential.
- Use the initiating user's key for every AI request and run segment.
- Attribute usage and cost to the user, program, task, and run.
- Prevent keys from appearing in logs, responses, provenance stamps, exports,
  git, or plaintext backups.
- Revoke Workbench sessions and delete locally stored credentials when an
  account is deactivated.
- Allow users without an OpenRouter connection to read authorized material and
  perform permitted human-only actions.
- Classify all pre-authentication decisions honestly as self-asserted without
  rewriting append-only history.
- Support explicit, provenance-visible handoff of paused work to another
  authorized user.

## 6. Non-goals

The MVP will not provide:

- Public registration or external customer accounts.
- General SaaS tenant isolation.
- SCIM provisioning or automatic directory synchronization.
- Multiple sign-in providers.
- OpenRouter organization or workspace administration.
- Automatic remote deletion of a user's OpenRouter key.
- Shared billing or reimbursement.
- Multiple OpenRouter credentials per user.
- Provider-specific BYOK credentials such as direct Anthropic or OpenAI keys.
- High availability, multiple regions, or multiple application servers.
- A comprehensive redesign of the governed artifact filesystem.
- Blanket separation of every role or governed action.
- Retroactive conversion of historical self-asserted decisions into
  authenticated decisions.

## 7. Identity, role authority, and program membership

### 7.1 System Administrator

A small number of trusted administrators may:

- Allow or deactivate Workbench accounts.
- Record program membership.
- Record role assignments and their authority bases.
- Set per-user and per-program application spending ceilings.
- View security events and credential status, but never credential values.
- View restricted-store metadata, but not restricted content by default.

Administrators do not automatically acquire Program Owner, Principal, Policy
Reviewer, or other program authority.

### 7.2 Program Owner designation

The Program Owner exists before Purpose Statement ratification; ratification
cannot be the act that creates the role.

For a new program:

1. A sponsor, charter, or equivalent program-creation basis identifies the
   initial Program Owner.
2. An administrator records that designation and its authority basis.
3. The Purpose Statement names the Program Owner in its roles block.
4. Ratification is permitted only when the authenticated ratifier matches the
   recorded designation.
5. A mismatch blocks ratification and requires a governed role correction or
   new authority basis.

The administrator records the designation but does not originate its authority.

### 7.3 Other governed roles

Every program role assignment records:

- Workbench user ID
- Program ID
- Role
- Authority-basis type
- Authority-basis reference
- Person who recorded the assignment
- Effective timestamp
- Optional expiry or revocation timestamp

Principal and delegate assignments require an authority basis appropriate to
the power exercised. Identity authentication alone does not establish Principal
legitimacy.

### 7.4 Program member

A member may see only programs to which they have been assigned. Their
permitted actions derive from program roles:

- Program Owner
- Scope Owner
- Distillation Lead
- Policy Reviewer
- Corpus Steward
- Principal or named delegate, in redesign mode

The server derives the user's name and roles from authenticated records. Client
requests must no longer be authoritative when they submit `name` or `role`.

### 7.5 Restricted material

- Program members may read governed artifacts for assigned programs.
- Restricted content requires program membership plus an explicit
  `restricted_reader` permission or a more specific consent rule.
- Application administrators see restricted-store inventory, size, retention,
  and integrity metadata—not content.
- Raw model archives receive the same protection as the sensitive inputs they
  contain.
- Break-glass access must be time-limited, justified, and logged.
- The server operator's unavoidable filesystem access is documented as a
  residual technical risk, not represented as ordinary application
  authorization.

## 8. Reviewer independence

One person may hold several roles in a pilot. Independence is enforced between
specified actions and producers, not by blanket role separation.

### Independence matrix

| Governed activity | MVP rule |
|---|---|
| P2.6 fidelity-sample adjudication | The adjudicating Policy Reviewer must differ from the human producer of the sampled distillation. At least one Policy Reviewer must be independent of the Distillation Lead. |
| P4.6 independent review | The ADR must define the relevant producer and required separation before this gate is automated. |
| Independent second census | Existing model, team, or method diversity rules remain; authentication does not replace them. |
| Ordinary refactor or redesign disposition | No additional two-person requirement unless the governing specification explicitly creates one. |
| Program Owner holding another role | Permitted unless a particular action pair requires separation. |
| AI-generated proposal | AI authorship alone does not create a second human. A person who materially edits or adopts authorship is recorded separately from the initiating operator. |

Until the ADR defines “producer” more precisely, the conservative MVP rule
treats the Distillation Lead who initiated and accepted a distillation output
as its accountable human producer.

Where an action requires independence and only one person is available:

- The workflow may run for demonstration.
- The affected audit or gate is marked `non_gating_demo_only`.
- The system may not represent the independence requirement as satisfied.
- The limitation appears in exports.

A generic rule that “one account with two roles never counts” must not be
implemented.

## 9. Primary user journeys

### 9.1 First sign-in

1. The user selects “Sign in with Organization.”
2. The identity provider authenticates the user.
3. Workbench validates issuer, audience, state, nonce, and stable subject.
4. Workbench confirms that the account is allowlisted and active.
5. Workbench creates a server-side session.
6. The user sees only assigned programs.
7. If the user is allowlisted but has no membership, the UI displays “No
   programs assigned.”

### 9.2 Connect OpenRouter

1. An authenticated user selects “Connect OpenRouter.”
2. The server creates a short-lived, one-use PKCE transaction bound to that user
   and session.
3. The browser is redirected to OpenRouter with an S256 code challenge and fixed
   callback URL.
4. OpenRouter authenticates the user and returns an authorization code.
5. The Workbench server exchanges the code using the stored verifier.
6. The server validates the resulting key using `GET /api/v1/key`.
7. The server rejects management or provisioning keys.
8. The server encrypts the key and stores only safe metadata alongside it.
9. The UI displays status, masked label, limit, remaining credit, reset policy,
   and expiry—never the key.

OpenRouter's current-key endpoint exposes the metadata needed for this
validation, including whether the key is a management key, its limit, remaining
amount, and expiry. See the
[OpenRouter current-key API](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).

### 9.3 Run an AI task

1. The server authenticates the request.
2. It verifies program membership and permission.
3. It checks user, credential, and program budgets.
4. It records the initiating user as the run-segment owner.
5. It loads and decrypts that user's active OpenRouter credential.
6. It makes the model request using that credential.
7. It releases the plaintext credential reference immediately after the
   request.
8. The provenance stamp records the Workbench user ID and credential-record ID,
   but no secret or reconstructable key fingerprint.
9. Usage and cost are persisted against the user, program, task, run, and run
   segment.

### 9.4 Resume a paused run using another user's key

1. A job pauses because its initiating credential is invalid, expired,
   disconnected, or out of funds.
2. The UI reports the completed items and exact stopping point.
3. Another authorized program member selects “Resume with my OpenRouter
   account.”
4. The server creates a new run segment owned by the resuming user.
5. Completed items are not re-run unless explicitly requested.
6. The handoff is recorded with both user IDs, reason, timestamps, previous and
   new segments, and budget state.
7. New model calls use only the resuming user's credential.

The system never changes credentials silently within one run segment.

### 9.5 Replace or disconnect a key

Replacing a key repeats the complete authorization and validation flow. The new
ciphertext is committed before the old local ciphertext is deleted.

Disconnecting:

- Deletes the local ciphertext immediately.
- Disables new AI work for that user.
- Pauses queued work owned by that credential.
- Records a security event.

Because the Workbench will not hold a Management API key, remote revocation
remains the user's responsibility in OpenRouter. The disconnect screen explains
this and links to OpenRouter's key settings.

### 9.6 Deactivate a user

Deactivation must:

- End all active sessions.
- Prevent new login.
- Pause that user's queued AI work.
- Delete the user's locally stored OpenRouter ciphertext.
- Remove active memberships and role assignments.
- Preserve an immutable identity tombstone so earlier decisions remain
  attributable.
- Record a security event.
- Remind the administrator and user to revoke the remote key in OpenRouter.

Historical governed decisions must not be rewritten or anonymized.

## 10. Historical identity-assurance migration

At authentication cutover, the Workbench contains historical decisions and
ratifications produced under self-asserted identity. Some artifacts contain
`identity_verified: true` even though the application did not technically
verify identity.

The migration must preserve history while making its assurance level honest.

### Required migration behavior

For each existing program:

1. Calculate the hash and entry count of the existing decision log.
2. Create a typed `IdentityAssuranceMigration` artifact.
3. Record the cutover timestamp and application version.
4. Classify every covered pre-cutover decision as `legacy_self_asserted`.
5. Identify affected artifacts containing legacy identity-verification claims.
6. Append a migration decision explaining the classification.
7. Leave the original append-only decisions unchanged.
8. Include the migration artifact in governed exports.
9. Render covered names as “self-asserted before authentication,” even when an
   original artifact contains `identity_verified: true`.

Post-cutover decisions record:

- Stable Workbench `actor_user_id`
- Display name at the time of action
- Governed role exercised
- `identity_assurance: oidc_authenticated`
- Authority-basis reference
- Timestamp and session-authentication time

Organizational authentication proves identity, not substantive authority. The
authority-basis reference remains mandatory for role-gated actions.

## 11. Security requirements

### 11.1 Sessions

Use opaque, random, server-side sessions rather than browser-stored JWTs.

The session cookie must be:

- `Secure`
- `HttpOnly`
- `SameSite=Lax`
- Host-only, with a `__Host-` cookie name
- Non-persistent where practical

Sessions expire after 12 hours of inactivity and a seven-day absolute maximum.
Sensitive actions—role changes, account deactivation, break-glass access, and
credential replacement—require recent authentication.

State-changing requests require CSRF protection. Responses containing account,
restricted-store, or credential metadata use `Cache-Control: no-store`. These
controls follow the
[OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

### 11.2 Credential encryption

Each OpenRouter key must be encrypted with an authenticated encryption mode
such as AES-256-GCM.

- Generate a unique random nonce for every encryption.
- Bind the ciphertext to its user and credential-record IDs as authenticated
  additional data.
- Store ciphertext, nonce, algorithm version, and key version in SQLite.
- Store the master encryption key outside SQLite, exports, source control,
  `.env`, and backups.
- Prefer an operating-system keychain or deployment secret store.
- Support master-key rotation from the first release.
- Restrict database and secret-store permissions to the service account.

Authenticated encryption and separation of encryption keys from encrypted data
follow the
[OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html).

Encryption at rest does not protect keys after a complete compromise of the
running server. That is an accepted residual risk for this internal MVP.

### 11.3 Secret handling

The application must:

- Never log authorization headers or OpenRouter exchange responses.
- Disable request-body logging for credential and authorization callbacks.
- Never return a saved key through an API.
- Never include keys in exceptions, telemetry, stamps, artifacts, exports, or
  support bundles.
- Redact OpenRouter-shaped secrets from logs as defense in depth.
- Keep encrypted credential records outside governed program directories.
- Reject use of the legacy environment key when authenticated multi-user mode
  is active.
- Prevent administrators from retrieving ciphertext through ordinary
  application endpoints.

### 11.4 Web security

- Serve the shared instance only over HTTPS.
- Bind the Python application to localhost behind a reverse proxy.
- Permit only the configured hostname.
- Do not enable permissive CORS.
- Set a restrictive Content Security Policy and framing policy.
- Use CSRF tokens for state-changing requests.
- Rate-limit login and authorization endpoints.
- Validate every redirect destination against a fixed allowlist.
- Run one application instance for the MVP unless shared-file mutation and job
  locking are redesigned.
- Encrypt backups and test restoration.
- Apply security updates to the host and dependencies.

### 11.5 OpenRouter privacy

Existing no-training and ZDR routing rules remain Workbench policy and may not
be weakened by a user's OpenRouter settings. Sensitive tasks continue to send
per-request ZDR requirements.

OpenRouter states that prompt retention is opt-in and that per-request
`provider.zdr: true` restricts routing to ZDR endpoints. See OpenRouter's
[data-collection policy](https://openrouter.ai/docs/guides/privacy/data-collection)
and [ZDR documentation](https://openrouter.ai/docs/guides/features/zdr).

### 11.6 Independent security review

Before real credentials or restricted program material enter the shared
instance:

- The implementation must be reviewed by someone who has previously shipped
  OAuth/OIDC, server-side session management, and application-level secret
  encryption.
- The reviewer must be independent of the primary implementer.
- The review covers authentication, authorization, OAuth transaction binding,
  session handling, CSRF, encryption, secret redaction, backup handling,
  deployment, and account deactivation.
- No critical or high-severity finding may remain open.
- Medium findings require documented disposition and owner.
- The review outcome is recorded as a release artifact.

AI-assisted testing and general code review do not satisfy this requirement by
themselves.

## 12. Spending and program continuity

The MVP needs two layers of protection:

1. **OpenRouter-side limit:** users must connect a dedicated key with a finite
   credit limit.
2. **Workbench-side limits:** administrators configure a monthly user ceiling
   and optional program ceiling.

AI work is blocked when:

- The credential has no finite OpenRouter limit or exceeds the
  administrator-set maximum.
- The credential is invalid, expired, disabled, or out of credit.
- The Workbench user or program ceiling has been reached.

Because exact request cost is known only after completion, the Workbench ceiling
prevents the next request rather than guaranteeing that the final request cannot
overshoot. The OpenRouter key limit is the financial backstop.

Program budget and billing source remain distinct:

- Program budget answers how much the program may spend.
- User credential answers whose OpenRouter account funds a run segment.
- A run handoff may change the billing source but not the program budget.
- Every segment's cost remains attributable to its funding user.
- No user becomes financially responsible for another user's work without
  explicitly starting or resuming a segment.

## 13. Data model

A small SQLite control database is sufficient.

Required records:

- `users`: stable Workbench ID, identity-provider issuer and subject, email,
  display name, status, timestamps.
- `program_memberships`: user, program, membership status.
- `role_assignments`: user, program, role, authority basis, recorder, effective
  and revocation times.
- `restricted_permissions`: user, program, permission type, consent or
  authority basis, expiry.
- `sessions`: hashed session token, user, expiry, last activity, CSRF data.
- `openrouter_credentials`: user, ciphertext, nonce, encryption-key version,
  OpenRouter user ID, safe key metadata, status, timestamps.
- `oauth_transactions`: one-use PKCE transaction, user/session binding,
  verifier, expiry, consumed timestamp.
- `usage_ledger`: user, program, task, run, segment, cost, tokens, timestamp.
- `run_segments`: initiating user, credential record, program, state,
  predecessor segment, handoff reason.
- `security_events`: login, logout, failed login, membership change, role
  change, key connection, replacement, disconnection, break-glass access, and
  account deactivation.
- `model_overrides`: user- and/or program-scoped model settings, replacing the
  current global `overrides.json`.
- `identity_tombstones`: durable identity references for deactivated users.

No OpenRouter plaintext secret may appear in any column.

## 14. Required application changes

### Authentication

- Add organizational OIDC login and callback endpoints.
- Add server-side session middleware.
- Protect every API endpoint except health, login, callback, and static assets.
- Add CSRF protection and security headers.

### Authorization and authority

- Add reusable program-membership, role, authority-basis, and restricted-access
  checks.
- Remove client-asserted identity from governed actions.
- Require the authenticated identity to match the role assignment.
- Require the Purpose Statement's Program Owner to match the authenticated
  Program Owner designation.
- Implement the action-specific independence matrix.
- Filter program lists by membership.

### Model router

- Remove `api_key` from mutable process-global router state.
- Pass a request-scoped credential into every model call.
- Persist user/program usage rather than keeping process-global totals.
- Make run history and diversity checks program-scoped.
- Add run segments and explicit handoff.
- Prohibit fallback to another user's credential.

### Storage and concurrency

- Introduce the SQLite control database without moving governed artifacts out
  of their files.
- Serialize mutations to each program.
- Generate decision-log identifiers transactionally.
- Make JSONL appends and artifact replacement atomic.
- Create and validate identity-assurance migration artifacts.

### Governance contracts

Before implementation, adopt an ADR covering:

- Identity provider and identity-assurance standard.
- Program membership and role-authority basis.
- Initial Program Owner designation.
- Principal and delegate authority.
- Action-specific independence rules and the definition of producer.
- Credential custody, disconnection, deletion, and remote-revocation
  limitation.
- Historical identity-assurance migration.
- Run handoff and billing attribution.
- Restricted-store and break-glass access.
- Account deactivation.

The decision-log schema must add immutable actor identity, assurance, and
authority-basis fields. Provenance stamps must add the initiating user, run
segment, and credential-record IDs. Keys, bearer credentials, and
reconstructable secret fingerprints remain prohibited.

## 15. Hosting decision

Hosting must be selected before implementation because it fixes callback URLs,
identity-provider configuration, secret storage, backup handling, network
exposure, and restricted-data location.

### Option A — Private cloud VM with private-network access

Example shape: a small encrypted Linux VM in an agreed region, reachable
through the organization's private overlay network, with HTTPS, a reverse
proxy, encrypted backups, and a deployment secret store.

Advantages:

- Small public attack surface.
- Stable callback URL.
- Straightforward persistent SQLite and filesystem storage.
- Clear data location.
- Full control over backup and encryption.

Costs:

- Colleagues may need a private-network client.
- The team owns operating-system maintenance and backups.
- OIDC and OpenRouter callback behavior must be verified against the private
  hostname.

**Recommendation for the MVP.**

### Option B — Public managed application platform

Advantages:

- Managed HTTPS and stable public URL.
- Easier browser access.
- Less operating-system administration.

Costs:

- Publicly reachable attack surface.
- Persistent-volume, SQLite, backup, and secret-store behavior varies by
  platform.
- Greater dependency on platform data-residency and logging controls.
- May require additional access-proxy controls.

Suitable if private-network client installation is unacceptable.

### Option C — Office workstation or Mac mini

Advantages:

- Low incremental hosting cost.
- Physical control of storage.

Costs:

- Weak availability and disaster recovery.
- Residential or office network complexity.
- Harder stable callbacks and remote access.
- Physical-custody and backup burden.
- Risk that a personal machine becomes the production security boundary.

Acceptable only for a short, non-sensitive pilot; not recommended for regular
use.

The hosting choice and selected data region must be recorded in the ADR.

## 16. Threat model

| Threat | Required mitigation |
|---|---|
| Stolen database | Authenticated encryption; master key stored separately |
| Cross-user key use | Request-scoped credential resolution; concurrency tests |
| Role or name spoofing | Ignore client identity claims; derive identity and role server-side |
| Administrator invents authority | Mandatory authority basis; admin records but does not originate designation |
| Unauthorized program access | Membership check on every program route |
| Unauthorized restricted-content access | Separate restricted permission; no blanket admin read; break-glass logging |
| OAuth callback interception or replay | PKCE S256; short-lived one-use transaction bound to session |
| Session theft | HTTPS; secure cookie; idle and absolute expiry; session revocation |
| CSRF | SameSite cookie plus CSRF token |
| XSS exposing credentials | Key never returned to browser; CSP; HttpOnly session cookie |
| Secret leakage through logs or exports | Redaction, logging restrictions, export allowlists, automated scans |
| Unbounded personal spending | Dedicated limited key plus Workbench ceilings |
| Program stalls when a key fails | Pause and explicit logged handoff to a new run segment |
| Historical provenance appears verified | Cutover migration classifies legacy entries as self-asserted |
| Departed colleague retains access | Immediate Workbench deactivation and session revocation |
| Compromised running server | Accepted residual risk; minimize host access and rotate affected keys |

## 17. Acceptance criteria

The feature is ready for pilot only when:

### Authentication and authorization

- Every protected API returns `401` without a valid session.
- A nonmember cannot discover, read, or mutate a program.
- A member without the required role receives `403`.
- Governed actions use the authenticated account, not submitted names or roles.
- Program Owner actions require a matching role assignment and authority basis.
- An administrator cannot grant themselves substantive program authority
  without recording an external basis.
- A user may hold multiple roles.
- Only action pairs identified in the independence matrix require different
  users.
- A solo demonstration cannot satisfy an independence gate and is labeled
  `non_gating_demo_only`.

### Credential protection

- Two simultaneous mocked model calls from different users demonstrably use
  different credentials.
- No secret appears in logs, API responses, stamps, governed artifacts,
  exports, git status, or plaintext database searches.
- A copied database cannot decrypt credentials without the separate master key.
- PKCE replay, expired transactions, and callbacks bound to another session
  fail.
- Invalid, management, provisioning, expired, and over-limit OpenRouter keys
  are rejected or disabled.
- Disconnecting a credential prevents subsequent AI work.
- Deactivating a user revokes sessions and deletes local credential ciphertext.

### Historical assurance

- Every pre-cutover program has a validated identity-assurance migration
  artifact.
- The artifact records the covered decision-log hash and count.
- Existing append-only decision entries remain byte-for-byte unchanged.
- UI and exports visibly distinguish legacy self-asserted actions from
  authenticated actions.
- Legacy embedded `identity_verified: true` fields are not presented as
  technically verified.

### Runs and budgets

- A background job never changes credentials silently.
- A failed credential pauses the run at a deterministic boundary.
- Another authorized user can resume in a new segment.
- The handoff identifies both users and preserves completed work.
- Costs reconcile by user, program, run, and segment.
- Program budget remains enforced across handoffs.

### Restricted material and deployment

- Application administrators cannot read restricted content by default.
- Break-glass access requires recent authentication, reason, authorization
  basis, expiry, and logging.
- Sensitive tasks continue to fail closed when ZDR-eligible routing is
  unavailable.
- Concurrent program mutations do not duplicate decision IDs or corrupt
  artifacts.
- Existing workflow and contract tests remain green.
- Backup restoration has been tested.
- The independent security review is complete with no open high or critical
  findings.

## 18. Delivery plan and estimate

For one engineer familiar with the codebase:

1. **ADR, contracts, historical migration design, and hosting decision — 3–5
   days**
2. **OIDC login, sessions, users, and program membership — 4–6 days**
3. **Role authority, independence rules, and restricted access — 3–5 days**
4. **Encrypted OpenRouter connection and request-scoped routing — 4–6 days**
5. **Usage ledger, run handoff, and concurrency safety — 3–5 days**
6. **Security tests, migration, deployment, and pilot fixes — 3–5 days**

Estimated implementation total: **20–30 engineering days**, approximately four
to seven calendar weeks depending on identity-provider and hosting setup.

Independent security review and remediation should receive an additional
**2–4 specialist days**, scheduled before the pilot handles real credentials or
restricted data.

## 19. Rollout

- Select hosting, region, identity provider, and security reviewer before
  implementation.
- Begin with two pilot users and one non-sensitive test program.
- Run the legacy identity-assurance migration and inspect its rendering.
- Verify separate identity attribution, role authority, key usage, spending,
  and offboarding.
- Expand to four users across several roles.
- Exercise both an allowed one-person-many-roles case and a prohibited
  independence case.
- Force a key exhaustion and test explicit run handoff.
- Conduct deliberate database-copy, log-leak, authorization-bypass, and
  backup-restoration tests.
- Complete the independent security review and remediate required findings.
- Add remaining colleagues only after all pilot acceptance criteria pass.
- Keep the old single-user configuration available only as a local development
  mode, never as a fallback in the shared instance.

## 20. Decisions required before implementation

1. Which single organizational identity provider will be used?
2. Which hosting option and data region will be used?
3. Will private-network access be mandatory?
4. Who may administer accounts and record program membership?
5. What sources are acceptable authority bases for each governed role?
6. Who designates the initial Program Owner?
7. How is “producer” defined for P2.6 and P4.6 independence?
8. What maximum OpenRouter key limit and monthly Workbench ceiling are
   appropriate?
9. Which roles receive restricted-content access?
10. Who may authorize break-glass access?
11. How long should sessions, security events, and inactive accounts be
    retained?
12. Will remote OpenRouter revocation remain a documented manual step for the
    MVP?
13. Who will perform the independent security review?

The recommended defaults are: one existing organizational identity provider, a
private encrypted VM in an agreed region, private-network access,
program-specific membership, authority-basis-backed roles, dedicated limited
OpenRouter keys, least-privilege restricted access, explicit run handoffs,
manual remote revocation, and specialist security review before pilot use.
