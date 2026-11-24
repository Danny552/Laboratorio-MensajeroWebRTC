# Mensajero WebRTC (Docker) · Avance sin interfaz

Dos nodos de señalización (Python + FastAPI) que corren en contenedores, se encuentran **por nombre**
en una red Docker y se reenvían los mensajes de sus usuarios. Informe de investigación: `docs/informe_investigacion.pdf`.

## Requisitos
- Docker y Docker Compose v2.
- Python 3.12 en el anfitrión solo para los scripts de prueba (`pip install websockets`).

## Ejecutar
```bash
cp .env.example .env        # opcional: cambia puertos o PEER_TOKEN
docker compose up --build
```
Puertos en el anfitrión: **8001** → nodo-a, **8002** → nodo-b (dentro de la red, ambos escuchan en 8000 y se ven como `nodo-a:8000` / `nodo-b:8000`).

## Probar este avance
1. **Estado de los nodos** (deben verse los enlaces):
   ```bash
   curl http://localhost:8001/status
   curl http://localhost:8002/status
   ```
2. **Demostración automática** (ana en nodo-a y beto en nodo-b):
   ```bash
   pip install websockets
   python scripts/demo.py
   ```
3. **A mano, con dos terminales** (ana en nodo-a, beto en nodo-b):
   ```bash
   python scripts/cliente.py --user ana  --url ws://localhost:8001
   python scripts/cliente.py --user beto --url ws://localhost:8002
   # en la de ana escribe:  @beto hola
   ```
   O con wscat: `wscat -c "ws://localhost:8002/ws?user=beto"` y enviar
   `{"type":"chat","to":"ana","payload":{"text":"hola"}}`.
4. **Logs de ambos nodos** (muestran cada mensaje, si fue local o reenviado):
   ```bash
   docker compose logs -f nodo-a nodo-b
   ```
5. **Caída de un nodo**: `docker compose stop nodo-b` → nodo-a pierde a los usuarios de nodo-b
   (`user_not_found`) y reintenta el enlace; `docker compose start nodo-b` y se reconectan solos.
6. **Pruebas de la lógica sin red**: `python -m unittest tests.test_router -v`

## Estructura
```
app/main.py        endpoints HTTP y WebSocket (/ws, /ws/peer, /status, /health)
app/router.py      usuarios locales/remotos y enrutamiento
app/peer_link.py   enlace saliente hacia el otro nodo (reconexión con espera creciente)
app/protocol.py    sobre JSON de los mensajes
scripts/           cliente de consola y demo
tests/             pruebas de la lógica
```

## Protocolo
Sobre: `{v, type, id, from, to, room, ts, payload}`. Tipos del cliente: `chat`, `offer`, `answer`, `ice`, `hangup`, `ping`.
Del servidor: `welcome`, `presence`, `error`, `pong`. Entre nodos: además `sync`.
El servidor fija `from`; un mensaje recibido por `/ws/peer` se entrega solo localmente (evita bucles).

## Problemas conocidos
- `/ws/peer` está publicado junto con el resto del puerto; se protege con `PEER_TOKEN`.
- Aún no hay interfaz web ni WebRTC.
   