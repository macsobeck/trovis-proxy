# Protocol Safety

The gateway uses a conservative request policy:

- FC01–04 are classified as reads. They may be retried only after an explicit transport failure,
  such as a timeout, disconnect, or incomplete frame.
- FC05, FC06, FC0F, and FC10 are writes. A write may be retried only when the transport proves
  the request was not sent. A timeout after transmission is ambiguous and is never retried.
- Other function codes are opaque. They are forwarded unchanged and never automatically retried.
- Requests are serialized per gateway and subject to the configured minimum interval.

Normal structured traces contain direction, transaction ID, downstream and upstream Unit IDs,
function code, classification, address/count when recognizable, duration, and retry number. Raw
PDU hex is emitted only when `MODBUS_TRACE` is enabled. Access keys are never passed to tracing,
metrics, health responses, or protocol backends.

An unreachable or unconfigured upstream produces Modbus exception `0x0B` (gateway target device
failed to respond). The original downstream transaction and Unit IDs are retained in that reply.
