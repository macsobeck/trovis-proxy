# Installation Guide

English | [Deutsch](installation.de.md)

This guide shows how to install the TROVIS Modbus Proxy and connect client applications such as
TROVIS-VIEW, Home Assistant, and Node-RED to a SAMSON TROVIS controller.

```text
Client application → Modbus TCP → Modbus Proxy → selected transport → controller
```

Docker Compose is the recommended installation method. A native Python setup is
described at the end for development or direct serial-port access.

## 1. Check the prerequisites

You need:

- a Linux, macOS, or Windows host with network access to the controller;
- Docker Engine with the Compose plugin, or Docker Desktop;
- TCP port `7112` on the Docker host reachable from the client applications;
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

## 2. Image policy

The provided `compose.yaml` uses the current prebuilt public image and stores persistent data in
the `./data` directory. It pulls `docker.io/macsobeck/trovis-proxy:latest` from Docker Hub for AMD64
or ARM64 and does not build the repository's `Dockerfile` during installation.

The `Dockerfile` is retained for project development and publishing new images, not for the
standard installation workflow.

## 3. Obtain the project files

For a fresh checkout:

```bash
git clone https://github.com/macsobeck/trovis-proxy.git
cd trovis-proxy
```

If the repository is already present, open a terminal in its root directory. The installation
uses `compose.yaml`.

## 4. Prepare persistent storage

The Compose file stores the configuration in the host directory `./data`. Create it before
starting the Modbus Proxy:

```bash
mkdir -p data
sudo chown -R 1000:1000 data
sudo chmod 755 data
```

The published images run with the fixed UID and GID `1000`. The commands above provide the
required write access on Linux and NAS systems.

## 5. Pull the image

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

The image includes the optional Serial RTU dependency. The default ports are:

| Purpose | Host binding | Container port |
|---|---|---:|
| Modbus TCP listener for client applications | all interfaces, port `7112` | `7112` |
| Administration website | all interfaces, port `8083` | `8080` |

## 6. Start the Modbus Proxy

Start the image in the background:

```bash
docker compose up -d
docker compose ps
```

Confirm that the Modbus Proxy is healthy:

```bash
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
6. Keep **Maximum connection age** at `25 s` as a starting point. After that age the proxy renews
   the connection before the next client sequence. A value of `0` disables scheduled renewal.
7. Choose **Single-client polling** for one application, **Multi-client polling** for several
   polling applications, or **TROVIS-VIEW + up to 2 clients** for TROVIS-VIEW readouts. The
   **Total timeout** of `16 s` includes time waiting in the queue. See
   [timing presets](configuration.md#timing-presets).
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

## 10. Connect client applications

Set the connection type to **Modbus TCP** in each client application. Use the Docker host's IP
address or DNS name and port `7112`. In TROVIS-VIEW, use the station address required by the project.

The proxy records the Unit ID sent by the client. For requests to the controller, it uses the
station address configured in the active controller profile.

Allow inbound TCP port `7112` in the host firewall only from the systems running your client applications.

## 11. Verify operation

Open the **Status** page and check:

- the listener address and port;
- the active profile and controller target;
- connected Modbus TCP clients;
- request, timeout, retry, and reconnect counters.

The page updates every five seconds. Select **Reset counters** and confirm to start a fresh
measurement period while the proxy is running.

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

## 12. Persistence and backups

Profiles are stored in `./data/config.json` on the Docker host and mounted as
`/data/config.json` in the container. Ordinary restarts, image updates, and
`docker compose down` preserve this bind-mounted directory.

Create a backup after configuring the Modbus Proxy.

```bash
docker compose exec -T gateway sh -c 'cat /data/config.json' > modbus-proxy-config-backup.json
chmod 600 modbus-proxy-config-backup.json
```

The backup contains the stored access key in clear text. Protect it accordingly.

Restore a backup with:

```bash
docker compose stop gateway
docker compose run --rm --no-deps -T --entrypoint sh gateway \
  -c 'umask 077; cat > /data/config.json' < modbus-proxy-config-backup.json
docker compose up -d
```

## 13. Update the installation

Back up the configuration first. Update the standard installation to the latest image with:

```bash
git pull --ff-only
docker compose pull
docker compose up -d
docker compose ps
```

The bind-mounted `./data` directory remains attached to the replacement container.

## 14. Serial RTU with Docker

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

### A Modbus TCP client cannot connect

Verify the client's Modbus TCP settings. If the application runs on a separate device, use the
Docker host's LAN address or DNS name and check that the host firewall allows TCP port `7112`.

### The controller test fails

Verify the active profile, controller host and port, routing, and adapter mode.
For a USR adapter, set Socket A to `TCP Server` with protocol mode `None` and
select `RTU-over-TCP` in the Modbus Proxy. The adapter must transport raw Modbus RTU
frames rather than converting them to Modbus TCP.

### Diagnose DNS and network reachability

**Test connection** shows DNS and TCP timings and the IP address reached. To compare results
from inside the container, replace `trovis-proxy-local` and `trovis.example.test` with your
container name and adapter hostname.

```bash
docker exec trovis-proxy-local nslookup trovis.example.test
docker exec trovis-proxy-local dig trovis.example.test A
docker exec trovis-proxy-local dig trovis.example.test AAAA
docker exec trovis-proxy-local ping -c 3 trovis.example.test
docker exec trovis-proxy-local traceroute trovis.example.test
```

For a short hostname, use `dig +search` to include the container's configured search domains.
`ping` requires permission to open an ICMP socket and an ICMP reply from the target. The
default UDP mode of `traceroute` depends on ICMP replies along the route. Use the TCP test in
the web UI to verify that the adapter port is reachable.

### Requests return Modbus exception `0x0B`

The controller is not responding or no active profile is configured. Review the
status counters and Modbus Proxy logs.

### Serial RTU fails

Check the device path, container device mapping, host permissions, baud rate,
data bits, parity, stop bits, and Modbus station address.
