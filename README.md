# TROVIS Proxy Gateway for TROVIS-VIEW and SAMSON Controllers

The **TROVIS Proxy Gateway** is a self-hosted Modbus proxy for reliable communication between
**SAMSON TROVIS-VIEW** and TROVIS heating controllers, including the **SAMSON TROVIS 5573-1xxx**
series. It provides a stable Modbus TCP endpoint for TROVIS-VIEW and connects to the controller
through Modbus TCP, RTU-over-TCP, or Serial RTU.

```text
TROVIS-VIEW → Modbus TCP → TROVIS Proxy Gateway → Modbus TCP / RTU-over-TCP / Serial RTU → controller
```

The proxy forwards Modbus PDUs unchanged and has no controller- or firmware-specific address
translation. The TROVIS 5573-1 FW 3.09 code in `src/trovis_manager/` remains a separate, read-only
integration and research harness; it is not part of the proxy core.

## Key features

- Reliable TROVIS-VIEW access through a stable Modbus TCP listener on port `7112`.
- Controller connections via Modbus TCP, transparent RTU-over-TCP, or Serial RTU.
- Docker Compose deployment for Linux servers and NAS systems such as Synology.
- Persistent controller profiles with a responsive browser-based administration interface.
- Multi-client sequence arbitration, safe read retries, protected writes, pacing, and proactive
  reconnects.
- Transparent operation with USR serial-to-Ethernet adapters in protocol mode `None`.
- Controller-neutral proxy core without hard-coded register maps or synthetic values.

## Interface examples

### Gateway status

![TROVIS Proxy Gateway status dashboard for TROVIS-VIEW and a SAMSON controller](docs/images/gateway-status.png)

*Status overview for the TROVIS-VIEW listener and the active upstream controller connection.*

### Controller connection

![TROVIS Proxy Gateway RTU-over-TCP controller profile](docs/images/controller-connection.png)

*Controller profile using RTU-over-TCP with its target, Modbus unit ID, and access settings.*

*Private network addresses are redacted in both interface examples.*

## Why this proxy gateway

I use TROVIS-VIEW to manage the configuration of my SAMSON TROVIS 5573-1xxx heating controller.
However, using the USR adapter's `ModbusTCP` mode did not provide a reliable connection. It caused
unstable communication causing failed reads and writes. Similar problems may also occur with other
serial-to-Ethernet adapters that perform their own Modbus TCP-to-RTU conversion.

The reliable setup is to configure the USR adapter as a `TCP Server` with its protocol mode set to
`None`, and then select `RTU-over-TCP` in the proxy controller profile. This keeps the adapter
transparent and lets the proxy handle the Modbus TCP-to-RTU framing.

This interoperability problem was the original motivation for developing the TROVIS Proxy Gateway.
The project has since evolved into a more general communication layer with several additional
strengths:

- **Coordinated multi-client access:** TROVIS-VIEW, Node-RED, TROVIS 55 Pro, and other Modbus TCP
  clients can access the same controller through one gateway. Client request sequences are queued
  and kept together to prevent competing applications from causing failed controller reads.
- **Transparent protocol handling:** Modbus function codes, addresses, and values are forwarded
  unchanged. The gateway does not depend on a controller-specific register map or synthetic address
  translation.
- **Flexible controller connections:** The upstream connection can use Modbus TCP, transparent
  RTU-over-TCP, or Serial RTU.
- **Reliable connection management:** Configurable pacing, timeouts, safe read retries, and
  proactive reconnection help stabilize communication with controllers and Ethernet adapters.
- **Protected write operations:** Writes are never repeated after an ambiguous result, reducing
  the risk of unintended configuration changes.
- **Simple self-hosted operation:** Docker Compose deployment, persistent configuration, and a
  browser-based administration interface make the gateway suitable for NAS systems and other
  always-on Linux hosts.
- **Operational visibility:** The status interface shows connected clients, queued requests,
  retries, timeouts, reconnects, and the active controller connection.

![USR adapter configured for transparent RTU-over-TCP operation](docs/images/usr-adapter-settings.png)

*USR adapter example: Socket A uses `TCP Server`, protocol mode `None`, and local port `7112`.*

## Quick start with Docker or Python

### Docker Compose (recommended)

```bash
cp .env.example .env
mkdir -p data
docker compose up -d --build
```

Open `http://localhost:8083/`. Compose builds the explicitly tagged local image
`trovis-proxy:1.1` and publishes the TROVIS-VIEW listener on port `7112`. The container defaults
to UID/GID `1000:1000`; both values can be changed in `.env` for NAS bind mounts.

### Native Python

Python 3.12 or newer is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,serial]'
mkdir -p data
trovis-gateway --listen-host 0.0.0.0 --listen-port 7112 \
  --admin-host 127.0.0.1 --admin-port 8080 \
  --config-path ./data/config.json
```

Open `http://127.0.0.1:8080/` for a native installation.

Create a controller profile, test its transport connection, and activate it. The connection test
opens only the configured transport; it sends no invented Modbus register request. Listener
address and port are infrastructure settings supplied by environment variables or CLI arguments,
not controller-profile fields.

Profile data persists in the host directory `./data` and appears as `/data/config.json` in the
Docker container with mode `0600`. A stored access key is masked in the API and UI and is not
logged, exposed as a metric, or injected into protocol traffic.

## Installation guide

Follow the [step-by-step installation guide](docs/gateway/installation.md) for:

- Docker and Docker Compose prerequisites;
- Synology NAS deployment, bind mounts, UID/GID ownership, and persistent storage;
- controller profiles for Modbus TCP, RTU-over-TCP, and Serial RTU;
- USR serial-to-Ethernet adapter settings;
- TROVIS-VIEW network configuration;
- upgrades, backups, diagnostics, and troubleshooting.

## Safety model

- Downstream Unit IDs are recorded and restored in responses; the active profile's Unit ID
  is used upstream.
- FC01–04 reads may retry after a clear transport failure.
- FC05/06/0F/10 writes never retry after an ambiguous result.
- Unknown and vendor-specific function codes are forwarded opaquely and are traceable.
- All Modbus PDUs, including FC01 addresses, are forwarded unchanged.
- TCP connections are renewed after 25 seconds by default, before the observed 30-second controller
  session boundary; renewal occurs before a request and never retries an ambiguous write.
- All requests to a controller are serialized and paced. Consecutive requests from one connected
  client retain short-lived affinity so another client cannot interleave a polling sequence.

See [gateway architecture](docs/gateway/architecture.md),
[configuration](docs/gateway/configuration.md), and
[protocol safety](docs/gateway/protocol-safety.md).

## Frequently asked questions

### Does this gateway replace TROVIS-VIEW?

No. TROVIS-VIEW remains the configuration application. The proxy gateway provides a reliable
network path between TROVIS-VIEW and the heating controller.

### Which TROVIS controllers are supported?

The proxy core is controller-neutral and forwards Modbus PDUs transparently. The documented
deployment has been validated with a SAMSON TROVIS 5573-1xxx controller. Other controllers can be
used when they expose a compatible Modbus TCP, RTU-over-TCP, or Serial RTU interface.

### Can the TROVIS Proxy Gateway run on a Synology NAS?

Yes. The Docker Compose setup supports NAS deployment, UID/GID mapping, automatic restarts, and a
persistent bind-mounted `./data` directory for controller profiles.

### Which mode should a USR Ethernet adapter use?

Use `TCP Server` with protocol mode `None`, then select `RTU-over-TCP` in the proxy profile. Do not
enable the adapter's `ModbusTCP` conversion mode for TROVIS-VIEW communication.

## Development assistance

This repository was developed and is maintained by macsobeck with assistance from OpenAI Codex
for code analysis, implementation, testing, documentation, and release preparation. All changes
are reviewed and published by the repository maintainer.

## Development

```bash
pytest
ruff check .
git diff --check
```

The default suite uses only local fake servers and never requires real hardware. The legacy
research CLI remains available as `trovisctl`; its hardware workflow stays read-only. See
[hardware validation](docs/hardware-validation.md) before connecting it to a controller.

## Repository layout

- `src/trovis_gateway/`: generic proxy, transports, configuration, API, and admin UI.
- `src/trovis_manager/`: device-specific read-only integration harness.
- `tests/gateway/`, `tests/unit/`, `tests/integration/`: automated coverage.
- `reference/`: immutable source artifacts and derived FW 3.09 research data.
- `docs/`: architecture, safety evidence, and research findings.
