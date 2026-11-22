# Protocol Safety

The Modbus Proxy uses a conservative request policy:

- FC01–04 are classified as reads. They may be retried only after an explicit transport failure,
  such as a timeout, disconnect, or incomplete frame.
- FC05, FC06, FC0F, and FC10 are writes. A write may be retried only when the transport proves
  the request was not sent. A timeout after transmission is ambiguous and is never retried.
- Other function codes are opaque. They are forwarded unchanged and never automatically retried.
- Requests are serialized per Modbus Proxy and subject to the configured minimum interval. Consecutive
  requests from the active downstream TCP connection retain affinity for the configured client
  sequence idle window. Other clients wait and are then served in arrival order; no requests are
  sent upstream in parallel.
- Once the configured TCP connection age is reached, scheduled renewal occurs at the next client
  sequence boundary. A value of zero disables scheduled renewal. Transport failures still trigger
  the usual recovery and retry rules.
- Function codes, addresses, counts, and values in Modbus PDUs are forwarded unchanged. The Modbus Proxy
  does not synthesize values or apply address offsets.

Structured traces identify the downstream connection, transaction ID, and downstream and upstream
Unit IDs. The function, classification, and address/count describe the request. When available, the
response function and read byte count appear in separate fields. Raw PDU hex is emitted only when
`MODBUS_TRACE` is enabled. Access keys are never passed to tracing, metrics, health responses, or
protocol backends.

## Upstream response correlation

Every upstream response is checked against the current request before it is returned to a client.
The function code must match (or be its Modbus exception form), read byte counts must match the
requested quantity, and write acknowledgements must echo the required request fields. A mismatch
is treated as a lost stream boundary: the response is rejected and the upstream connection is
closed so that all already buffered frames are discarded. Reads may then be retried on a new
connection; a write that may already have reached the controller is never repeated.

RTU-over-TCP also checks for bytes already waiting before a request and after a complete reply.
Either condition means the stream may be out of sync. The proxy discards that connection, including
its receive buffer. The RTU response timeout covers the whole frame, including all TCP chunks.
After an error, the proxy drains unexpected input on the replacement connection and waits for a
quiet interval before sending a new request. The client request deadline also covers this step.
The RTU reply for a coil or register read carries neither its address nor a transaction ID. A single
stale reply that arrives during a request and matches its shape can therefore be indistinguishable
from a fresh reply. Route every Modbus client through the proxy so it is the sole requester on the
adapter's serial link.

An expired request or an unreachable or unconfigured upstream produces Modbus exception `0x0B`
(target device failed to respond). The original downstream transaction and Unit IDs are retained
in that reply.
