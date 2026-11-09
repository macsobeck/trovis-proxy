"""Downstream Modbus TCP server forwarding opaque PDUs to one controller."""

from __future__ import annotations

import asyncio
import logging

from .metrics import GatewayMetrics
from .protocol import encode_tcp_adu, exception_pdu, read_tcp_adu
from .store import ConfigStore
from .trace import GatewayTrace
from .upstream import UpstreamRequestError, UpstreamRouter


class ModbusProxy:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        store: ConfigStore,
        router: UpstreamRouter,
        metrics: GatewayMetrics,
        trace: GatewayTrace,
    ) -> None:
        self.host = host
        self.port = port
        self.store = store
        self.router = router
        self.metrics = metrics
        self.trace = trace
        self._server: asyncio.Server | None = None
        self._next_client_id = 1
        self._logger = logging.getLogger("trovis_gateway.proxy")

    @property
    def bound_port(self) -> int | None:
        if self._server is None or not self._server.sockets:
            return None
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        await self.router.close()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        client_id = self._next_client_id
        self._next_client_id += 1
        self.metrics.increment("downstream_clients")
        try:
            while True:
                try:
                    request = await read_tcp_adu(reader)
                except asyncio.IncompleteReadError:
                    break
                except (ConnectionError, ValueError) as exc:
                    self._logger.warning("Closing invalid downstream connection: %s", exc)
                    break

                self.metrics.increment("requests")
                profile = self.store.active_profile()
                self.trace.emit(
                    "DOWNSTREAM RX",
                    transaction_id=request.transaction_id,
                    downstream_unit_id=request.unit_id,
                    upstream_unit_id=profile.upstream_unit_id if profile else None,
                    pdu=request.pdu,
                )
                if profile is None:
                    response_pdu = exception_pdu(request.pdu, 0x0B)
                else:
                    try:
                        response_pdu = await self.router.request(
                            client_id=client_id,
                            transaction_id=request.transaction_id,
                            downstream_unit_id=request.unit_id,
                            pdu=request.pdu,
                            profile=profile,
                        )
                    except UpstreamRequestError:
                        response_pdu = exception_pdu(request.pdu, 0x0B)

                self.trace.emit(
                    "DOWNSTREAM TX",
                    transaction_id=request.transaction_id,
                    downstream_unit_id=request.unit_id,
                    upstream_unit_id=profile.upstream_unit_id if profile else None,
                    pdu=response_pdu,
                )
                writer.write(
                    encode_tcp_adu(request.transaction_id, request.unit_id, response_pdu)
                )
                try:
                    await writer.drain()
                except ConnectionError:
                    break
        finally:
            await self.router.release_client(client_id)
            self.metrics.increment("downstream_clients", -1)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
