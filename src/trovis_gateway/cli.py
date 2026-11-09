"""Command-line entry point for infrastructure-only gateway settings."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import replace
from pathlib import Path

from . import __version__
from .app import GatewayApplication
from .config import InfrastructureSettings


def parser() -> argparse.ArgumentParser:
    defaults = InfrastructureSettings.from_environment()
    command = argparse.ArgumentParser(description="Generic TROVIS Proxy Gateway")
    command.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    command.add_argument("--listen-host", default=defaults.listen_host)
    command.add_argument("--listen-port", type=int, default=defaults.listen_port)
    command.add_argument("--admin-host", default=defaults.admin_host)
    command.add_argument("--admin-port", type=int, default=defaults.admin_port)
    command.add_argument("--config-path", type=Path, default=defaults.config_path)
    command.add_argument("--modbus-trace", action="store_true", default=defaults.trace_modbus)
    command.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING"), default="INFO")
    return command


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, arguments.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = replace(
        InfrastructureSettings.from_environment(),
        listen_host=arguments.listen_host,
        listen_port=arguments.listen_port,
        admin_host=arguments.admin_host,
        admin_port=arguments.admin_port,
        config_path=arguments.config_path,
        trace_modbus=arguments.modbus_trace,
    )
    try:
        asyncio.run(GatewayApplication(settings).run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
