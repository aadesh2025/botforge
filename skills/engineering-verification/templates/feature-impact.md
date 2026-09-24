# Feature impact

Two parts: the plan (write it before editing) and the report (write it at the end). Compare them.

---

# FEATURE IMPACT PLAN

Feature:
Acceptance criteria:
Domain owner:
Existing abstraction:
Existing implementation to reuse:
Search performed (terms, places, what was found):
Why a new abstraction is needed (only if one is proposed):

Expected files to change:
Files explicitly expected NOT to change:

API impact:
Database impact (tables, migrations, indexes, ownership, deletion, compatibility):
Security impact:
Authorization impact:
Tenant impact (or "not multi-tenant"):
Integration impact:
Frontend impact:
Background-job impact:
Configuration / environment impact:

Tests required:
Documentation required:
Potential ripple effects:

Change budget (files / domains) and the point at which I stop and re-plan:

---

# FEATURE IMPACT REPORT

## Feature

## Domain Owner

## Existing Abstractions

Reused: `<what>`. Created: `<what, and why reuse was not possible>`.

## Files Changed

| File | Planned? | Why |
|---|---|---|
| | yes / no | |

Unplanned changes need an explanation here.

## Files Protected From Change

`<files/areas the plan said would not change>`; confirmed unchanged: `<yes / exceptions>`.

## Security Impact

## Authorization

## Tenant Impact

## API Impact

## Database Impact

## Integration Impact

## Tests

| Test | Covers | Result |
|---|---|---|
| | | |

Checks run: `<commands and outcomes>`. Not run: `<...and why>`.

## Documentation

## Remaining Risks

`<each risk; proven / inferred / unknown>`
