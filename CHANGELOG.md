# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
semantic versioning.

## [Unreleased]

## [1.2.0] - 2026-11-21

### Added

- Persistent forwarding control in the administration interface.
- Two pause modes: reject requests immediately or buffer all requests until forwarding resumes.
- Configurable buffer retention from 1 to 3600 seconds, with a 300-second default.
- Fast, Standard, Reliable, and Custom timing selections for controller profiles.
- Automatic Custom selection after a manual timing change and preset recognition when loading a
  profile.
- Status and configuration API fields for the forwarding state, pause mode, and retention time.
- Automated coverage for immediate rejection, buffered reads and writes, unknown function codes,
  persistence, and administration controls.

### Changed

- Declared the application, package, administration UI, and container image as release 1.2.0.
- Extended the English and German documentation for forwarding pauses and timing selections.

### Safety

- Without buffering, paused requests are rejected with Modbus gateway exception `0x0B` and are not
  sent to the controller.
- With buffering, reads, writes, and unknown or vendor-specific function codes remain blocked while
  paused and are forwarded after resuming. A buffered write may still execute after its client has
  timed out; expired requests are discarded.

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

[Unreleased]: https://github.com/macsobeck/trovis-proxy/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/macsobeck/trovis-proxy/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/macsobeck/trovis-proxy/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/macsobeck/trovis-proxy/releases/tag/v1.1.0
