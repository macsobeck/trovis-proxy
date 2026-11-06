# Installation Guide

This guide installs the TROVIS Communication Gateway and connects it between
TROVIS-VIEW and a controller.

```text
TROVIS-VIEW → Modbus TCP → Gateway → selected transport → controller
```

Docker Compose is the recommended installation method. A native Python setup is
described at the end for development or direct serial-port access.

## 1. Check the prerequisites

You need:

- a Linux, macOS, or Windows host with network access to the controller;
- Docker Engine with the Compose plugin, or Docker Desktop;
- TCP port `7112` reachable from the TROVIS-VIEW computer;
- the controller host, port, Modbus station address, and transport type;
- Python 3.12 or newer only when using the native installation.

Check Docker:

```bash
docker --version
docker compose version
```

Do not expose the administration port directly to an untrusted network. The
provided Compose configuration publishes it on host loopback only.

## 2. Obtain the source

For a fresh checkout:

```bash
git clone https://github.com/macsobeck/trovis-proxy.git
cd trovis-proxy
```

If the repository is already present, open a terminal in its root directory.
The directory must contain `compose.yaml`, `Dockerfile`, and `pyproject.toml`.

## 3. Validate and build the Docker configuration

Validate the Compose file before starting anything:

```bash
docker compose config --quiet
```

Build the image:

```bash
docker compose build
```

Compose builds and tags the local image as:

```text
trovis-proxy:0.1.0
```

The `build` definition remains linked to the repository's `Dockerfile`, so the
same command recreates the versioned image after a source update.

The image includes the optional Serial RTU dependency. The default ports are:

| Purpose | Host binding | Container port |
|---|---|---:|
| TROVIS-VIEW Modbus TCP listener | all interfaces, port `7112` | `7112` |
| Administration website | `127.0.0.1:8080` | `8080` |

## 4. Start the gateway

Start it in the background:

```bash
docker compose up -d
```

Confirm that the container is running and healthy:

```bash
docker compose ps
curl http://127.0.0.1:8080/health
```

The health endpoint should return:

```json
{"status":"ok"}
```

If startup fails, inspect the logs:

```bash
docker compose logs --tail=100 gateway
```

## 5. Open the administration website

On the Docker host, open:

```text
http://127.0.0.1:8080/
```

For secure access from another computer, keep port 8080 bound to loopback and
use an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 user@gateway-host
```

Then open `http://127.0.0.1:8080/` on the local computer.

## 6. Create the controller profile

Open **Controller connection** (`Reglerverbindung`) and select **New profile**.
Enter the settings for the connection from the gateway to the controller:

1. Enter a profile name and optional description.
2. Select `Modbus TCP`, `RTU-over-TCP`, or `Serial RTU`.
3. For a TCP transport, enter the controller or adapter host and port.
4. Enter the controller's Modbus station address. The default is `247`, but it
   must match the actual controller.
5. Optionally store the access key. It remains in pass-through mode and is not
   injected into Modbus traffic.
6. Review timeouts, request spacing, and retry values.
7. Select **Save**.
8. Select **Activate** if this is not already the active profile.

Only one profile is active at a time. Changing the active profile does not
require a rebuild or container restart.

## 7. Test the controller connection

Select **Test connection** (`Verbindung testen`). The test opens the configured
transport and reports the target, station, and connection time. It intentionally
sends no arbitrary Modbus register request.

A successful TCP connection proves network reachability only. It does not prove
that the controller accepts a specific Modbus function or address.

## 8. Configure TROVIS-VIEW

Configure TROVIS-VIEW separately. Do not enter TROVIS-VIEW settings in the
gateway profile.

Use:

- **Gateway IP:** the IP address of the Docker host;
- **Gateway port:** `7112`;
- **Station address:** the value required by the TROVIS-VIEW project.

The gateway records the downstream Unit ID sent by TROVIS-VIEW. For the
controller-facing request it uses the station address configured in the active
controller profile.

Allow inbound TCP port `7112` in the host firewall only from the required
TROVIS-VIEW network or workstation.

## 9. Verify operation

Open the **Status** page and check:

- the listener address and port;
- the active profile and controller target;
- connected TROVIS-VIEW clients;
- request, timeout, retry, and reconnect counters.

Follow live logs when diagnosing communication:

```bash
docker compose logs -f gateway
```

Raw Modbus PDU tracing is disabled by default. Enable `MODBUS_TRACE=1` in
`compose.yaml` only for controlled diagnostics, then recreate the container:

```bash
docker compose up -d --force-recreate
```

## 10. Persistence and backups

Profiles are stored in `/data/config.json` inside the logical `gateway-data`
volume. With the fixed Compose project name, Docker creates it as
`trovis-proxy_gateway-data`. Ordinary restarts, rebuilds, and
`docker compose down` preserve it.

Never use this command unless you intentionally want to delete all profiles:

```text
docker compose down -v
```

Create a backup after configuring the gateway:

```bash
docker compose exec -T gateway sh -c 'cat /data/config.json' > gateway-config-backup.json
chmod 600 gateway-config-backup.json
```

The backup contains the stored access key in clear text. Protect it accordingly.

Restore a backup:

```bash
docker compose stop gateway
docker compose run --rm --no-deps -T --entrypoint sh gateway \
  -c 'umask 077; cat > /data/config.json' < gateway-config-backup.json
docker compose up -d
```

## 11. Update the installation

Back up the configuration first, then update and rebuild:

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
```

The named data volume remains attached to the replacement container.

## 12. Serial RTU with Docker

On Linux, pass the serial device into the service by adding this under
`services.gateway` in `compose.yaml`:

```yaml
devices:
  - "/dev/ttyUSB0:/dev/ttyUSB0"
```

The container user must have permission to open the device. Device ownership and
group IDs differ between Linux distributions; verify them with:

```bash
ls -l /dev/ttyUSB0
```

Direct USB serial access through Docker Desktop depends on host USB forwarding.
For macOS or Windows, the native installation or an RTU-over-TCP adapter is often
simpler.

## 13. Native Python installation

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[serial]'
mkdir -p data
trovis-gateway \
  --listen-host 0.0.0.0 \
  --listen-port 7112 \
  --admin-host 127.0.0.1 \
  --admin-port 8080 \
  --config-path "$PWD/data/config.json"
```

Keep this terminal open while testing. Stop the gateway with `Ctrl+C`. For a
permanent native installation, run the same command under a service manager and
use an absolute configuration path.

## 14. Troubleshooting

### The website does not open

Check `docker compose ps`, the gateway logs, and whether another process already
uses port `8080`.

### TROVIS-VIEW cannot connect

Confirm that TROVIS-VIEW uses the Docker host IP, not `127.0.0.1`, and verify that
TCP port `7112` is allowed through the host firewall.

### The controller test fails

Verify the active profile, controller host and port, routing, and adapter mode.
For RTU-over-TCP, ensure the adapter transports raw Modbus RTU frames rather than
converting them to Modbus TCP.

### Requests return gateway exception `0x0B`

The controller is not responding or no active profile is configured. Review the
status counters and gateway logs.

### Serial RTU fails

Check the device path, container device mapping, host permissions, baud rate,
data bits, parity, stop bits, and Modbus station address.
