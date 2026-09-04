# Campus — Data Model

Filled in per phase. Each app owns its models; this file is the index and the
place where every **PII field** is listed with its **purpose** and **retention**
(the model carries the same via `SensitiveModel.PII_FIELDS` / `PII_PURPOSE`).

## Conventions

- All domain models inherit `apps.core.models.BaseModel` (UUID pk + timestamps).
- Anything holding high-sensitivity PII inherits `SensitiveModel` — the audit
  layer logs *reads* of these, and retention treats them with the shortest
  configured window.
- Records are `SoftDeleteModel` where a delete could orphan history; only
  retention/erasure jobs hard-delete, and they audit it.
- Encrypted columns use `EncryptedTextField` / `EncryptedCharField`
  (`apps/core/fields.py`). They are not queryable by value, by design.

## accounts  *(Phase 0/1)*

- `User(AbstractUser)` — `role`, `must_use_mfa`, `last_password_change`.
- `StaffInvite` — single-use, expiring, no password.

| PII field | purpose | retention |
|---|---|---|
| `User.email`, `first_name`, `last_name` | account identity, notifications | while the account is active + 90 days |

## audit  *(Phase 0/1)*

- `AuditEntry` — append-only. Object type + id + action + actor snapshot + IP.
  No field values.
- Retention: `RETENTION_AUDIT_LOG_DAYS` (default ~10 years).

## people  *(Phase 2)*

Planned: `Student`, `Guardian`, `GuardianLink` (relationship + custody flag),
`EmergencyContact`, `AuthorizedPickup`, `Observation`, `Document`.
PII table to be completed here.

## health  *(Phase 2 — all encrypted)*

Planned: `Allergy`, `Condition`, `Medication`, `ActionPlan`. Encrypted fields:
allergen, reaction, condition name, medication name + dose + schedule, plan text.
Retention: shortest window; erased with the student.

## registration  *(Phase 2)*

Planned: `Application`, `WaitlistEntry`, `Offer`, `Enrolment`, `Consent`
(`kind`, `version`, `granted_at`, `granted_by`), `UploadedDocument` (encrypted).

## scheduling / attendance  *(Phase 3)*
## lessons  *(Phase 3)*
## grades  *(Phase 4)*
## communication  *(Phase 4 — email only)*
## booking  *(Phase 5)*
## billing  *(Phase 7 — placeholder)*

Planned: `FeeSchedule`, `Invoice`, `InvoiceLine`, `Payment` (manual only),
`Credit`. No card data. `PaymentGateway` interface + `ManualGateway` +
`StripeGateway` stub.

## reporting  *(Phase 2+)*

No models of its own — jobs and exports over the above: retention purge /
anonymize, right-to-erasure, data-subject access export.
