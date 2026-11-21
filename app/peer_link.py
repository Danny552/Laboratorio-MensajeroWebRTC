"""Enlace saliente hacia el otro nodo (cliente WebSocket con reconexión)."""
import asyncio
import logging

import websockets

from .protocol import dumps

log = logging.getLogger("peer_link")


class PeerLink:
    def __init__(self, node: str, url: str, token: str, router):
        self.node, self.url, self.token, self.router = node, url, token, router
        self.ws = None

    @property
    def connected(self) -> bool:
        return self.ws is not None

    async def send(self, msg: dict) -> bool:
        if self.ws is None:
            return False
        try:
            await self.ws.send(dumps(msg))
            return True
        except Exception as e:
            log.warning("No se pudo enviar al nodo par: %s", e)
            return False

    async def run(self):
        delay = 1
        full_url = f"{self.url}?node={self.node}&token={self.token}"
        while True:
            try:
                log.info("Conectando con el nodo par %s ...", self.url)
                async with websockets.connect(full_url, ping_interval=20, ping_timeout=20) as ws:
                    self.ws = ws
                    delay = 1
                    log.info("Enlace saliente ESTABLECIDO con %s", self.url)
                    await self.router.send_sync()
                    async for _ in ws:   # este enlace solo envía; si llega algo se ignora
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("Enlace con el nodo par caído (%s); reintento en %ss", e, delay)
            finally:
                self.ws = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 15)
