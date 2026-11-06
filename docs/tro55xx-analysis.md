# `.tro_55xx` Analysis

## Container and integrity

The source file was inspected read-only with `file`, `unzip -l`, `xxd`, Python
`zipfile`, XML parsing, and binary decompression.

- Outer type: ZIP archive with one entry, `compressedData` (79,772 bytes).
- Archive SHA-256: `8b06d260492a6281df65e77ccb6aa0e8c42d7e25553824687ed9dad0f45787f8`.
- Entry type: UTF-8 BOM XML 1.0 with CRLF and root `Trovis_View_File`.
- XML SHA-256: `32e7734fb62f023c1673fd1184d6cfef860e0acb004c3a2bda1e7c40e5613bbd`.
- Header: database `5573_1`, version `309`, file version `330`, tool
  `TROVIS-VIEW v4.100.34`, `ConsistentDataset=True`.
- The document contains 753 unique `Parameter` elements.

## Correlated parameters

| TROVIS value | XML key | Raw | Interpretation | Confidence |
|---|---:|---|---|---|
| System 2.1 | item 5 | `21` | ×0.1 → 2.1 | VERIFIED |
| Firmware 3.09 | item 2 | `309` | formatted 3.09 | VERIFIED |
| Firmware 03.09.00 | item 130 | `30900` | formatted 03.09.00 | VERIFIED |
| Model family | item 20 / header | `5573` / `5573_1` | TROVIS 5573-1 | HIGH |
| Serial 243179 | item 3 | `b5eb0003` | word/byte reorder → `0x0003b5eb` | HIGH |
| Station 247 | items 1601, 10027 | `247` | direct | VERIFIED |
| CO1 F01/F02/F03 | items 301–303 | `0/1/1` | OFF/ON/ON | VERIFIED |
| CO1 F12 | item 312 | `1` | ON | VERIFIED |
| Kp/Tn/Tv/Ty | items 335–338 | `2/130/0/25` | 0.2/130/0/25 | VERIFIED |
| Heating slope/level | items 1101/1102 | `10/0` | 1.0/0.0 | VERIFIED |
| Min/max flow | items 1103/1104 | `30/70` | °C | VERIFIED |
| Room day/night | items 1130/1131 | `195/170` | ×0.1 °C | VERIFIED |
| DHW min/max | items 1401/1402 | `23/55` | °C | VERIFIED |
| DHW day/night | items 1411/1412 | `54/40` | °C | VERIFIED |

`VERIFIED` here means the file mapping is directly consistent with the PDF; it
does not verify a Modbus address.

## Time-program encoding

Items 1801–1807 contain `000000FEFFFFFFFFFFFFFF07`. Interpreting bits
least-significant first produces 06:15–22:45 for every day. Items 2101–2107
(`0000F0030000000000000000`) produce 05:00–06:30. Items 2201–2207 are all
`FF`, matching 00:00–24:00. The PDF independently identifies these as Rk1,
domestic hot water, and circulation respectively. Because 2211–2217 also carry
all-`FF` values, the exact circulation item family is `HIGH`, not `VERIFIED`.

## Embedded binary

Item 9999 is 864 hexadecimal characters (432 bytes). After an 18-byte header,
it contains a gzip stream which expands to exactly 4,096 opaque bytes
(SHA-256 `4e87079f905148f93aa367360958b9f6d534bbc156da227b025c3ee0df3ac96c`). No stable semantic strings or schema were found. Its
purpose and all other unexplained binary fields remain `UNKNOWN`; they are not
used by the PoC.
