"""Prueba de la lógica de enrutamiento SIN red: dos Router unidos por un enlace simulado.
Ejecutar:  python -m unittest tests.test_router -v
"""
import asyncio
import json
import unittest

from app.router import Router


class FakeWS:
    """Cliente simulado: guarda lo que el servidor le envía."""
    def __init__(self):
        self.inbox = []

    async def send_text(self, text):
        self.inbox.append(json.loads(text))

    def types(self):
        return [m["type"] for m in self.inbox]


class FakeLink:
    """Enlace saliente simulado: entrega directamente al Router del otro nodo."""
    def __init__(self, target: Router):
        self.target, self.up = target, True
        self.connected = True

    async def send(self, msg):
        if not self.up:
            return False
        await self.target.from_peer(json.dumps(msg))
        return True


def make_pair():
    a, b = Router("nodo-a"), Router("nodo-b")
    a.link, b.link = FakeLink(b), FakeLink(a)
    return a, b


def msg(**kw):
    kw.setdefault("payload", {})
    return json.dumps(kw)


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.a, self.b = make_pair()
        self.ana, self.Dani = FakeWS(), FakeWS()
        await self.a.register("ana", self.ana)
        await self.b.register("Dani", self.Dani)

    async def test_presencia_entre_nodos(self):
        self.assertIn("Dani", self.a.remote_users)
        self.assertIn("ana", self.b.remote_users)
        self.assertIn("presence", self.ana.types())

    async def test_chat_reenviado_al_otro_nodo(self):
        await self.a.from_client("ana", msg(type="chat", to="Dani", payload={"text": "hola"}))
        chat = [m for m in self.Dani.inbox if m["type"] == "chat"]
        self.assertEqual(len(chat), 1)
        self.assertEqual(chat[0]["from"], "ana")
        self.assertEqual(chat[0]["payload"]["text"], "hola")

    async def test_origen_no_se_puede_suplantar(self):
        await self.a.from_client("ana", msg(type="chat", to="Dani", **{"from": "root"}, payload={"text": "x"}))
        self.assertEqual([m for m in self.Dani.inbox if m["type"] == "chat"][0]["from"], "ana")

    async def test_entrega_local(self):
        luis = FakeWS()
        await self.a.register("luis", luis)
        await self.a.from_client("ana", msg(type="chat", to="luis", payload={"text": "k"}))
        self.assertEqual(len([m for m in luis.inbox if m["type"] == "chat"]), 1)
        self.assertEqual([m for m in self.Dani.inbox if m["type"] == "chat"], [])

    async def test_usuario_inexistente(self):
        await self.a.from_client("ana", msg(type="chat", to="nadie", payload={"text": "?"}))
        self.assertEqual(self.ana.inbox[-1]["payload"]["code"], "user_not_found")

    async def test_nombre_duplicado_entre_nodos(self):
        self.assertEqual(await self.a.register("Dani", FakeWS()), "user_taken")

    async def test_offer_sin_destinatario(self):
        await self.a.from_client("ana", msg(type="offer", payload={"sdp": "v=0"}))
        self.assertEqual(self.ana.inbox[-1]["payload"]["code"], "missing_to")

    async def test_json_invalido(self):
        await self.a.from_client("ana", "esto no es json")
        self.assertEqual(self.ana.inbox[-1]["payload"]["code"], "bad_json")

    async def test_difusion(self):
        await self.a.from_client("ana", msg(type="chat", payload={"text": "todos"}))
        self.assertEqual(len([m for m in self.Dani.inbox if m["type"] == "chat"]), 1)

    async def test_caida_del_enlace(self):
        ws = object()
        self.b.peer_connected(ws, "nodo-a")        # enlace entrante en B
        self.a.link.up = False
        await self.a.from_client("ana", msg(type="chat", to="Dani", payload={"text": "x"}))
        self.assertEqual(self.ana.inbox[-1]["payload"]["code"], "peer_unavailable")
        await self.b.peer_disconnected(ws)          # B pierde a los usuarios remotos
        self.assertEqual(self.b.remote_users, set())

    async def test_error_vuelve_al_remitente_remoto(self):
        await self.a.from_client("ana", msg(type="chat", to="Dani", payload={"text": "1"}))
        await self.b.unregister("Dani", self.Dani)
        self.a.remote_users.add("Dani")            # A aún cree que existe (carrera)
        await self.a.from_client("ana", msg(type="chat", to="Dani", payload={"text": "2"}))
        self.assertEqual(self.ana.inbox[-1]["payload"]["code"], "user_not_found")


if __name__ == "__main__":
    unittest.main()
