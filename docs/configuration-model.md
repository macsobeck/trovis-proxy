# Configuration Model

Pydantic v2 models in `src/trovis_manager/models.py` define the stable file and
service boundary. Unknown values use `null`; uncertainty is never encoded as a
plausible default.

## Core models

- `ControllerIdentity`: manufacturer, model, firmware, raw hardware version,
  resolved serial, separate serial candidate word, system code, and unit ID.
- `DataPointDefinition`: immutable matrix metadata including address, datatype,
  scaling, limits, enum, access flags, dependencies, source, and confidence.
- `DataPoint`: one decoded runtime value plus its raw value and provenance.
- `TimeProgram`: per-day interval lists with source and confidence.
- `ReadResult`: either a `DataPoint` or a structured `CommunicationError`.
- `ConfigurationSection`: points and time programs grouped by subsystem.
- `ConfigurationSnapshot`: schema version, UTC timestamp, identity, status,
  sections, and accumulated errors.

Definitions and values carry `value_kind`: `identity`, `communication`,
`configuration`, `runtime`, or `unknown`. Matrix definitions also reserve
explicit hardware-verification metadata. All fields remain false/empty until a
reviewed real-controller report proves the mapping; report candidates never
mutate the matrix automatically.

## Snapshot invariants

`status` is `complete` only when every requested point was read and the
firmware matches 03.09.xx. A failed register does not erase other values; it
creates a `CommunicationError` and changes status to `partial`. JSON validation
rejects unknown top-level fields so schema drift is visible.

Decoded values retain `raw_value`. Signed 16-bit conversion happens before the
scale factor; `0x7fff` sensor sentinels become `null`. Enum keys remain raw
integer strings in JSON for deterministic round trips.

The Golden Sample (`reference/fw309_anlage21.json`) is deliberately a separate
document model. It captures all visible TROVIS-VIEW fields, including items that
currently have no trustworthy Modbus mapping, and is never treated as a default.
