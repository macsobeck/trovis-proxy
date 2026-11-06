# Write Engine Design — Blocked

## Gate

No write engine is implemented in this repository. The task requires a passing
real-hardware read-only report before mock write execution may be added. That
report does not yet exist, so the public transport still has no write method and
the CLI has no `restore` command.

## Planned model boundary

After the gate passes, a separate module will define:

- `WriteOperation`: point ID, description, current/target engineering and raw
  values, address space/address, function code, scaling, protection,
  dependencies, order, verification strategy, and risk.
- `WriteValidation`: identity, firmware, range, enum, dependency, writable, and
  protection results with blocking reasons.
- `WritePlan`: immutable source/target snapshot IDs, ordered operations,
  unchanged/blocked counts, validation result, and dry-run flag.
- `RestorePlan`: complete pre-write backup reference, controller identity,
  WritePlan, and explicit operator authorization metadata.
- `WriteResult`: sent/not-sent/ambiguous state, raw response, error, timestamps,
  and audit reference.
- `VerificationResult`: read-back value/raw value and exact/range/effective-state
  verdict.

Risk classes are `LOW`, `MEDIUM`, `HIGH`, and `BLOCKED`. Unknown mapping,
firmware mismatch, read-only metadata, missing dependency evidence, or
unverified write protection always produces `BLOCKED`.

## Planned pipeline

```text
Snapshot → semantic diff → validation → dependency analysis
         → immutable WritePlan → dry run → pre-write backup
         → apply one operation → read-back → verify → audit
```

A snapshot can never directly emit Modbus writes. Dry run performs every check
except transport mutation. A future real apply must re-identify the controller,
create a complete recovery backup, verify it is `complete`, and abort otherwise.

A future `trovisctl restore --dry-run SNAPSHOT` will be permitted before any
apply command. It will report unchanged, planned, blocked, and protected counts
without constructing or calling a live write transport.

## Planned persistent audit log

Audit records will be append-only JSON Lines. Each record contains UTC
timestamp, plan/operation IDs, controller serial and firmware, point ID,
previous/target engineering values, raw current/target words, address/function
code, access state, send result, read-back, verification status, and any
exception. File synchronization and restrictive permissions are required before
the next operation proceeds.

## Failure behavior

A write timeout is ambiguous. State must be read before any retry. On a failed
read-back, lost access, connection loss, exception, or partially executed plan:
stop immediately, disable access where safely possible, preserve the recovery
snapshot, and emit an audit/incident report. No automatic rollback is claimed
until every affected point has an independently verified inverse operation.

Mock-only implementation—including accepted-but-wrong read-back, timeout,
connection loss, exception, invalid value, read-only point, wrong firmware,
missing/lost access, dependencies, partial plans, and audit persistence—remains
a gated follow-up after a real read-only `PASS`.
