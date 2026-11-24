import asyncio
import json
import urllib.request

import websockets

A, B = "ws://localhost:8001", "ws://localhost:8002"
HTTP_A = "http://localhost:8001"


async def recv_type(ws, tipo, timeout=5):
    async def _loop():
        while True:
            m = json.loads(await ws.recv())
            if m["type"] == tipo:
                return m
    return await asyncio.wait_for(_loop(), timeout)


async def send(ws, **kw):
    kw.setdefault("payload", {})
    await ws.send(json.dumps(kw))


def status(url):
    return json.load(urllib.request.urlopen(url + "/status"))


async def main():
    async with websockets.connect(f"{A}/ws?user=Ana") as Ana, websockets.connect(f"{B}/ws?user=Dani") as Dani:
        await recv_type(Ana, "welcome")
        await recv_type(Dani, "welcome")
        for _ in range(50):                       # esperar a que nodo-a conozca a Dani
            if "Dani" in status(HTTP_A)["remote_users"]:
                break
            await asyncio.sleep(0.1)
        print("1. Estado nodo-a:", status(HTTP_A))

        await send(Ana, type="chat", to="Dani", payload={"text": "hola Dani, desde nodo-a"})
        m = await recv_type(Dani, "chat")
        print("2. Dani recibió en nodo-b:", m["from"], "->", m["payload"]["text"])
        assert m["from"] == "Ana"

        await send(Dani, type="chat", to="Ana", payload={"text": "hola Ana, desde nodo-b"})
        m = await recv_type(Ana, "chat")
        print("3. Ana recibió en nodo-a:", m["from"], "->", m["payload"]["text"])

        await send(Ana, type="chat", to="fantasma", payload={"text": "?"})
        e = await recv_type(Ana, "error")
        print("4. error esperado:", e["payload"]["code"])
        assert e["payload"]["code"] == "user_not_found"

        await send(Ana, type="offer", to="Dani", payload={"sdp": "v=0 (simulado)"})
        m = await recv_type(Dani, "offer")
        print("5. oferta reenviada entre nodos:", m["from"], "->", m["to"])
    print("\nOK: la señalización entre nodos funciona. Revisa `docker compose logs` para ver el recorrido.")


asyncio.run(main())
