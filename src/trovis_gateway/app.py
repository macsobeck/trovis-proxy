"""Modbus Proxy process lifecycle."""

from __future__ import annotations

import asyncio
import logging

from .admin.server import AdminServer
from .config import InfrastructureSettings
from .metrics import GatewayMetrics
from .proxy import ModbusProxy
from .store import ConfigStore
from .trace import GatewayTrace
from .upstream import UpstreamRouter


class GatewayApplication:
    def __init__(self, settings: InfrastructureSettings) -> None:
        self.settings = settings
        self.store = ConfigStore(settings.config_path)
        self.metrics = GatewayMetrics()
        self.trace = GatewayTrace(settings.trace_modbus)
        self.router = UpstreamRouter(self.metrics, self.trace)
        self.proxy = ModbusProxy(
            host=settings.listen_host,
            port=settings.listen_port,
            store=self.store,
            router=self.router,
            metrics=self.metrics,
            trace=self.trace,
        )
        self.admin: AdminServer | None = None

    async def start(self) -> None:
        self.store.load()
        await self.proxy.start()
        self.admin = AdminServer(
            self.settings,
            self.store,
            self.metrics,
            asyncio.get_running_loop(),
        )
        self.admin.start()
        logging.getLogger("trovis_gateway").info(
            "Modbus Proxy listening on %s:%s; admin on %s:%s",
            self.settings.listen_host,
            self.proxy.bound_port,
            self.settings.admin_host,
            self.admin.bound_port,
        )

    async def close(self) -> None:
        if self.admin is not None:
            await asyncio.to_thread(self.admin.close)
            self.admin = None
        await self.proxy.close()

    async def run(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        finally:
            await self.close()
