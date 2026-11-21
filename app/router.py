"""Usuarios locales, usuarios del nodo par y enrutamiento de mensajes."""
import logging

from .protocol import CLIENT_TYPES, ProtocolError, dumps, make, parse

log = logging.getLogger("router")


class Router:
    def __init__(self, node: str):
        self.node = node
        self.users: dict[str, object] = {}     # usuario -> WebSocket local
        self.remote_users: set[str] = set()    # usuarios conectados al otro nodo
        self.link = None                       # PeerLink (enlace saliente)
        self.peer_in = None                    # WebSocket del enlace entrante

    # ------------------------------------------------------------ utilidades
    def online(self) -> list[str]:
        return sorted(set(self.users) | self.remote_users)

    async def _to_ws(self, ws, msg: dict):
        try:
            await ws.send_text(dumps(msg))
        except Exception as e:
            log.warning("No se pudo entregar a un cliente: %s", e)

    async def _broadcast_local(self, msg: dict, exclude: str | None = None):
        for name, ws in list(self.users.items()):
            if name != exclude:
                await self._to_ws(ws, msg)

    async def _error(self, to_user: str, code: str, text: str, ref=None):
        msg = make("error", to=to_user, payload={"code": code, "msg": text, "ref": ref})
        if to_user in self.users:
            await self._to_ws(self.users[to_user], msg)
        elif self.link:
            await self.link.send(msg)   # el destinatario del error está en el otro nodo

    def _presence(self, user: str, online: bool) -> dict:
        return make("presence", frm=user, payload={"user": user, "online": online, "node": self.node})

    # ------------------------------------------------------------ clientes
    async def register(self, user: str, ws) -> str | None:
        if user in self.users or user in self.remote_users:
            return "user_taken"
        self.users[user] = ws
        log.info("USUARIO conectado: %s (locales=%s remotos=%s)", user, sorted(self.users), sorted(self.remote_users))
        await self._to_ws(ws, make("welcome", payload={"user": user, "node": self.node, "online": self.online()}))
        pres = self._presence(user, True)
        await self._broadcast_local(pres, exclude=user)
        if self.link:
            await self.link.send(pres)
        return None

    async def unregister(self, user: str, ws):
        if self.users.get(user) is not ws:
            return
        del self.users[user]
        log.info("USUARIO desconectado: %s", user)
        pres = self._presence(user, False)
        await self._broadcast_local(pres)
        if self.link:
            await self.link.send(pres)

    async def from_client(self, sender: str, raw: str):
        try:
            msg = parse(raw)
        except ProtocolError as e:
            await self._error(sender, e.code, e.msg)
            return
        t = msg["type"]
        if t not in CLIENT_TYPES:
            await self._error(sender, "unknown_type", f"Tipo no permitido: {t}", msg.get("id"))
            return
        if t == "ping":
            await self._to_ws(self.users[sender], make("pong", to=sender))
            return
        # el origen lo fija el servidor: el cliente no puede suplantar a otro
        msg["from"] = sender
        msg["ts"] = make("x")["ts"]
        msg.setdefault("id", make("x")["id"])
        to = msg.get("to")

        if to is None:
            if t != "chat":
                await self._error(sender, "missing_to", f"'{t}' necesita destinatario ('to')", msg["id"])
                return
            log.info("MSG %s %s -> TODOS: %s", t, sender, msg["payload"].get("text", ""))
            await self._broadcast_local(msg, exclude=sender)
            if self.link:
                await self.link.send(msg)
            return

        if to in self.users:
            log.info("MSG %s %s -> %s (entrega LOCAL)", t, sender, to)
            await self._to_ws(self.users[to], msg)
        elif to in self.remote_users:
            ok = await self.link.send(msg) if self.link else False
            log.info("MSG %s %s -> %s (REENVIADO al nodo par, ok=%s)", t, sender, to, ok)
            if not ok:
                await self._error(sender, "peer_unavailable", "El nodo par no está disponible", msg["id"])
        else:
            log.info("MSG %s %s -> %s: destinatario no encontrado", t, sender, to)
            await self._error(sender, "user_not_found", f"No existe el usuario '{to}'", msg["id"])

    # ------------------------------------------------------------ nodo par
    def peer_connected(self, ws, node: str):
        self.peer_in = ws
        log.info("Enlace entrante ESTABLECIDO desde %s", node)

    async def peer_disconnected(self, ws):
        if self.peer_in is not ws:
            return          # ya hay un enlace más nuevo; no se borra su estado
        self.peer_in = None
        gone = sorted(self.remote_users)
        self.remote_users.clear()
        log.warning("Enlace entrante CAÍDO; usuarios remotos perdidos: %s", gone)
        for u in gone:
            await self._broadcast_local(self._presence(u, False))

    async def send_sync(self):
        """Informa al otro nodo de los usuarios locales (al conectar o reconectar)."""
        if self.link:
            await self.link.send(make("sync", payload={"users": sorted(self.users), "node": self.node}))

    async def from_peer(self, raw: str):
        try:
            msg = parse(raw)
        except ProtocolError as e:
            log.warning("Mensaje inválido del nodo par: %s", e.msg)
            return
        t, to = msg["type"], msg.get("to")

        if t == "presence":
            user = msg["payload"].get("user")
            if msg["payload"].get("online"):
                self.remote_users.add(user)
            else:
                self.remote_users.discard(user)
            log.info("PRESENCIA remota: %s online=%s", user, msg["payload"].get("online"))
            await self._broadcast_local(msg)
            return
        if t == "sync":
            new = set(msg["payload"].get("users", []))
            for u in sorted(new - self.remote_users):
                await self._broadcast_local(self._presence(u, True))
            for u in sorted(self.remote_users - new):
                await self._broadcast_local(self._presence(u, False))
            self.remote_users = new
            log.info("SYNC con el nodo par; usuarios remotos=%s", sorted(new))
            return

        # Mensaje reenviado: se entrega SOLO localmente (nunca se reenvía otra vez).
        if to is None:
            log.info("MSG %s %s -> TODOS (recibido del nodo par)", t, msg.get("from"))
            await self._broadcast_local(msg)
        elif to in self.users:
            log.info("MSG %s %s -> %s (recibido del nodo par, entrega LOCAL)", t, msg.get("from"), to)
            await self._to_ws(self.users[to], msg)
        elif t != "error":
            log.info("MSG %s para %s: no existe aquí", t, to)
            await self._error(msg.get("from"), "user_not_found", f"No existe el usuario '{to}'", msg.get("id"))
