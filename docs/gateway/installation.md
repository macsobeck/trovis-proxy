# Installation Guide

This guide installs the TROVIS Modbus Proxy and connects it between
TROVIS-VIEW and a controller.

```text
TROVIS-VIEW → Modbus TCP → Modbus Proxy → selected transport → controller
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

## 2. Choose an image policy

Both Compose files use prebuilt public images and the same persistent `./data` directory. Neither
file builds the repository's `Dockerfile` during installation.

| Compose file | Choose it when | Image policy |
|---|---|---|
| **`compose.yaml`** (recommended) | You want the current release and regular image updates. | Pulls `docker.io/macsobeck/trovis-proxy:latest` from Docker Hub for AMD64 or ARM64. |
| **`.compose.v1.1.0.yaml`** | You need a reproducible rollback deployment on release 1.1.0. | Pulls the pinned Docker Hub image `docker.io/macsobeck/trovis-proxy:1.1.0`. |

Use `compose.yaml` for normal NAS and Linux installations. The `Dockerfile` is retained for project
development and publishing new images, not for the standard installation workflow.

## 3. Obtain the project files

For a fresh checkout:

```bash
git clone https://github.com/macsobeck/trovis-proxy.git
cd trovis-proxy
```

If the repository is already present, open a terminal in its root directory. A standard
installation requires `compose.yaml`; a pinned 1.1.0 rollback uses `.compose.v1.1.0.yaml`.

## 4. Prepare persistent storage

Both Compose files store the configuration in the host directory `./data`. Create it before
starting the Modbus Proxy:

```bash
mkdir -p data
sudo chown -R 1000:1000 data
sudo chmod 755 data
```

The published images run with the fixed UID and GID `1000`. The commands above provide the
required write access on Linux and NAS systems.

## 5. Pull the selected image

### Latest image with `compose.yaml` (recommended)

Validate the standard Compose file and pull the latest public multi-platform image. No registry
login is required; Docker automatically selects Linux AMD64 or ARM64.

```bash
docker compose config --quiet
docker compose pull
```

The image reference is:

```text
docker.io/macsobeck/trovis-proxy:latest
```

### Pinned rollback release 1.1.0 with `.compose.v1.1.0.yaml`

Use the pinned Compose file when the installation must remain reproducible:

```bash
docker compose -f .compose.v1.1.0.yaml config --quiet
docker compose -f .compose.v1.1.0.yaml pull
```

The pinned image reference is:

```text
docker.io/macsobeck/trovis-proxy:1.1.0
```

The image includes the optional Serial RTU dependency. The default ports are:

| Purpose | Host binding | Container port |
|---|---|---:|
| TROVIS-VIEW Modbus TCP listener | all interfaces, port `7112` | `7112` |
| Administration website | all interfaces, port `8083` | `8080` |

## 6. Start the Modbus Proxy

Start the selected image in the background.

For the **latest image**:

```bash
docker compose up -d
docker compose ps
```

For the **pinned 1.1.0 image**:

```bash
docker compose -f .compose.v1.1.0.yaml up -d
docker compose -f .compose.v1.1.0.yaml ps
```

Confirm that the Modbus Proxy is healthy; this check is identical for both image policies:

```bash
curl http://127.0.0.1:8083/health
```

The health endpoint should return:

```json
{"status":"ok"}
```

If startup fails, inspect the logs with the command for the selected variant:

```bash
# Latest image
docker compose logs --tail=100 gateway

# Pinned 1.1.0 image
docker compose -f .compose.v1.1.0.yaml logs --tail=100 gateway
```

## 7. Open the administration website

From a computer in the trusted LAN, open:

```text
http://NAS-IP:8083/
```

Replace `NAS-IP` with the IP address or trusted DNS name of the Docker host.
Restrict host firewall access to the required LAN clients.

## 8. Create the controller profile

Open **Controller connection** and select **New profile**.
Enter the settings for the connection from the Modbus Proxy to the controller:

1. Enter a profile name and optional description.
2. Select `Modbus TCP`, `RTU-over-TCP`, or `Serial RTU`.
3. For a TCP transport, enter the controller or adapter host and port.
4. Enter the controller's Modbus station address. The default is `247`, but it
   must match the actual controller.
5. Optionally store the access key. It remains in pass-through mode and is not
   injected into Modbus traffic.
6. Keep **Maximum connection age** at `25 s` for the observed TROVIS controller behavior. The
   Modbus Proxy then renews the TCP connection before the controller's approximately 30-second session
   boundary. Set it to `0` only when the controller supports unrestricted persistent sessions.
7. Keep **Client sequence idle window** at `0.25 s` when more than one application accesses the
   Modbus Proxy. This prevents Node-RED requests from being inserted into a TROVIS-VIEW or TROVIS 55 Pro
   polling sequence. Increase it slightly only if a client pauses longer between requests; `0`
   disables the protection.
8. Review the remaining timeouts, request spacing, and retry values.
9. Select **Save**.
10. Select **Activate** if this is not already the active profile.

Only one profile is active at a time. Changing the active profile does not
require a rebuild or container restart.

### USR serial-to-Ethernet adapter

For reliable operation with a USR adapter, configure Socket A as follows:

- set **Work Mode** to `TCP Server`;
- set the adjacent protocol mode to `None`, not `ModbusTCP`;
- select `RTU-over-TCP` as the transport in the Modbus Proxy profile.

This keeps the USR adapter transparent while the Modbus Proxy performs the required
Modbus TCP-to-RTU framing.

## 9. Test the controller connection

Select **Test connection**. The test opens the configured
transport and reports the target, station, and connection time. It intentionally
sends no arbitrary Modbus register request.

A successful TCP connection proves network reachability only. It does not prove
that the controller accepts a specific Modbus function or address.

## 10. Configure TROVIS-VIEW

Configure TROVIS-VIEW separately. Do not enter TROVIS-VIEW settings in the
Modbus Proxy profile.

Use:

- **Modbus Proxy IP:** the IP address of the Docker host;
- **Modbus Proxy port:** `7112`;
- **Station address:** the value required by the TROVIS-VIEW project.

The Modbus Proxy records the downstream Unit ID sent by TROVIS-VIEW. For the
controller-facing request it uses the station address configured in the active
controller profile.

Allow inbound TCP port `7112` in the host firewall only from the required
TROVIS-VIEW network or workstation.

## 11. Verify operation

Open the **Status** page and check:

- the listener address and port;
- the active profile and controller target;
- connected TROVIS-VIEW clients;
- request, timeout, retry, and reconnect counters.

Follow live logs when diagnosing communication:

```bash
# Latest image
docker compose logs -f gateway

# Pinned 1.1.0 image
docker compose -f .compose.v1.1.0.yaml logs -f gateway
```

The current NAS Compose configuration enables raw Modbus PDU tracing with
`MODBUS_TRACE=1` for diagnostics. Logs can contain protocol data. Set it to `0`
after troubleshooting and recreate the container:

```bash
# Latest image
docker compose up -d --force-recreate

# Pinned 1.1.0 image
docker compose -f .compose.v1.1.0.yaml up -d --force-recreate
```

## 12. Persistence and backups

Profiles are stored in `./data/config.json` on the Docker host and mounted as
`/data/config.json` in the container. Ordinary restarts, image updates, and
`docker compose down` preserve this bind-mounted directory.

Create a backup after configuring the Modbus Proxy.

For the **latest image**:

```bash
docker compose exec -T gateway sh -c 'cat /data/config.json' > modbus-proxy-config-backup.json
chmod 600 modbus-proxy-config-backup.json
```

For the **pinned 1.1.0 image**:

```bash
docker compose -f .compose.v1.1.0.yaml exec -T gateway \
  sh -c 'cat /data/config.json' > modbus-proxy-config-backup.json
chmod 600 modbus-proxy-config-backup.json
```

The backup contains the stored access key in clear text. Protect it accordingly.

Restore a backup with the commands for the selected image.

For the **latest image**:

```bash
docker compose stop gateway
docker compose run --rm --no-deps -T --entrypoint sh gateway \
  -c 'umask 077; cat > /data/config.json' < modbus-proxy-config-backup.json
docker compose up -d
```

For the **pinned 1.1.0 image**:

```bash
docker compose -f .compose.v1.1.0.yaml stop gateway
docker compose -f .compose.v1.1.0.yaml run --rm --no-deps -T --entrypoint sh gateway \
  -c 'umask 077; cat > /data/config.json' < modbus-proxy-config-backup.json
docker compose -f .compose.v1.1.0.yaml up -d
```

## 13. Update the installation

Back up the configuration first. Update the standard installation to the latest image with:

```bash
git pull --ff-only
docker compose pull
docker compose up -d
docker compose ps
```

For the pinned 1.1.0 installation, update only the project files while retaining the pinned image:

```bash
git pull --ff-only
docker compose -f .compose.v1.1.0.yaml pull
docker compose -f .compose.v1.1.0.yaml up -d
docker compose -f .compose.v1.1.0.yaml ps
```

The bind-mounted `./data` directory remains attached to the replacement container.

## 14. Serial RTU with Docker

On Linux, pass the serial device into the service by adding this under
`services.gateway` in the Compose file selected for the installation:

```yaml
devices:
  - "/dev/ttyUSB0:/dev/ttyUSB0"
```

The container user must have permission to open the device. Device ownership and
group IDs differ between Linux distributions; verify them with:

```bash
ls -l /dev/ttyUSB0
```

The published image has the fixed group ID `1000`. If the serial device requires a different group
ID, create a custom development image from the `Dockerfile`; this is outside the standard
installation workflow.

Direct USB serial access through Docker Desktop depends on host USB forwarding.
For macOS or Windows, the native installation or an RTU-over-TCP adapter is often
simpler.

## 15. Native Python installation

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

Keep this terminal open while testing. Stop the Modbus Proxy with `Ctrl+C`. For a
permanent native installation, run the same command under a service manager and
use an absolute configuration path.

## 16. Troubleshooting

### The website does not open

Check the container status and Modbus Proxy logs with the Compose command for the selected image, and
verify that no other process uses host port `8083`.

### TROVIS-VIEW cannot connect

Confirm that TROVIS-VIEW uses the Docker host IP, not `127.0.0.1`, and verify that
TCP port `7112` is allowed through the host firewall.

### The controller test fails

Verify the active profile, controller host and port, routing, and adapter mode.
For a USR adapter, set Socket A to `TCP Server` with protocol mode `None` and
select `RTU-over-TCP` in the Modbus Proxy. The adapter must transport raw Modbus RTU
frames rather than converting them to Modbus TCP.

### Requests return Modbus exception `0x0B`

The controller is not responding or no active profile is configured. Review the
status counters and Modbus Proxy logs.

### Serial RTU fails

Check the device path, container device mapping, host permissions, baud rate,
data bits, parity, stop bits, and Modbus station address.
