# Modbus Proxy Configuration

Controller profiles are stored atomically in `/data/config.json` by default. The file is created
with owner-only permissions (`0600`) and should be backed by a persistent Docker volume. Several
profiles may exist; exactly zero or one is active.

## Forwarding control

The status page can pause controller forwarding without stopping the listener or administration
interface. **Without buffering** returns Modbus exception `0x0B` to every new request while paused.
**Buffer all requests** holds reads, writes, and unclassified/vendor-specific functions and passes
them through the existing client arbitration after the proxy is resumed. No buffered request is
forwarded while the proxy remains paused.

Buffer retention is independent of the normal request timeout. It accepts `1`–`3600` seconds and
defaults to `300` seconds. When that time expires, the waiting request receives `0x0B` and is discarded;
it is not sent to the controller later. The forwarding state, pause policy, and retention value are
stored in `/data/config.json` and survive a container restart.

Buffered writes execute after resuming even if the originating client has already timed out or
disconnected. Use the shortest practical retention time and choose **Without buffering** whenever
delayed writes would be unsafe.

## Timing presets

The controller editor provides four choices. Selecting a preset fills the timing fields but does
not change retry settings. Editing any timing field selects **Custom** automatically.

| Preset | Connect | Response | Total | Minimum interval | Client idle | Settle | Reconnect | Max age |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fast | 2 s | 1 s | 5 s | 0.05 s | 0.10 s | 0.10 s | 0.50 s | 25 s |
| Standard | 3 s | 2 s | 8 s | 0.10 s | 0.25 s | 0.25 s | 1.00 s | 25 s |
| Reliable | 5 s | 4 s | 20 s | 0.20 s | 1.00 s | 0.50 s | 2.00 s | 25 s |

Each profile contains transport, TCP endpoint or serial parameters, upstream Modbus Unit ID,
timeouts, pacing, retry limits, and an optional access key. The API returns only a boolean saying
whether a key exists. An empty key field preserves the stored value; the explicit delete checkbox
removes it. `key_mode` is fixed to `pass-through`, so the stored key is not injected. Modbus PDUs
and addresses are forwarded unchanged. Obsolete FC01 offset settings from earlier builds are
removed automatically when the configuration is loaded.

The **Client sequence idle window** defaults to `0.25` seconds. After a request completes, the same
downstream TCP connection keeps controller affinity for this long. Consecutive requests from
TROVIS-VIEW, TROVIS 55 Pro, or Node-RED therefore stay together instead of being interleaved with
another client's polling sequence. Waiting clients are served in arrival order once the active
client is idle. Set the value to `0` only to restore request-by-request arbitration. Clients must
allow enough response time for a polling sequence already in progress.

TCP profiles also limit a persistent upstream connection to `25` seconds by default. Before the
next request would use an older connection, the Modbus Proxy closes it, observes the configured
reconnect delay, and opens a fresh connection. This avoids the approximately 30-second session
boundary observed in controller captures. The renewal happens before a request is sent, so it does
not repeat an ambiguous write. Set the maximum connection age to `0` to disable this behavior.

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
