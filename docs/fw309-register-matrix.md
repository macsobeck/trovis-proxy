# FW 3.09 Register and Parameter Matrix

The machine-readable source of truth is
`reference/fw309-register-matrix.json`. It records datatype, signedness, scale,
unit, limits, enums, access flags, dependencies, firmware, sources, and
confidence. Addresses below are SAMSON references; JSON also stores the
zero-based PDU address.

## Confidence policy

- `VERIFIED`: directly proved by an authoritative source or raw artifact.
- `HIGH`: implemented and tested upstream, with Golden values corroborating the
  semantics, but no official 3.09 register list.
- `MEDIUM`: plausible mapping with a remaining semantic ambiguity.
- `UNKNOWN`: unresolved; not read by the PoC.

No Modbus address is inferred from a TROVIS-VIEW item ID.

## Identity and communication

| Stable ID | Reference | Type / scale | Access | Confidence |
|---|---:|---|---|---|
| `controller.model` | HR40001 | uint16 enum | R | HIGH |
| `controller.system_code` | HR40002 | uint16 ×0.1 | R | HIGH |
| `controller.firmware` | HR40003 | uint16 ×0.01 | R | HIGH |
| `controller.hardware_version` | HR40004 | raw uint16 | R | HIGH |
| `controller.serial_number` | HR40006 | width conflict | disabled | UNKNOWN |
| `controller.serial_number_raw` | HR40006 | raw uint16 candidate | R | UNKNOWN |
| `communication.station_address` | HR40143 | uint16 | R | HIGH |

The interpreted serial mapping is disabled because the Golden serial `243179`
does not fit one 16-bit register. Hardware mode may collect HR40006 as a raw
candidate, but it does not treat that value as the serial or raise confidence.

## CO1 / Rk1

| Stable ID | CO/F | Reference | Decode | Access | Confidence |
|---|---|---:|---|---|---|
| `co1.f01` | CO1 F01 | CL1025 | bool | R | HIGH |
| `co1.f02` | CO1 F02 | CL1026 | bool | R | HIGH |
| `co1.f03` | CO1 F03 | CL1027 | bool | R | HIGH |
| `co1.f12` | CO1 F12 | CL1036 | bool | R/W* | HIGH |
| `rk1.flow.maximum` | — | HR41001 | int16 ×0.1 °C | R/W* | HIGH |
| `rk1.flow.minimum` | — | HR41002 | int16 ×0.1 °C | R/W* | HIGH |
| `rk1.room.day` | — | HR41003 | int16 ×0.1 °C | R/W* | HIGH |
| `rk1.room.night` | — | HR41004 | int16 ×0.1 °C | R/W* | HIGH |
| `rk1.heating_curve.slope` | — | HR41006 | uint16 ×0.1 | R/W* | HIGH |
| `rk1.heating_curve.level` | — | HR41007 | int16 ×0.1 K | R/W* | HIGH |
| `rk1.return_curve.slope` | — | HR41009 | uint16 ×0.1 | R/W* | HIGH |
| `rk1.return_curve.level` | — | HR41010 | int16 ×0.1 K | R/W* | HIGH |
| `rk1.return.maximum` | — | HR41011 | int16 ×0.1 °C | R/W* | HIGH |
| `rk1.return.base_point` | — | HR41012 | int16 ×0.1 °C | R/W* | MEDIUM |
| `rk1.controller.kp` | CO1 F12 | HR41065 | uint16 ×0.1 | R/W* | HIGH |
| `rk1.controller.tn` | CO1 F12 | HR41066 | uint16 s | R/W* | HIGH |
| `rk1.controller.ty` | CO1 F12 | HR41067 | uint16 s | R/W* | HIGH |
| `rk1.controller.tv` | CO1 F12 | HR41068 | uint16 s | R/W* | HIGH |

## CO4 / domestic hot water

| Stable ID | Reference | Decode | Access | Confidence |
|---|---:|---|---|---|
| `dhw.setpoint.day` | HR41800 | int16 ×0.1 °C | R/W* | HIGH |
| `dhw.setpoint.maximum` | HR41801 | int16 ×0.1 °C | R/W* | HIGH |
| `dhw.setpoint.minimum` | HR41802 | int16 ×0.1 °C | R/W* | HIGH |
| `dhw.hysteresis` | HR41803 | uint16 ×0.1 K | R/W* | HIGH |
| `dhw.charging_boost` | HR41804 | uint16 ×0.1 K | R/W* | HIGH |
| `dhw.pump_lag_factor` | HR41805 | uint16 ×0.1 | R/W* | MEDIUM |
| `dhw.setpoint.night` | HR41807 | int16 ×0.1 °C | R/W* | HIGH |
| `dhw.return.maximum` | HR41828 | int16 ×0.1 °C | R/W* | HIGH |

## Sensors

AF1 HR40010, VF1 HR40013, RüF1 HR40017, and SF1 HR40023 are signed
temperature words scaled by 0.1 °C. `0x7fff` means unavailable. All are
read-only with `HIGH` confidence.

`R/W*` describes upstream capability, not this application. The Phase-1
transport has no write API. Any later implementation must establish and verify
HR40145 access, range-check the value, write once, read back, and reset access.

## Coverage boundary

The Golden Sample includes many more CO1/CO4/CO5/CO6/CO7/CO8 fields. They are
preserved in `fw309_anlage21.json` but omitted from live reads until an address
is supported by a pinned source and then checked on FW 3.09 hardware. Raw time
program register mapping is also `UNKNOWN`; mock schedules come from the Golden
artifacts, not a claimed Modbus table.

Schema 1.1 classifies groups as identity, communication, configuration, or
runtime and reserves per-point hardware-verification fields. No point is marked
hardware verified yet.
