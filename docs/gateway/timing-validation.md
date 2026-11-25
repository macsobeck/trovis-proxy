# Timing architecture and validation

## Decision

Use **variant B**. **Multi-client incl. TROVIS-VIEW** (0.80 s) and
**Multi-client without TROVIS-VIEW** (0.20 s) set only the client sequence window.
**Custom** keeps the current window for manual editing. The seven advanced settings remain
configurable per controller profile. Distinct controllers, adapters, or serial links can
still need different values.

Variant A would require meaningful combinations of several parameters for the same
use case. Client count alone gives no basis for changing connection delays, pacing, or
exchange timeouts. The overall timeout does depend on the workload and each client's
deadline. Its value is an independent budget, since the number of clients or their
application names cannot predict the queue length, controller response time, or retry
cost. The common advanced defaults retain the v1.2.2 values.

## Previous and new timing controls

| Parameter | v1.2.2 | New configuration | What determines the value |
|---|---|---|---|
| Client sequence window | Single-client 0.10 s, Multi-client 0.20 s, TROVIS-VIEW 0.80 s | With TROVIS-VIEW 0.80 s, without TROVIS-VIEW 0.20 s, Custom 0–10 s | Client request gaps and whether requests form a sequence. At 0, arbitrate after each request. |
| Connection timeout | 3 s in every preset | Advanced, 3 s | DNS and TCP connection budget. For Serial RTU, also limits the port open and is used as the serial write timeout. |
| Response timeout | 2 s in every preset | Advanced, 2 s | Controller processing time, transmission speed, and reply length. For TCP transports it bounds the complete reply. For Serial RTU it is the serial read timeout used by the port. |
| Total timeout | 16 s in every preset | Advanced, 16 s | End-to-end budget including queueing, pacing, connection setup, recovery, and retries. It should fit the client's own deadline. |
| Minimum request interval | 0.10 s in every preset | Advanced, 0.10 s | Controller or adapter recovery time after a successful exchange. This sets a throughput limit independently of the number of clients. |
| Post-connect delay | 0.25 s in every preset | Advanced, 0.25 s | Endpoint readiness after opening. For RTU-over-TCP recovery it is the required quiet interval, with a 50 ms floor. |
| Pre-reconnect delay | 1.00 s in every preset | Advanced, 1.00 s | Time for socket or link cleanup after a failure or a scheduled close. It consumes the total request budget. |
| Maximum TCP connection age | 25 s in every preset | Advanced, 25 s | Adapter session lifetime. Once due, renewal occurs at the next sequence boundary. Serial RTU has no age-based renewal. |

The sequence window starts when the router completes an exchange, including recovery
or failure processing. It holds the client's turn, while the minimum interval controls
when the next frame may be sent. When a competing client waits for its turn, part or
all of the minimum interval may already elapse during that wait. If the turn is granted
earlier, the remaining interval still applies. A candidate sequence window should
therefore reflect client pauses measured **from the reply to the next request**.

An expired TCP connection can remain open while the same client extends its sequence.
A smaller window can make a gap become a sequence boundary and bring renewal forward.
A larger window can avoid a planned reconnect during a readout, but a controller or
adapter may close the session independently. On a connection failure, the response
timeout, reconnect delay, and recovery rules still apply within the total budget.
A request that expires while queued returns Modbus exception `0x0B` without reaching
the controller. RTU response checks and the write replay policy follow the existing
[protocol safety rules](protocol-safety.md).

## Reproducible simulation

Run from the repository root with the development dependencies installed.

```bash
PYTHONPATH=src python -m pytest -q -s tests/gateway/test_proxy.py \
  -k 'scheduling_windows or single_client_pacing or continuous_polling_burst or queue_timeout or total_timeout_reconnects or multiple_clients_keep_values or scheduled_rtu_renewal or rtu_write_with_extra_reply'
```

The comparison uses a local simulated RTU-over-TCP adapter and two Modbus TCP clients.
Client A sends A1, then A2 after the indicated pause. Client B sends B1 just after A1
completes. This isolates scheduling by setting request pacing and scheduled renewal to
zero for the comparison. The controller delay is held constant within each case.
Each row represents one three-request batch. Mean and max are from the three client
round trips. B wait measures submission to receipt at the simulated controller, and
the batch rate includes the scripted pause. These timings illustrate the ordering
trade-off on loopback and vary with the host scheduler.

| Window | A pause | Reply delay | Order | Mean RTT | Max RTT | B wait | Batch rate |
|---:|---:|---:|---|---:|---:|---:|---:|
| 0 s | 150 ms | 10 ms | A1, B1, A2 | 19 ms | 26 ms | 1 ms | 15.3 req/s |
| 0.10 s | 150 ms | 10 ms | A1, B1, A2 | 74 ms | 121 ms | 105 ms | 11.8 req/s |
| 0.20 s | 150 ms | 10 ms | A1, A2, B1 | 141 ms | 388 ms | 373 ms | 7.4 req/s |
| 0.20 s | 400 ms | 10 ms | A1, B1, A2 | 89 ms | 218 ms | 204 ms | 6.6 req/s |
| 0.80 s | 400 ms | 10 ms | A1, A2, B1 | 425 ms | 1,240 ms | 1,224 ms | 2.4 req/s |
| 0.80 s | 670 ms | 10 ms | A1, A2, B1 | 515 ms | 1,514 ms | 1,493 ms | 2.0 req/s |
| 0.20 s | 150 ms | 80 ms | A1, A2, B1 | 237 ms | 531 ms | 446 ms | 4.8 req/s |

Every batch returned the expected register values and transaction IDs without timeouts
or reconnects. At a 150 ms gap, 0.10 s serves a waiting poll sooner and 0.20 s preserves
the sequence. The longer TROVIS-VIEW window preserves the tested 400 ms and 670 ms
gaps at the cost of a longer wait for another client.

With one polling client, a 100 ms minimum interval, and an unexpired connection, the
measured mean/max RTTs were 55/104 ms, 55/105 ms, and 57/107 ms for windows of 0.10 s,
0.20 s, and 0.80 s. The test asserts that upstream pacing still applies. It then ages
the TCP connection in the test with a 150 ms client pause. The connection renews before
the next request with a 0.10 s window and stays open with the other two windows. This
demonstrates a renewal difference, with no single-client throughput gain established.

A client making successive reads 30 ms apart retained its turn at a 0.20 s window.
A waiting client received `0x0B` when its test budget of 0.45 s expired, without a
reconnect or a request reaching the controller. It completed a fresh read after the
busy client disconnected. The queue deadline bounds a client's wait for a result,
while a continuous burst can still prevent that client from getting a turn. A window
of zero is an option for independent polling with this pattern.

The regression suite also exercises planned renewal between sequences, late and
mismatched RTU frames, read retry following reconnect, queue timeout, and protection
against repeated writes after an uncertain outcome.

## Upgrade and hardware validation

The JSON schema and `profiles[].timing` field names remain compatible with v1.2.1 and
v1.2.2. Each controller profile keeps its exact saved values, including zero, the
previous 0.10 s window, and fractional custom values. On opening a profile, the editor derives
its label from the saved window. A v1.2.1 Fast or Reliable profile therefore retains every
advanced setting regardless of the label shown. If a legacy file omitted the window,
the proxy uses the old 0.80 s default. New profiles created in the UI or API start
with 0.20 s, and a partial timing update preserves other existing values.

Loopback establishes scheduling and protocol behavior under the modeled conditions.
On hardware, compare the saved configuration and both presets with one polling client,
multiple polling clients, and at least two TROVIS-VIEW readouts while polling continues.
Record client response times and retries, timeouts, and reconnects over several adapter
session lifetimes, particularly during sustained bursts. Verify the USR adapter's actual
session limits, post-connect silence, and behavior under temporary loss of communication.
The known second-read behavior reproduced through the direct adapter connection remains
a separate hardware and application check.
