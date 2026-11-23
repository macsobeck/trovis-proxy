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

## Timing presets

The controller editor provides four choices. Selecting a preset fills the timing fields but does
not change retry settings. Editing any timing field selects **Custom** automatically.

| Preset | Connect | Response | Total | Minimum interval | Client idle | Settle | Reconnect | Max age |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fast | 2 s | 1 s | 5 s | 0.05 s | 0.10 s | 0.10 s | 0.50 s | 25 s |
| Standard | 3 s | 2 s | 16 s | 0.10 s | 0.80 s | 0.25 s | 1.00 s | 25 s |
| Reliable | 5 s | 4 s | 20 s | 0.20 s | 1.00 s | 0.50 s | 2.00 s | 25 s |

New profiles start with Standard. To apply the current Standard values to an existing profile,
select **Standard (recommended)** and save.

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

The **Client sequence idle window** defaults to `0.8` seconds. After a request completes, the same
downstream TCP connection keeps controller affinity for this long. Consecutive requests from
the same client, such as TROVIS-VIEW, Home Assistant, Node-RED, or TROVIS 55 Pro, stay together
during this window. Waiting clients are served in arrival order once the active client is idle. Set the value to `0` only to restore request-by-request arbitration. Clients must
allow enough response time for a polling sequence already in progress.

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

After an RTU-over-TCP error, the proxy observes **Reconnect delay** before opening a new
connection. It then waits for a quiet interval equal to **Connection settle delay** (at least
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
