# Source Conflicts

| Data point | SAMSON FW 3.09 manual | `trovis-modbus` | `samson_trovis_557x` / field evidence | Assessment and verification |
|---|---|---|---|---|
| Register table | No raw address table | Shared 5573/5573-1 model; base ranges cite Rev. 2.54 | Uses the same library in current code | Treat addresses as HIGH at most; read one point at a time on FW 3.09. |
| Model identity | Names TROVIS 5573-1 | HR40001, raw 55731 | Integration resolves 5573-1 | Read HR40001 and compare with physical label/PDF. |
| Serial number | PDF shows 243179 | HR40006 as one 16-bit integer | No width resolution found | Interpreted mapping stays `UNKNOWN`: 243179 exceeds 65535. Hardware mode captures HR40006 only as an uninterpreted raw candidate. |
| System code | Describes plant codes | HR40002 ×0.1 | Golden file item 5 = 21 | HIGH; verify HR40002 returns 21. |
| Station address | 1–247 in 8-bit mode; up to 32000 with CO6 F02 | HR40143 | Golden shows 247 | HIGH; confirm CO6 F02 before interpreting >247. |
| RK1 return foot/max | UI shows foot/max terminology | HR41011 max, HR41012 base point | `.tro` has related values 65/65 | HR41012 semantic split is MEDIUM; vary only on test hardware and observe both UI fields. |
| Pump lag factor | PDF shows 4.0 | HR41805 ×0.1 | Exact `.tro` item not isolated | MEDIUM; read HR41805 and compare without writing. |
| Time programs | Defines behavior, not raw words | Support deferred/incomplete | `.tro` bit fields correlate with PDF | Modbus mapping `UNKNOWN`; mock/file parser only until official or hardware proof. |
| Write access | Local key-number workflow documented | HR40145, default 1732, reset 0 | FW 3.09 success reported in discussion #85 | Do not equate local key number with remote code. Verify on isolated device with readback and reset. |
| Operating mode | Physical selector constrains remote operation | Separate command/effective/ownership fields | Discussions #85/#87 require Automatic for effective remote control | Confirm physical selector, write command once, poll effective state; out of Phase 1. |

## General rule

Conflicts are retained rather than merged. The official manual governs device
behavior and firmware features; it cannot validate undocumented register
addresses. The current libraries provide executable hypotheses, and the Golden
files validate values/semantics only. Hardware evidence must record firmware,
system code, raw request/response, physical switch position, and UI result.
