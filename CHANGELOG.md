# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
semantic versioning.

## [Unreleased]

## [1.2.3] - 2026-11-25

### Added

- The administration interface is available in English and German. English is the default,
  and the language selector remembers the choice in the browser.

### Changed

- The scheduling selector offers **Multi-client incl. TROVIS-VIEW** (0.80 s),
  **Multi-client without TROVIS-VIEW** (0.20 s), and **Custom** for a manually entered
  client sequence window. Edit the controller and adapter timing under **Advanced communication
  settings**.
- New controller profiles start with 0.20 s. Existing configurations retain all stored timing
  values and use 0.80 s for an omitted sequence window.

## [1.2.2] - 2026-11-24

### Added

- **Reset counters** clears request, retry, timeout, and reconnect counts while the proxy
  continues serving Modbus clients. The live client count, queue depth, and connection state
  remain available.

### Changed

- The timing editor offers **Single-client polling**, **Multi-client polling**,
  **TROVIS-VIEW + up to 2 clients**, and **Custom**. The multi-client preset uses a
  0.2-second sequence idle window so waiting clients get their turn sooner.
- The TROVIS-VIEW preset uses the former Standard timing values, including the 0.8-second
  sequence idle window. Existing profiles retain their saved values.
- Status updates automatically and refreshes immediately after a counter reset.

## [1.2.1] - 2026-11-22

### Added

- TCP controller profiles can prefer IPv4, prefer IPv6, or follow the system resolver order.
- The Docker image includes `dig`, `nslookup`, `ping`, and `traceroute` for network diagnostics.
- The web connection test reports DNS and TCP timings and the endpoint reached.

### Changed

- The Standard timing preset allows 16 seconds per request including queue time and keeps
  requests from the same client together across pauses of up to 0.8 seconds.

### Fixed

- Reject upstream responses whose function code, byte count, or write echo cannot belong to the
  current request. A mismatch now closes the connection and discards queued frames before a safe
  read retry, preventing shifted RTU-over-TCP responses from being assigned to later requests.
- Reject RTU-over-TCP streams with bytes waiting before a request or after a complete reply,
  including stale frames whose function and size match the next read.
- Apply the response timeout to the complete RTU-over-TCP frame and shorten connection attempts
  when DNS offers an address of the other family as a fallback.
- Include queue time in the total request deadline. Expired queued requests return Modbus
  exception `0x0B` while the active request continues.
- Enforce the reconnect delay after an expired upstream exchange. Discard late RTU-over-TCP data
  and require a quiet interval on the replacement stream before sending another request.
- Reuse recent DNS results on upstream reconnects. Refresh them in the background and resolve
  immediately when cached addresses fail.
- Share the connection timeout across DNS and TCP and try the alternate address family
  promptly when the preferred endpoint stalls.
- Defer scheduled TCP renewal until the next client sequence so a planned reconnect cannot
  split consecutive requests from a configuration read.

### Documentation

- Documented that a second configuration read in TROVIS-VIEW can fail even with a direct USR
  adapter connection. Restarting TROVIS-VIEW allows another successful read in the tested setup.
  See the [README note on repeated configuration reads](README.md#why-can-a-second-read-in-trovis-view-fail).

## [1.2.0] - 2026-11-21

### Added

- Persistent forwarding control in the administration interface.
- Fast, Standard, Reliable, and Custom timing selections for controller profiles.
- Automatic Custom selection after a manual timing change and preset recognition when loading a
  profile.
- Explicit DNS-name resolution before TCP connection establishment, including the resolved address
  in connection-test results and documented IPv6-to-IPv4 fallback behavior.
- Status and configuration API fields for the persistent forwarding state.
- Automated coverage for immediate and queued-request rejection, persistence, and administration
  controls.

### Changed

- Declared the application, package, administration UI, and container image as release 1.2.0.
- Extended the English and German documentation for forwarding pauses and timing selections.

### Safety

- Active requests finish safely when forwarding is paused. New and already queued requests receive
  Modbus gateway exception `0x0B` and are not sent to the controller.
- Paused requests are not stored or executed after forwarding resumes, preventing delayed writes.

## [1.1.1] - 2026-11-13

### Added

- Automated multi-platform container publishing to Docker Hub and GitHub Container Registry.
- A package-based Docker Compose deployment and expanded NAS installation guidance.
- Updated interface examples with the release number in the status screenshot.

### Changed

- Renamed the public product from TROVIS Proxy Gateway to TROVIS Modbus Proxy throughout the code,
  administration interface, container metadata, and documentation.
- Switched the default Docker Compose deployment to the published Docker Hub image.
- Moved the previous local-build Compose definition to a hidden rollback file.

## [1.1.0] - 2026-11-13

### Added

- Initial TROVIS proxy implementation with Modbus TCP, RTU-over-TCP, and Serial RTU controller
  transports.
- Browser-based controller profile management, operational status, and persistent configuration.
- Serialized multi-client request arbitration with short-lived client affinity to prevent competing
  applications from interleaving controller request sequences.
- Configurable pacing, timeouts, retries, connection renewal, and raw Modbus tracing.
- Docker Compose and Python installation paths, including documented transparent USR adapter setup.
- Repository-linked OCI image metadata and an expanded project rationale and feature overview.

### Safety

- Transparent forwarding of Modbus PDUs without a controller-specific register map or address
  translation.
- Read retries only after eligible transport failures and no repeated write after an ambiguous
  result.
- Access keys remain masked and are not inserted into pass-through protocol traffic.
- Hardened the runtime image by upgrading operating-system packages, updating and removing the
  build-time package installer, and running the service as an unprivileged user.

[Unreleased]: https://github.com/macsobeck/trovis-proxy/compare/v1.2.3...HEAD
[1.2.3]: https://github.com/macsobeck/trovis-proxy/compare/32bc056...v1.2.3
[1.2.2]: https://github.com/macsobeck/trovis-proxy/compare/v1.2.1...32bc056
[1.2.1]: https://github.com/macsobeck/trovis-proxy/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/macsobeck/trovis-proxy/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/macsobeck/trovis-proxy/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/macsobeck/trovis-proxy/releases/tag/v1.1.0
