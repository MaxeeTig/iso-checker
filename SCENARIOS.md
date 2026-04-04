# Scenario packs

Scenarios are YAML files. Each file may contain a top-level `scenarios:` list, or a single scenario with `name`, optional `description`, and `steps`.

## Selecting a scenario

- Default: the **first** scenario in the file.
- **`--scenario-name`** (CLI): pick by `name`.

Example:

```bash
iso-checker serve --scenario-file scenarios/default.yaml --scenario-name network_echo --port 8583
```

## Step fields

| YAML key | Meaning |
|----------|---------|
| `id` | Stable id for ledger references (e.g. `auth`). |
| `expect_mti` | MTI the partner must send for this step. |
| `validate.required_fields` | Extra data elements (digits) that must be present in addition to spec **M**andatory fields. |
| `validate.expect_field_values` | Map of DE number → exact value (string); request field must match (e.g. sign-on **24**=`801`). |
| `validate.field48_check_de3` | If true and DE48 present, require tag **002** and match known Processing Code → SVFE type mappings (subset implemented). |
| `validate.matches_step` | Id of a prior step; for reversals, **PAN (DE2)** and **RRN (DE37)** must match that step’s request/response. |
| `respond.mti` | Simulator response MTI. |
| `respond.field_overrides` | String DE number → value overrides on the response. |
| `reference_request` | Optional. Template for the **reference TCP client** (portal “Tests” and `scripts/client_run_scenario.py`). Either a flat map of ISO fields (`t`, digit keys as strings), or a mapping with `inherit_request_from` (prior step `id`), optional `field_overrides`, and optional `copy_response_fields` (target DE → source DE in that step’s **response**). Field **11** (STAN) is overwritten at send time; company **32/41/42** from the portal user’s company override template values when set. |

## Error codes (`error_code` in JSON Lines reports)

| Code | Meaning |
|------|---------|
| `FRAME_TOO_LARGE` | Declared frame length too big or invalid. |
| `PARSE_ERROR` | ISO8583 decode failed (bitmap/fields). |
| `MCO_MISSING` | Mandatory field missing (spec table or scenario extra). |
| `FORMAT_FIELD` | Field value failed basic format checks (e.g. DE12 length). |
| `FIELD48_TAG002_MISSING` | DE48 missing or without tag 002. |
| `FIELD48_TAG002_MISMATCH_DE3` | DE48 tag 002 does not match DE3 mapping. |
| `LEDGER_NO_PRIOR_STEP` | `matches_step` references a step not yet completed. |
| `MATCH_RRN` | Reversal RRN does not match original response. |
| `MATCH_PAN` | PAN does not match original request. |
| `SCENARIO_UNEXPECTED_MTI` | Wrong MTI for the current step. |
| `VALIDATION_RULE` | Generic scenario rule (reserved). |
| `TIMEOUT` | Reserved for future read timeouts. |

Each report row may include `remediation` with a short fix hint.

## Stateful flow

1. Complete step *auth* (e.g. 1100 → 1110). The simulator stores request/response fields for `auth`.
2. Send reversal **1420** with the same **PAN** as original and **RRN (37)** equal to the **1110** response **37**.

See `docs/SVFE_Host2Host_AI_INDEX.md` § Message matching.
