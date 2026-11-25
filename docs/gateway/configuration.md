# Modbus Proxy Configuration

Controller profiles are stored atomically in `/data/config.json` by default. The file is created
with owner-only permissions (`0600`) and should be backed by a persistent Docker volume. Several
profiles may exist; exactly zero or one is active.

## Forwarding control

The status page can pause controller forwarding without stopping the listener or administration
interface. A request that is already active finishes safely. New requests are rejected immediately,
and requests that were waiting for the controller are rejected before transmission. Clients receive
Modbus gateway exception `0x0B` in both cases.

Paused requests are not buffered and are never executed later. This avoids stale reads and delayed
writes after a client timeout. The forwarding state is stored in `/data/config.json` and survives a
container restart. Any prerelease 1.2 buffering fields are removed automatically when the file is
loaded.

## Status counters

The status page updates automatically every five seconds. **Reset counters** starts a new
measurement period after confirmation by setting Requests, Retries, Timeouts, and Reconnects to
zero. The proxy continues serving requests, and the live client count, queue depth, and connection
state are still reported. Events recorded after the reset appear in the new counts.

## Timing presets

Under **Client scheduling**, the selector controls the client sequence window.

| Scheduling preset | Client sequence window |
|---|---:|
| Multi-client incl. TROVIS-VIEW | 0.80 s |
| Multi-client without TROVIS-VIEW | 0.20 s |
| Custom | Enter 0–10 s |

New controller profiles start with **Multi-client without TROVIS-VIEW**. Selecting **Custom**
keeps the current window as a starting point. Editing the window directly also selects
**Custom**. When a profile is opened, the selector reflects its saved window.

The seven **Advanced communication settings** belong to the controller profile, so each
controller or adapter can have its own values. Changing the scheduling preset edits only the
window. Retry limits have their own controls.

| Advanced setting | Default | Adjust when |
|---|---:|---|
| Connection timeout | 3 s | DNS, TCP connection setup, or opening a serial port needs more time. |
| Response timeout | 2 s | A complete reply takes longer, for example with a slow link or large read. |
| Total timeout | 16 s | Queueing, connection setup, pacing, and permitted retries need a different overall budget. Consider the client deadline. |
| Minimum request interval | 0.10 s | The controller or serial adapter needs a different pause after a successful response. |
| Post-connect delay | 0.25 s | The adapter needs time after connection, or RTU-over-TCP recovery needs a longer quiet interval. |
| Pre-reconnect delay | 1.00 s | The endpoint needs a different interval between a failed exchange or scheduled close and reopening. |
| Maximum TCP connection age | 25 s | The adapter has a different session lifetime. Set to 0 to disable scheduled renewal. |

### Existing configurations

Profiles saved by v1.2.1 and v1.2.2 retain their individual timing values, including old
Single-client (0.10 s), Multi-client (0.20 s), TROVIS-VIEW (0.80 s), and custom values. A
legacy file with an omitted window uses its previous default of 0.80 s. The persisted flat
`profiles[].timing` object and schema remain compatible with both versions. Reading an
existing file does not rewrite its timing values.

See [timing analysis and validation](timing-validation.md) for the comparison and its limits.

Each profile contains transport, TCP endpoint or serial parameters, upstream Modbus Unit ID,
timeouts, pacing, retry limits, and an optional access key. The API returns only a boolean saying
whether a key exists. An empty key field preserves the stored value; the explicit delete checkbox
removes it. `key_mode` is fixed to `pass-through`, so the stored key is not injected. Modbus PDUs
and addresses are forwarded unchanged. Obsolete FC01 offset settings from earlier builds are
removed automatically when the configuration is loaded.

TCP profile hosts may be IPv4 addresses, IPv6 addresses, or DNS names. The proxy passes names to the
container's system resolver and uses IP literals directly. The configured **Connection timeout**
is shared by DNS resolution and all TCP attempts, including any lookup and retry after a cached
address fails. **Test connection** shows the time spent on DNS and TCP and reports the endpoint it
reached, for example `trovis.example.test:7112` via `192.0.2.20:7112`. With `--log-level DEBUG`,
the proxy logs lookup and per-address connection timings.

For reconnects to the same controller, the proxy reuses recently resolved addresses. Starting
after 60 seconds, the next reconnect refreshes DNS in the background. The proxy uses DNS results for
at most 120 seconds and resolves again immediately if cached addresses cannot be reached.
**Test connection** performs its own lookup to show the current resolver behavior.

For a DNS name, **IP address preference** controls which address family is tried first. Existing
profiles use **System order**. **Prefer IPv4** and **Prefer IPv6** move that family to the front,
keeping the other family available. When both families are available, the proxy alternates
between them. It starts the next family after at most 300 ms, or sooner if the current attempt
fails or the remaining budget requires it. Attempts are sequential so the proxy opens only one
connection to the adapter. The same preference applies to **Test connection**.

Keep a configuration backup when reverting to an older release. Version 1.2.0 and earlier
do not recognize the new per-profile `address_preference` field.

After the proxy completes a request, the same downstream TCP connection keeps its turn for
the configured window. A follow-up request extends the sequence. Other connections are served
in arrival order once the active connection is idle or disconnects. At 0, clients take turns
after each request and the upstream exchange stays serialized. A continuously active client
with gaps shorter than the window can keep its turn until other requests reach their total
timeout. For independent polling where that occurs, a window of 0 allows request-by-request
scheduling.

The minimum request interval paces transmissions after each successful exchange. It can delay
a request even at a window of 0. With a single client, the idle window does not itself delay
forwarding, although it can affect when an aging TCP connection is renewed.

**Total timeout** starts when the proxy accepts a complete client request. The budget covers queue
time, request pacing, connection setup, recovery, and retries. A request that expires in the queue
receives Modbus exception `0x0B` and never reaches the controller. The proxy lets the current
exchange continue. If a request expires during an exchange, the proxy closes that upstream
connection while returning `0x0B` to the affected client.

TCP profiles schedule upstream connection renewal at an age of `25` seconds by default. If a
client is still sending requests within its sequence idle window, the current connection can
exceed that age. The proxy closes it and observes the configured reconnect delay before the first
request of the next sequence. This age was chosen for the approximately 30-second session
boundary observed in controller captures. Set the age to `0` to disable scheduled renewal.

After an RTU-over-TCP error, the proxy observes **Pre-reconnect delay** before opening a new
connection. It then waits for a quiet interval equal to **Post-connect delay** (at least
50 ms), discarding any incoming bytes and restarting that interval. The total timeout bounds this
recovery even if the adapter keeps sending data. Successful exchanges need no recovery wait.

Infrastructure settings are deliberately separate:

| Environment | Default | CLI |
|---|---:|---|
| `LISTEN_ADDRESS` | `0.0.0.0` | `--listen-host` |
| `LISTEN_PORT` | `7112` | `--listen-port` |
| `ADMIN_ADDRESS` | `127.0.0.1` | `--admin-host` |
| `ADMIN_PORT` | `8080` | `--admin-port` |
| `GATEWAY_CONFIG_PATH` | `/data/config.json` | `--config-path` |
| `MODBUS_TRACE` | `0` | `--modbus-trace` |

The connection test opens and closes the selected TCP transport without sending a Modbus PDU.
For Serial RTU it verifies that the configured device path exists, again without a request.
