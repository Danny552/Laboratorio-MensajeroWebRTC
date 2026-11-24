
import argparse
import asyncio
import json
import sys

import websockets


async def leer(ws):
    async for raw in ws:
        m = json.loads(raw)
        print(f"<< {m['type']:9} de={m.get('from')} payload={json.dumps(m['payload'], ensure_ascii=False)}", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8001")
    ap.add_argument("--user", required=True)
    ap.add_argument("--to")
    ap.add_argument("--text")
    ap.add_argument("--wait", type=float, default=0, help="segundos a escuchar tras enviar (modo un envío)")
    a = ap.parse_args()

    async with websockets.connect(f"{a.url}/ws?user={a.user}") as ws:
        lector = asyncio.create_task(leer(ws))
        if a.text:
            await ws.send(json.dumps({"type": "chat", "to": a.to, "payload": {"text": a.text}}))
            print(f">> chat a={a.to or 'TODOS'}: {a.text}")
            await asyncio.sleep(a.wait)
        else:
            print(f"Conectado como {a.user}. '@usuario texto' o 'texto' (a todos). Ctrl+C para salir.")
            loop = asyncio.get_running_loop()
            while True:
                linea = (await loop.run_in_executor(None, sys.stdin.readline)).strip()
                if not linea:
                    continue
                to, text = None, linea
                if linea.startswith("@") and " " in linea:
                    to, text = linea[1:].split(" ", 1)
                await ws.send(json.dumps({"type": "chat", "to": to, "payload": {"text": text}}))
        lector.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
