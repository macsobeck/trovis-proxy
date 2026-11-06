# TROVIS Communication Gateway

This repository contains a generic, locally operated communication gateway:

```text
TROVIS-VIEW → Modbus TCP → Gateway → Modbus TCP / RTU-over-TCP / Serial RTU → controller
```

The proxy forwards Modbus PDUs without controller- or firmware-specific branches. The
TROVIS 5573-1 FW 3.09 code in `src/trovis_manager/` remains a separate, read-only
integration and research harness; it is not part of the proxy core.

## Run the gateway

Python 3.12 or newer is required.

```bash
python -m pip install -e '.[dev,serial]'
trovis-gateway --listen-host 0.0.0.0 --listen-port 7112 \
  --admin-host 127.0.0.1 --admin-port 8080 \
  --config-path ./data/config.json
```

Open `http://127.0.0.1:8080`, create a controller profile, test its transport connection,
and activate it. The connection test opens only the configured transport; it sends no
invented Modbus register request. The listener address and port are infrastructure settings
provided by environment variables or CLI arguments—not controller-profile fields.

For Docker:

```bash
docker compose up --build
```

Compose builds the explicitly tagged local image
`trovis-proxy:0.1.0` from the repository's `Dockerfile`.

Profile data persists at `/data/config.json` with mode `0600`. A stored access key is masked
in the API and UI and is not logged, exposed as a metric, or injected into protocol traffic.

## Safety model

- Downstream Unit IDs are recorded and restored in responses; the active profile's Unit ID
  is used upstream.
- FC01–04 reads may retry after a clear transport failure.
- FC05/06/0F/10 writes never retry after an ambiguous result.
- Unknown and vendor-specific function codes are forwarded opaquely and are traceable.
- All requests to a controller are serialized and paced.

See [gateway architecture](docs/gateway/architecture.md),
[configuration](docs/gateway/configuration.md), and
[protocol safety](docs/gateway/protocol-safety.md). For a complete deployment,
follow the [step-by-step installation guide](docs/gateway/installation.md).

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
