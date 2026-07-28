# AskVera Optional Enhancements Rollout

## Purpose

This runbook covers three optional additions:

1. richer negative feedback;
2. portal users and role-based access control;
3. managed widget instances.

The work is isolated from retrieval and answer generation. Every capability is
off by default and can be rolled back by disabling its feature flag.

## Feature matrix

| Capability | Database migration | Admin flag | Runtime flag | Default |
| --- | --- | --- | --- | --- |
| Expected answer after Not helpful | `20260728_01_feedback_expected_answer.sql` | `FEEDBACK_EXPECTED_ANSWER_ENABLED` | Same flag | Off |
| Users and RBAC | `20260728_02_admin_rbac.sql` | `ADMIN_USER_MANAGEMENT_ENABLED` | `ADMIN_RBAC_ENABLED` | Off |
| Widget builder | `20260728_03_widget_configs.sql` | `WIDGET_CONFIG_ADMIN_ENABLED` | `WIDGET_CONFIG_RUNTIME_ENABLED` | Off |

## Roles

| Role | Intended access |
| --- | --- |
| Super Admin | All markets and portal sections; manage users and widgets |
| Country Admin | Assigned markets; Flow, Knowledge, and Insights only |
| Section-scoped Admin | Only explicitly granted market, section, and permission combinations |
| Auditor | All-market read-only access to Users and Audit |

Country and section enforcement occurs in FastAPI and PostgreSQL queries.
Hidden navigation is not treated as authorization.

The first Super Admin is not chosen by login order. Before enabling RBAC, set
`ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL` to the one approved administrator email.
AskVera serializes the first-login transaction and rejects every other identity
until that account has bootstrapped the administrator table. The setting can
remain configured after bootstrap; it cannot create a second Super Admin.

## Permission matrix

| Capability | Permission | Super Admin | Country Admin | Section-scoped Admin | Auditor |
| --- | --- | --- | --- | --- | --- |
| Live flow | `flow:view` | All markets | Assigned markets | Explicit markets only | No |
| Insights | `insights:view` | All markets | Assigned markets | Explicit markets only | No |
| Knowledge list | `knowledge:view` | All markets | Assigned markets | Explicit markets only | No |
| Knowledge upload/stage | `knowledge:stage` | All markets | Assigned markets | Explicit markets only | No |
| Knowledge publish | `knowledge:publish` | All markets | No by default | Explicit markets only | No |
| Widget configuration | `widget:manage` | Yes | No | Explicitly granted | No |
| User list | `users:view` | Yes | No | No | Read only |
| User administration | `users:manage` | Yes | No | No | No |
| Audit log | `audit:view` | Yes | No | No | Read only |

Every market-aware route intersects the requested market with the caller's
stored RDS scope. A section being visible in the portal does not authorize an
API request. Global knowledge uploads require Super Admin access.

## Database migrations

Apply in filename order after taking a PostgreSQL backup:

1. `20260728_01_feedback_expected_answer.sql` adds nullable, backward-compatible
   expected-answer feedback fields.
2. `20260728_02_admin_rbac.sql` creates administrator profiles, structured
   scopes, and audit records.
3. `20260728_03_widget_configs.sql` creates managed widget configuration,
   locale, origin, status, and public-key storage.

The migrations are additive. Do not remove the new columns or tables during a
flag rollback.

## Widget origin rules

- Origins must be complete HTTPS or approved local-development origins.
- Paths, queries, fragments, credentials, and wildcards are rejected.
- The request origin must exactly match an active widget registration.
- The selected market and language must exist in that same registration.
- Key rotation invalidates the prior public key.
- Disabling a widget prevents new initialization.
- Widget changes publish a version through the existing Valkey connection so
  every API worker drops its local widget and origin caches. If Valkey is
  temporarily unavailable, managed widget authorization entries expire locally
  within 30 seconds.
- Create, update, key rotation, and disable actions are written to
  `admin_audit_log`.

## Cognito and IAM requirements

Production must use `ADMIN_AUTH_MODE=cognito` with
`ADMIN_AUTH_ALLOW_API_KEY=false`. The EC2 instance role needs only the Cognito
administrator actions used by the portal:

- `cognito-idp:AdminCreateUser`
- `cognito-idp:AdminDeleteUser` for failed-create compensation
- `cognito-idp:AdminAddUserToGroup`
- `cognito-idp:AdminEnableUser`
- `cognito-idp:AdminDisableUser`
- `cognito-idp:AdminGetUser`

Scope those actions to the configured user pool. User creation and invitation
resends place the identity in `ADMIN_COGNITO_REQUIRED_GROUP`; the default group
is `AskVeraAdmins`.

AskVera checks the RDS administrator status on every Cognito-authenticated
request. Disabling an account updates RDS before calling Cognito, so access is
blocked even if Cognito is unavailable. This is intentional because a revoked
Cognito JWT can still pass offline signature and expiry checks until it expires.
An administrator cannot disable their own account, demote their own Super Admin
role, or remove the last active Super Admin.

## Recommended sequence

1. Back up PostgreSQL and apply all three additive migrations.
2. Deploy the code with all feature flags off.
3. Confirm existing widget initialization, consent, chat, feedback, and admin
   portal behavior.
4. Enable expected-answer feedback and test helpful, not-helpful, skip, PII,
   retry, keyboard, and mobile behavior.
5. Set `ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL`, enable RBAC and user management,
   then sign in as that exact account. Create one restricted test administrator
   and verify the invitation, Cognito group membership, and both allowed and
   denied market access.
6. Enable widget administration and create a disabled non-production record.
7. Validate the embed snippet, exact origin checks, locale restrictions, key
   rotation, and disable behavior.
8. Enable the RDS widget runtime only after the non-production record passes.
9. Monitor authentication failures, denied actions, widget initialization
   failures, feedback delivery, and API latency.

## Rollback

Set the affected flag to `false` and restart the API. For widget incidents,
disable `WIDGET_CONFIG_RUNTIME_ENABLED` first so the service returns to the
existing static registry. The additive tables and columns may remain in place;
they do not affect legacy execution when their flags are off.

## Assumptions requiring deployment confirmation

- The administrator Cognito user pool ID and app client are the intended UAT
  resources.
- `ADMIN_BOOTSTRAP_SUPER_ADMIN_EMAIL` names the approved initial administrator.
- Cognito is allowed to send invitation email.
- The EC2 role can perform the required Cognito administrator actions,
  including `AdminAddUserToGroup`.
- PostgreSQL migrations are applied before any related flag is enabled.
- The operations portal origin is present in the API CORS configuration.
- Widget loader and stylesheet URLs point to the approved immutable or latest
  CloudFront release.
- Production retention and audit access policies cover the new tables.
- The optional widget rate tier and usage cap are configuration metadata; the
  existing runtime limiter remains authoritative until a tier-aware limiter is
  separately enabled.
- PostgreSQL migration execution must be tested against a recent populated UAT
  backup because this workstation does not contain a production-equivalent
  PostgreSQL service.

## Change manifest

### Backend and configuration

- `config/settings.py`
- `api/routes.py`
- `api/admin_routes.py`
- `services/admin_auth.py`
- `services/admin_users.py`
- `services/analytics.py`
- `services/aws_clients.py`
- `services/db.py`
- `services/widget_configs.py`
- `utils/validators.py`
- `app/widget_registry/service.py`
- `app/widget_registry/rds_provider.py`

### Operations portal

- `admin-portal/src/App.tsx`
- `admin-portal/src/api.ts`
- `admin-portal/src/types.ts`
- `admin-portal/src/styles.css`
- `admin-portal/src/components/InsightsDashboard.tsx`
- `admin-portal/src/components/UsersManager.tsx`
- `admin-portal/src/components/WidgetManager.tsx`

### Customer widget

- `widget-wrapper/src/api/configApi.ts`
- `widget-wrapper/src/api/feedbackApi.ts`
- `widget-wrapper/src/generic-widget/MessageFeed.tsx`
- `widget-wrapper/src/generic-widget/generic-widget.css`
- `widget-wrapper/src/generic-widget/reference-polish.css`
- `widget-wrapper/src/generic-widget/types.ts`
- `widget-wrapper/src/sdk/AskVera.ts`
- `widget-wrapper/src/sdk/WidgetRuntime.tsx`
- `widget-wrapper/src/sdk/mount.tsx`

### Tests, migrations, and documentation

- `tests/unit/test_feedback_expected_answer.py`
- `tests/unit/test_admin_rbac.py`
- `tests/unit/test_widget_config_admin.py`
- `migrations/20260728_01_feedback_expected_answer.sql`
- `migrations/20260728_02_admin_rbac.sql`
- `migrations/20260728_03_widget_configs.sql`
- `README.md`
- `docs/OPERATIONS_PORTAL.md`
- `docs/ASKVERA_DOCUMENT_INGESTION_AND_RETRIEVAL_REFERENCE.md`
- `docs/ASKVERA_OPTIONAL_ENHANCEMENTS_ROLLOUT.md`

## Deployment approvals

The implementation itself does not require AWS mutation. Deployment requires
explicit approval for:

1. PostgreSQL backup and migration execution;
2. Parameter Store updates for feature flags and widget asset URLs;
3. EC2 code deployment and service restart;
4. Cognito administrator permissions and invitation email;
5. operations portal and widget asset publishing;
6. creation of the first managed widget record and its origin allowlist;
7. post-deployment smoke tests and, only after acceptance, feature enablement.
