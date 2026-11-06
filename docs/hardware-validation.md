# Read-only Hardware Validation

## Status

The validation tooling is implemented, but no real controller endpoint was
provided in this work block. Consequently, no real-hardware report exists and
the Phase-2 read-only acceptance status is **FAIL / NOT RUN**. Mock runs are
useful tests but are structurally unable to produce `PASS`.

## Identity gate

Every configuration read first reads and checks:

- model `TROVIS 5573-1`;
- firmware prefix `03.09.`;
- system code `2.1`;
- reported and targeted unit ID `247`;
- raw hardware version, where available;
- serial number and the separate HR40006 raw candidate.

An unsupported model, firmware, system, or unit aborts before any
firmware-dependent configuration address is read. HR40006 remains `UNKNOWN`:
its 16-bit raw value is collected for diagnosis but is not silently interpreted
as the six-digit Golden serial.

## Commands

Install the live backend, then select exactly one real transport:

```bash
pip install -e '.[live]'

trovisctl hardware --transport tcp --host 192.0.2.10 --unit 247 identify
trovisctl hardware --transport tcp --host 192.0.2.10 --unit 247 read-config
trovisctl hardware --transport tcp --host 192.0.2.10 --unit 247 backup backup.json
trovisctl hardware --transport tcp --host 192.0.2.10 --unit 247 validate
trovisctl hardware --transport tcp --host 192.0.2.10 --unit 247 \
  --modbus-trace endurance-read --runs 20 --pause 2
```

Serial RTU uses `--transport serial --device /dev/ttyUSB0 --baudrate 19200`.
RTU over TCP uses `--transport rtu-tcp --host HOST --port PORT`. Hardware mode
does not accept the mock transport and requires an explicit host or device; it
never guesses an endpoint.

Defaults are deliberately conservative: 2 s timeout, 100 ms inter-request
delay, two retries, 250 ms exponential-backoff base, and 250 ms connect delay.
Change one parameter at a time and compare complete reports before retaining an
optimization.

`hardware validate` performs one diagnostic read and must not be mistaken for
acceptance. Only `endurance-read` with at least 20 real reads can pass the full
gate.

## Reports

Each validation creates `hardware-validation/<UTC timestamp>/` with:

- `snapshots/run-NNN.json` and `runs.json`;
- `validation-summary.json` and `.md`;
- `consistency-report.json` and `.md`;
- `golden-comparison.json` and `.md`;
- optional `modbus-trace.json` and `.jsonl`;
- `matrix-verification-candidates.json`.

Each run records duration, logical requests, attempts, retries, timeouts,
exceptions, connection losses, reconnects, point counts, missing points,
snapshot status, and identity. Trace records contain UTC timestamp, function
code, zero-based address, count, raw and decoded responses, duration, retry
number, exception, and run context.

## Consistency and acceptance

Matrix groups distinguish `identity`, `communication`, `configuration`, and
`runtime`. Changing sensor readings are `CHANGED_EXPECTED`; changing
configuration points are `INCONSISTENT`. Missing values are `UNREADABLE`.

`PASS` requires a real transport, at least 20 requested and completed reads,
only complete snapshots, no configuration inconsistencies, no mapped Golden
differences, successful identity on every run, and a resolved serial identity.
Recovered timeouts are reported and do not alone fail the run. Matrix candidates
are never promoted automatically; a plausible matching number is insufficient
evidence.
