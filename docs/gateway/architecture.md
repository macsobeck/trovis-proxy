# Gateway Architecture

The generic data path is:

```text
TROVIS-VIEW --Modbus TCP--> downstream listener
    --> serialized proxy --> selected upstream transport --> controller
```

`trovis_gateway.proxy` is the only downstream Modbus TCP server. It parses only the MBAP
envelope, captures the downstream Unit ID, and forwards the PDU without device interpretation.
`UpstreamRouter` serializes and paces all controller requests. A transport backend applies the
active profile's Unit ID and returns only the upstream PDU. The proxy then restores the original
transaction and downstream Unit IDs.

The upstream transports are Modbus TCP, RTU-over-TCP, and Serial RTU. Switching controller or
transport requires only profile configuration; no code branch or rebuild is expected. Unknown
function codes follow the same opaque path as known codes.

The Admin HTTP service serves the status page and controller-profile editor. It does not expose
downstream listener settings for editing. Listener address/port, admin address/port, config path,
and protocol tracing are process infrastructure configured via environment or CLI.

`src/trovis_manager/` is an isolated firmware research harness and may contain model-specific
knowledge. It is not imported by `src/trovis_gateway/`.
