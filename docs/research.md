# Research Summary

## Result

The supplied files consistently describe a TROVIS 5573-1, firmware 03.09.00,
system 2.1, station 247. The PDF is the authoritative Golden Sample for values;
the `.tro_55xx` independently reproduces identity, many parameter values, and
three schedules. Its numeric item IDs are application-level TROVIS-VIEW keys,
not evidence of Modbus addresses.

The current `trovis-modbus` library has the most coherent typed device model:
zero-based conversion, signed/scaled fields, enums, limits, read planning, and
model/system detection. It delegates connection ownership to
`modbus-connection`, which serializes requests, paces messages, reconnects on a
later request, and provides TCP/serial backends plus an in-memory mock.

It is not an executable dependency of this PoC yet. Its shared 5573 address
profile is rooted in a Rev. 2.54 table, the serial mapping conflicts with the
Golden value, and time programs are incomplete. Importing the full model would
silently expose more fields than this FW-3.09 confidence gate allows. Instead,
the pinned metadata is cited field by field and a small isolated decoder handles
only the approved matrix. Replacing that layer with upstream components is the
preferred follow-up once the FW 3.09 subset is validated on hardware.

## Firmware 3.09 assessment

The official February 2026 manual covers FW 3.09.xx and records new behavior
through 3.09. It does not publish a Modbus register table. The community
library's conservative two-heating-circuit ranges are explicitly rooted in a
TROVIS 5573 Rev. 2.54 table and then shared with 5573-1/5575/5576. Accordingly,
matrix addresses are mostly `HIGH`, not `VERIFIED`, for FW 3.09.

Known 3.09 community evidence confirms remote write enable at HR40145 and an
RK1 external-mode register, but Phase 1 exposes neither operation. Real writes
remain out of scope.

## PoC decisions

- A narrow transport protocol has no write method.
- Every request is serialized and bounded by `asyncio.wait_for`; timeout and
  connection failures receive finite retries with exponential backoff.
- Only truly contiguous fields in one address space are grouped (maximum 50
  registers). Failed blocks fall back to single reads for a partial snapshot.
- The mock is the default transport and carries the PDF's identity, parameters,
  sensors, function states, and schedules.
- Live TCP, serial RTU, and RTU-over-TCP adapters are optional and unverified
  on this hardware.

## Open questions

The serial number mapping conflicts with 16-bit width. Hardware validation now
collects HR40006 only as an uninterpreted raw candidate. Complete
FW 3.09 CO/parameter coverage, holidays, vacations, and raw time-program
registers remain `UNKNOWN`. Hardware validation should begin with identity and
one register at a time before enabling the current read matrix.
