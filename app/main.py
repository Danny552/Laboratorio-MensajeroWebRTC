import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .config import NODE_NAME, PEER_TOKEN, PEER_URL
from .peer_link import PeerLink
from .protocol import dumps, make
from .router import Router

log = logging.getLogger("main")
router = Router(NODE_NAME)
USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if PEER_URL:
        router.link = PeerLink(NODE_NAME, PEER_URL, PEER_TOKEN, router)
        task = asyncio.create_task(router.link.run())
    log.info("Nodo %s listo (par: %s)", NODE_NAME, PEER_URL or "ninguno")
    yield
    if task:
        task.cancel()


app = FastAPI(title=f"Señalización {NODE_NAME}", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "node": NODE_NAME}


@app.get("/status")
async def status():
    return {
        "node": NODE_NAME,
        "local_users": sorted(router.users),
        "remote_users": sorted(router.remote_users),
        "peer_out_connected": bool(router.link and router.link.connected),
        "peer_in_connected": router.peer_in is not None,
    }


async def _reject(ws: WebSocket, code: int, err: str, text: str):
    await ws.send_text(dumps(make("error", payload={"code": err, "msg": text})))
    await ws.close(code=code)


@app.websocket("/ws")
async def ws_client(ws: WebSocket, user: str = ""):
    await ws.accept()
    user = user.strip()
    if not USER_RE.match(user):
        return await _reject(ws, 4400, "invalid_user", "Usuario inválido (1-32 letras, números, - o _)")
    err = await router.register(user, ws)
    if err:
        return await _reject(ws, 4409, err, f"El usuario '{user}' ya está conectado")
    try:
        while True:
            await router.from_client(user, await ws.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        await router.unregister(user, ws)


@app.websocket("/ws/peer")
async def ws_peer(ws: WebSocket, node: str = "", token: str = ""):
    await ws.accept()
    if token != PEER_TOKEN:
        log.warning("Enlace de nodo rechazado (token inválido) desde %s", node)
        return await ws.close(code=4403)
    router.peer_connected(ws, node)
    try:
        while True:
            await router.from_peer(await ws.receive_text())
    except WebSocketDisconnect:
        pass
    finally:
        await router.peer_disconnected(ws)


_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")
