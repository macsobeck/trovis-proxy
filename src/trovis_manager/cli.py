"""``trovisctl`` read-only command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from trovis_manager.catalog import RegisterCatalog
from trovis_manager.configuration import ConfigurationService
from trovis_manager.controller import golden_mock_transport
from trovis_manager.hardware import HardwareValidator
from trovis_manager.hardware.models import ValidationOutcome
from trovis_manager.models import ControllerIdentity
from trovis_manager.storage import load_snapshot, save_snapshot
from trovis_manager.transport import ConnectionManager, ConnectionSettings
from trovis_manager.transport.live import LiveTransport


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trovisctl", description="Read-only TROVIS 5573-1 tool")
    parser.add_argument(
        "--transport", choices=("mock", "tcp", "serial", "rtu-tcp"), default="mock"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--device", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=19200)
    parser.add_argument("--unit", type=int, default=247)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--backoff", type=float, default=0.1)
    parser.add_argument("--connect-delay", type=float, default=0.0)
    parser.add_argument("--modbus-trace", action="store_true")
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("connect")
    command.add_parser("identify")
    read = command.add_parser("read")
    read.add_argument("data_point")
    read_group = command.add_parser("read-group")
    read_group.add_argument("group")
    command.add_parser("read-config")
    backup = command.add_parser("backup")
    backup.add_argument("file", type=Path)
    validate = command.add_parser("validate")
    validate.add_argument("file", type=Path)
    hardware = command.add_parser(
        "hardware", description="Explicit read-only real-controller validation"
    )
    hardware.add_argument(
        "--transport", choices=("tcp", "serial", "rtu-tcp"), required=True
    )
    hardware.add_argument("--host")
    hardware.add_argument("--port", type=int, default=502)
    hardware.add_argument("--device")
    hardware.add_argument("--baudrate", type=int, default=19200)
    hardware.add_argument("--unit", type=int, default=247)
    hardware.add_argument("--timeout", type=float, default=2.0)
    hardware.add_argument("--retries", type=int, default=2)
    hardware.add_argument("--delay", type=float, default=0.1)
    hardware.add_argument("--backoff", type=float, default=0.25)
    hardware.add_argument("--connect-delay", type=float, default=0.25)
    hardware.add_argument("--modbus-trace", action="store_true")
    hardware_command = hardware.add_subparsers(dest="hardware_command", required=True)
    hardware_command.add_parser("identify")
    hardware_command.add_parser("read-config")
    hardware_backup = hardware_command.add_parser("backup")
    hardware_backup.add_argument("file", type=Path)
    hardware_validate = hardware_command.add_parser("validate")
    hardware_validate.add_argument(
        "--output-root", type=Path, default=Path("hardware-validation")
    )
    endurance = hardware_command.add_parser("endurance-read")
    endurance.add_argument("--runs", type=int, default=20)
    endurance.add_argument("--pause", type=float, default=2.0)
    endurance.add_argument(
        "--output-root", type=Path, default=Path("hardware-validation")
    )
    return parser


def _manager(args: argparse.Namespace) -> ConnectionManager:
    if args.command == "hardware":
        if args.transport in {"tcp", "rtu-tcp"} and not args.host:
            raise ValueError("--host is required for hardware TCP transports")
        if args.transport == "serial" and not args.device:
            raise ValueError("--device is required for hardware serial transport")
    if args.transport == "mock":
        transport = golden_mock_transport()
    elif args.transport == "tcp":
        transport = LiveTransport.tcp(
            args.host, args.port, args.unit, args.timeout, args.connect_delay
        )
    elif args.transport == "rtu-tcp":
        transport = LiveTransport.rtu_over_tcp(
            args.host,
            args.port,
            args.unit,
            args.timeout,
            args.baudrate,
            args.connect_delay,
        )
    else:
        transport = LiveTransport.serial(
            args.device,
            args.unit,
            args.timeout,
            args.baudrate,
            args.connect_delay,
        )
    return ConnectionManager(
        transport,
        ConnectionSettings(
            timeout=args.timeout,
            inter_request_delay=args.delay,
            retries=args.retries,
            retry_backoff=args.backoff,
            trace_enabled=args.modbus_trace,
        ),
    )


def _print_identity(identity: ControllerIdentity) -> None:
    print(f"SAMSON {identity.model}")
    print(f"Firmware: {identity.firmware}")
    print(f"Hardware: {identity.hardware_version or 'UNKNOWN'}")
    print(f"Serial: {identity.serial_number or 'UNKNOWN'}")
    print(f"Serial raw candidate: {identity.serial_number_raw or 'UNKNOWN'}")
    print(f"System: {identity.system_code}")
    print(f"Unit ID: {identity.modbus_unit_id}")


async def _run_hardware(args: argparse.Namespace) -> int:
    manager = _manager(args)
    catalog = RegisterCatalog.load()
    service = ConfigurationService(manager, catalog)
    validator = HardwareValidator(service, manager, catalog)
    try:
        if args.hardware_command == "identify":
            _print_identity(await validator.identify_gate())
            return 0
        if args.hardware_command in {"read-config", "backup"}:
            snapshot = await validator.read_once()
            if args.hardware_command == "backup":
                save_snapshot(snapshot, args.file)
                print(f"saved {snapshot.status} hardware snapshot to {args.file}")
            else:
                print(snapshot.model_dump_json(indent=2))
            return 0 if snapshot.status == "complete" else 2
        runs = 1 if args.hardware_command == "validate" else args.runs
        pause = 0.0 if args.hardware_command == "validate" else args.pause
        output_dir, summary = await validator.endurance_read(
            runs=runs,
            pause_s=pause,
            output_root=args.output_root,
        )
        print(f"hardware validation: {summary.outcome}")
        print(f"reports: {output_dir}")
        return 0 if summary.outcome == ValidationOutcome.PASS else 2
    finally:
        try:
            await manager.disconnect()
        except Exception:
            pass


async def _run(args: argparse.Namespace) -> int:
    if args.command == "validate":
        snapshot = load_snapshot(args.file)
        print(f"valid snapshot {snapshot.schema_version}: {snapshot.status}")
        return 0
    if args.command == "hardware":
        return await _run_hardware(args)
    manager = _manager(args)
    service = ConfigurationService(manager, RegisterCatalog.load())
    try:
        if args.command == "connect":
            await manager.connect()
            print(f"connected ({args.transport})")
        elif args.command == "identify":
            identity = await service.identify()
            _print_identity(identity)
        elif args.command == "read":
            result = await service.read(args.data_point)
            print(result.model_dump_json(indent=2))
            return 0 if result.successful else 2
        elif args.command == "read-group":
            results = await service.read_group(args.group)
            print(json.dumps([item.model_dump(mode="json") for item in results], indent=2))
            return 0 if all(item.successful for item in results) else 2
        elif args.command in {"read-config", "backup"}:
            snapshot = await service.read_config()
            if args.command == "backup":
                save_snapshot(snapshot, args.file)
                print(f"saved {snapshot.status} snapshot to {args.file}")
            else:
                print(snapshot.model_dump_json(indent=2))
            return 0 if not snapshot.errors else 2
        return 0
    finally:
        try:
            await manager.disconnect()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> None:
    try:
        code = asyncio.run(_run(_parser().parse_args(argv)))
    except (KeyError, ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
