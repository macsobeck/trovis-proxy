# Implementation Plan

> This roadmap applies to the device-specific `trovis_manager` research
> harness. The generic gateway has its own architecture and safety boundaries
> under `docs/gateway/`.

## P0 — identify and back up FW 3.09

- [x] Preserve and inspect the PDF and `.tro_55xx` Golden artifacts.
- [x] Pin official/community sources and document conflicts/licences.
- [x] Create the Golden Sample and a source-attributed register matrix.
- [x] Define Pydantic identity, data-point, time-program, result, error, and
  snapshot models.
- [x] Implement a read-only mock, connection manager, safe grouped reads,
  partial snapshots, atomic JSON backup, validation, and `trovisctl` commands.
- [x] Test decoding, scaling, signed values, enums, detection, grouping,
  timeout, retry, partial reads, firmware mismatch, snapshots, and CLI backup.
- [x] Add an explicit real-hardware-only CLI, identity abort gate, per-request
  telemetry/trace, 20-read endurance runner, consistency classification, Golden
  comparison, timestamped reports, and RTU-over-TCP adapter.
- [x] Separate runtime, configuration, identity, and communication values.
- [ ] Validate identity and each enabled matrix block on an isolated real
  TROVIS 5573-1 FW 03.09.00. Until then live support is experimental.
- [ ] Run 20 real reads and retain the resulting acceptance reports.
- [ ] Resolve the serial-number width conflict using the collected HR40006 raw
  evidence and an independent encoding source.

P0 completion for the mock/research PoC is achieved. Production-read readiness
is not: hardware validation is an explicit gate.

## P1 — complete and compare

- Extend the matrix across all relevant CO1–CO8 functions and parameters using
  official or recorded hardware evidence.
- Establish raw Modbus mappings for time programs, holidays, and vacations.
- After a real read-only `PASS`, implement the WritePlan/RestorePlan models,
  risk/dependency validator, dry run, mock-only state machine, verification,
  failure reports, and persistent audit log described in `write-engine.md`.
- Implement a lossless, separately sandboxed `.tro_55xx` importer after its
  remaining XML and binary fields are understood.
- Add recorded-frame integration tests for TCP, serial RTU, RTU-over-TCP,
  disconnects, illegal-address responses, and firmware variants.

## P2 — controlled product expansion

- Local browser UI with audit log, compare view, and diagnostics.
- Qualify one separately authorized, low-risk real write on isolated hardware;
  no automatic rollback claim until inverse operations are proven.
- Additional 557x models and firmware profiles; never silently reuse a matrix
  across profiles.
- Packaging, authentication, secret handling, backup retention, and deployment
  documentation.
