# Write Access on FW 3.09

## Revalidation on 2026-11-05

The current official FW 3.09 manual, current `trovis-modbus` main source, and
Discussions [#85](https://github.com/Tom-Bom-badil/samson_trovis_557x/discussions/85)
and [#87](https://github.com/Tom-Bom-badil/samson_trovis_557x/discussions/87)
were checked again. The current library still defines HR40145 (PDU 144), enable
code 1732, disable value 0, bounded timeout/mismatch retries, and mandatory
read-back before repeating an ambiguous write. The official
[FW 3.09.xx manual](https://www.samsongroup.com/document/e55731en_3.09.xx.pdf)
still does not publish the raw write-register table. No existing uncertainty is
therefore promoted.

## Phase-1 safety boundary

No write has been performed. The public `Transport` protocol and every CLI
command are read-only. The matrix records upstream `writable` metadata solely
for future planning; it does not authorize use on a controller.

## Evidence found

The pinned `trovis-modbus` source defines:

- HR40145 (zero-based PDU address 144) as `Write-En_Modem`.
- Default enable code `1732` and disable value `0`.
- Function-code 6 single-register writes for modeled Holding Registers and
  function-code 5 for modeled single Coils.
- An enable/disable helper that writes HR40145 and reads it back. A timed-out
  write is treated as ambiguous: state is read before another write is sent.
- Bounded attempts for timeouts/readback mismatches; other Modbus errors fail
  immediately.
- Field validation against raw and engineering-unit limits, a targeted write,
  and readback verification.

[Discussion #85](https://github.com/Tom-Bom-badil/samson_trovis_557x/discussions/85)
reports successful use of code 1732 on TROVIS 5573 FW 3.09. It also reports an
RK1 external operating-mode command at HR40106 (PDU 105). This is valuable
field evidence, not official register documentation.

## Parameters, functions, and modes

The community model marks numerous setpoint/configuration Holding Registers as
writable, including the Rk1 and DHW subset in the matrix. CO function selectors
are more mixed: the read-oriented `Functions` component exposes many selectors
as read-only, while subsystem-specific fields such as Rk1 three-point control
are writable. A complete FW 3.09 writable-coil list is therefore `UNKNOWN`.

Remote operating modes have separate command and effective-state registers.
The current library refreshes write access, writes the command once, and polls
effective state. Discussions #85/#87 indicate the physical circuit selector
must be in Automatic; a remote command does not override a physical manual
position. Ownership/GLT state must be observed rather than blindly toggled.

## What is not established

- The official manual documents local configuration key numbers (including
  user-defined 0100–1900), but does not identify them as HR40145's remote code.
  These mechanisms must not be conflated.
- No official FW 3.09 Modbus register/write table was found.
- Timeout duration of the enable state, any wear limits, multi-register atomic
  behavior, and required ordering across all CO/parameter changes are UNKNOWN.
- No special write function code beyond standard single register/coil writes
  was evidenced for the mapped subset.
- Firmware-specific differences in 3.09 write protection remain UNKNOWN beyond
  the cited field report.

## Preconditions for a future write phase

Use an isolated controller and explicit operator confirmation. Capture a full
pre-write backup, verify model/firmware/system/physical selector, permit only a
small allowlist, validate ranges and dependencies, enable and read back access,
write once, read back the exact target and effective state, then reset HR40145
to zero in a bounded `finally` path. Never retry an ambiguous action until its
result has been read.

## Required state machine

```text
WRITE_DISABLED
  → WRITE_REQUESTED
  → PRECHECK
  → WRITE_ENABLED
  → WRITING
  → VERIFYING
  → WRITE_DISABLED
```

Every error transitions to `STOPPED_UNCERTAIN`, records sent/not-sent/read-back
state, and attempts only the independently safe access-disable cleanup. A write
timeout never transitions directly back to `WRITING`. `WRITE_DISABLED` is the
startup, shutdown, and post-operation default. This state machine remains a
design only until the read-only hardware gate passes.
