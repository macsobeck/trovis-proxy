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

The provided Compose configuration publishes the administration website on
host port `8083`. Allow access only from the trusted LAN; do not expose this
port to the Internet.

## 2. Obtain the source

For a fresh checkout:

```bash
git clone https://github.com/macsobeck/trovis-proxy.git
cd trovis-proxy
```

If the repository is already present, open a terminal in its root directory.
The directory must contain `compose.yaml`, `Dockerfile`, and `pyproject.toml`.

## 3. Configure the container identity

Create the local Compose environment file:

```bash
cp .env.example .env
```

The defaults run the container as UID and GID `1000`:

```env
GATEWAY_UID=1000
GATEWAY_GID=1000
```

The Compose configuration bind-mounts the host directory `./data` into `/data`.
Use the owner of that directory for the container identity. On Linux, determine
the values with:

```bash
id -u
id -g
```

The local `.env` is excluded from Git and the Docker build context.

## 4. Validate and build the Docker configuration

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
| Administration website | all interfaces, port `8083` | `8080` |

## 5. Start the gateway

Start it in the background:

```bash
docker compose up -d
```

Confirm that the container is running and healthy:

```bash
docker compose ps
curl http://127.0.0.1:8083/health
```

The health endpoint should return:

```json
{"status":"ok"}
```

If startup fails, inspect the logs:

```bash
docker compose logs --tail=100 gateway
```

## 6. Open the administration website

From a computer in the trusted LAN, open:

```text
http://NAS-IP:8083/
```

Replace `NAS-IP` with the IP address or trusted DNS name of the Docker host.
Restrict host firewall access to the required LAN clients.

## 7. Create the controller profile

Open **Controller connection** and select **New profile**.
Enter the settings for the connection from the gateway to the controller:

1. Enter a profile name and optional description.
2. Select `Modbus TCP`, `RTU-over-TCP`, or `Serial RTU`.
3. For a TCP transport, enter the controller or adapter host and port.
4. Enter the controller's Modbus station address. The default is `247`, but it
   must match the actual controller.
5. Optionally store the access key. It remains in pass-through mode and is not
   injected into Modbus traffic.
6. Keep **Maximum connection age** at `25 s` for the observed TROVIS controller behavior. The
   gateway then renews the TCP connection before the controller's approximately 30-second session
   boundary. Set it to `0` only when the controller supports unrestricted persistent sessions.
7. Review the remaining timeouts, request spacing, and retry values.
8. Select **Save**.
9. Select **Activate** if this is not already the active profile.

Only one profile is active at a time. Changing the active profile does not
require a rebuild or container restart.

### USR serial-to-Ethernet adapter

For reliable operation with a USR adapter, configure Socket A as follows:

- set **Work Mode** to `TCP Server`;
- set the adjacent protocol mode to `None`, not `ModbusTCP`;
- select `RTU-over-TCP` as the transport in the proxy profile.

This keeps the USR adapter transparent while the proxy performs the required
Modbus TCP-to-RTU framing.

## 8. Test the controller connection

Select **Test connection**. The test opens the configured
transport and reports the target, station, and connection time. It intentionally
sends no arbitrary Modbus register request.

A successful TCP connection proves network reachability only. It does not prove
that the controller accepts a specific Modbus function or address.

## 9. Configure TROVIS-VIEW

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

## 10. Verify operation

Open the **Status** page and check:

- the listener address and port;
- the active profile and controller target;
- connected TROVIS-VIEW clients;
- request, timeout, retry, and reconnect counters.

Follow live logs when diagnosing communication:

```bash
docker compose logs -f gateway
```

The current NAS Compose configuration enables raw Modbus PDU tracing with
`MODBUS_TRACE=1` for diagnostics. Logs can contain protocol data. Set it to `0`
after troubleshooting and recreate the container:

```bash
docker compose up -d --force-recreate
```

## 11. Persistence and backups

Profiles are stored in `./data/config.json` on the Docker host and mounted as
`/data/config.json` in the container. Ordinary restarts, rebuilds, and
`docker compose down` preserve this bind-mounted directory.

Create a backup after configuring the gateway:

```bash
docker compose exec -T gateway sh -c 'cat /data/config.json' > gateway-config-backup.json
chmod 600 gateway-config-backup.json
```

The backup contains the stored access key in clear text. Protect it accordingly.

Before the first start, create the bind-mount directory and assign it to the
configured container UID and GID:

```bash
mkdir -p data
sudo chown -R 1000:1000 data
sudo chmod 755 data
```

Replace `1000:1000` when `.env` contains different values.

Restore a backup:

```bash
docker compose stop gateway
docker compose run --rm --no-deps -T --entrypoint sh gateway \
  -c 'umask 077; cat > /data/config.json' < gateway-config-backup.json
docker compose up -d
```

## 12. Update the installation

Back up the configuration first, then update and rebuild:

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
```

The bind-mounted `./data` directory remains attached to the replacement container.

## 13. Serial RTU with Docker

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

Set `GATEWAY_GID` in `.env` to the serial device's group ID when group access is
required. Rebuild the image after changing UID or GID.

Direct USB serial access through Docker Desktop depends on host USB forwarding.
For macOS or Windows, the native installation or an RTU-over-TCP adapter is often
simpler.

## 14. Native Python installation

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

## 15. Troubleshooting

### The website does not open

Check `docker compose ps`, the gateway logs, and whether another process already
uses host port `8083`.

### TROVIS-VIEW cannot connect

Confirm that TROVIS-VIEW uses the Docker host IP, not `127.0.0.1`, and verify that
TCP port `7112` is allowed through the host firewall.

### The controller test fails

Verify the active profile, controller host and port, routing, and adapter mode.
For a USR adapter, set Socket A to `TCP Server` with protocol mode `None` and
select `RTU-over-TCP` in the proxy. The adapter must transport raw Modbus RTU
frames rather than converting them to Modbus TCP.

### Requests return gateway exception `0x0B`

The controller is not responding or no active profile is configured. Review the
status counters and gateway logs.

### Serial RTU fails

Check the device path, container device mapping, host permissions, baud rate,
data bits, parity, stop bits, and Modbus station address.
