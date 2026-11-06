# Restore Safety Contract

Restore is currently unavailable. These invariants are mandatory for any later
implementation.

## Preconditions

1. Require a passing FW 03.09.00 hardware-validation report for the same device
   profile and matrix revision.
2. Re-identify model, firmware, system, unit ID, and serial immediately before
   the operation.
3. Read the current configuration and persist a `complete` recovery snapshot.
4. Validate snapshot schema, controller compatibility, values, enums,
   dependencies, address confidence, and the explicit write allowlist.
5. Present an immutable dry-run WritePlan and require separate operator
   authorization. `BLOCKED` operations can never be overridden.

## Execution invariants

- Serialize all operations; never write in parallel.
- Default to `WRITE_DISABLED` and enable access only for the shortest bounded
  interval required.
- Never repeat an ambiguous write before targeted read-back.
- Apply one validated operation at a time and verify its exact or documented
  effective state before continuing.
- Persist an audit event with identity, old/target/raw values, response,
  read-back, and verification status.
- Reset write access in a bounded cleanup path and verify the disabled state.

## Abort conditions

Abort before writing if identity changed, firmware is not 03.09.xx, the backup
is partial, any dependency is unknown, or communication is unstable. Stop after
the first ambiguous/failed operation. Preserve what is known, what was sent,
what was verified, and what remains uncertain. Provide the recovery snapshot;
do not advertise automatic rollback.

The first real write must be a separate, narrowly scoped work order on isolated
hardware with an explicitly selected low-risk data point.
