# Sources

Research was performed on 2026-11-05. Register claims use pinned repository
revisions; `transport.address` in this project is zero-based PDU addressing.

Write-access evidence was rechecked on the same date against the current
[`trovis-modbus` main source](https://raw.githubusercontent.com/Tom-Bom-badil/trovis-modbus_python-library/main/src/trovis_modbus/data_model.py),
the current project README, and Discussions #85/#87. This confirmed the existing
design evidence but did not provide an official FW 3.09 register table.

## Official SAMSON material

- [TROVIS 5573-1 operating instructions, FW 3.09.xx, English, Feb. 2026](https://www.samsongroup.com/document/e55731en_3.09.xx.pdf) — device functions, CO1–CO8, parameters, communication setup, firmware changes, and local key-number behavior.
- [TROVIS 5573-1 operating instructions, FW 3.09.xx, German](https://leusch.samsongroup.com/document/e55731de_3.09.xx.pdf) — German terminology cross-check.

The public 3.09 manual confirms Modbus RTU/RS-485, 8N1, CO6 F01/F02/F07, and
station-address behavior. It does **not** provide the raw Holding Register/Coil
table used by the community libraries. No public, official 3.09 register list
was found during this phase; such mappings therefore cannot be `VERIFIED` from
SAMSON documentation alone.

## Community implementations

- [`trovis-modbus_python-library` at `c4a8349`](https://github.com/Tom-Bom-badil/trovis-modbus_python-library/tree/c4a8349b64fc5407aced981ec79ac81217db876a) — current typed registers/coils, scaling, limits, detection, grouping, and tests.
- [`samson_trovis_557x` at `ebfeaaa`](https://github.com/Tom-Bom-badil/samson_trovis_557x/tree/ebfeaaaa5ff104c741e610fdf3b497a184ef9b92) — Home Assistant integration and device behavior.
- [`modbus-connection` at `28ebad9`](https://github.com/home-assistant-libs/modbus-connection/tree/28ebad97fed1a4ce5716403b1be0a611aaa4eeb5) — connection lifecycle, request pacing/serialization, grouped model reads, mock backend, and backend error behavior.
- [Discussion #85](https://github.com/Tom-Bom-badil/samson_trovis_557x/discussions/85) — successful FW 3.09 write-access and RK1 operating-mode report.
- [Discussion #87](https://github.com/Tom-Bom-badil/samson_trovis_557x/discussions/87) — automatic/manual selector and effective-mode constraints.

The cloned wikis were inspected at `b8c67d…` (`samson_trovis_557x`) and
`20436c…` (`trovis-modbus`). Time-program support is described as incomplete.

## Local primary evidence

- `reference/2026_11_05_Trovis_5573_1_Konfig.pdf` — 17-page TROVIS-VIEW export; values are `VERIFIED` for this installation only.
- `reference/2026_11_05_Trovis_5573_1_Konfig.tro_55xx` — original archive; internal IDs are TROVIS-VIEW IDs, not Modbus addresses.
- `reference/fw309_anlage21.json` — structured Golden Sample derived from the PDF.

Source tags in the matrix are `SAMSON`, `TM`, `GOLDEN`, and `TRO`. Correlation
between independent sources can raise confidence, but only direct source proof
is labeled `VERIFIED`.
