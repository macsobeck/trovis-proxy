# Architecture

> This document describes the device-specific, read-only `trovis_manager`
> research harness. The product Modbus Proxy is a separate generic component; see
> [Modbus Proxy Architecture](gateway/architecture.md).

## Layers

```text
trovisctl
   │
HardwareValidator ── identity gate / endurance / Golden & consistency reports
   │
ConfigurationService ── RegisterCatalog / Pydantic snapshot models
   │
ConnectionManager (lock, timeout, pacing, retry, reconnect)
   │
Transport protocol
   ├── MockTransport (default and fully tested)
   └── LiveTransport (Modbus TCP, serial RTU, or RTU over TCP)
```

The CLI only coordinates services; it contains no Modbus calls. The transport
contract intentionally exposes `connect`, `disconnect`, `read_holding_registers`,
and `read_coils`—no write method.

Hardware mode cannot select the mock backend. It identifies model, firmware,
system, and both reported/target unit IDs before a configuration read. A failed
gate aborts without probing firmware-specific configuration ranges.

## Address and read planning

Matrix addresses are zero-based PDU addresses. The adjacent SAMSON reference
(for example HR41001) remains visible to prevent off-by-one errors. A grouped
read may cross neither address spaces nor gaps. Blocks are capped at 50 words,
matching the conservative limit used by the inspected device library.

If a block fails, the service retries its members separately. Successful points
are preserved and errors become a `partial` snapshot. This prioritizes a useful,
auditable backup over all-or-nothing behavior.

## Lifecycle and safety

`ConnectionManager` owns a single asynchronous lock. It enforces inter-request
delay, per-operation timeout, finite retry count, exponential backoff, reconnect,
and bounded disconnect. Cancellation is re-raised immediately. Atomic snapshot
storage writes a temporary file, calls `fsync`, then replaces the destination.

Per-request metrics record requests, attempts, retries, timeout/exception/loss
classes, and reconnects. Optional traces add function code, address, count, raw
response, decoded values, duration, retry, and exception. Reports distinguish
configuration values from runtime sensor values, so changing temperatures do
not create false configuration inconsistencies.

The mock remains the only transport certified by automated tests. A mock report
is always `FAIL` for real-hardware acceptance. Write/restore remains a separate,
currently blocked layer; no write surface exists in this architecture.
