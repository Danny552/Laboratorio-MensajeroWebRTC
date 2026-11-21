"""Sobre JSON común de los mensajes de señalización (ver informe, C3)."""
import json
import time
import uuid

VERSION = 1
# Tipos que un cliente puede enviar.
CLIENT_TYPES = {"chat", "offer", "answer", "ice", "hangup", "ping"}


class ProtocolError(Exception):
    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def make(type_: str, *, frm=None, to=None, room="main", payload=None) -> dict:
    return {
        "v": VERSION,
        "type": type_,
        "id": uuid.uuid4().hex[:8],
        "from": frm,
        "to": to,
        "room": room,
        "ts": int(time.time()),
        "payload": payload or {},
    }


def parse(raw: str) -> dict:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        raise ProtocolError("bad_json", "El mensaje no es JSON válido")
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise ProtocolError("bad_message", "Falta el campo 'type'")
    if not isinstance(msg.get("payload", {}), dict):
        raise ProtocolError("bad_message", "'payload' debe ser un objeto")
    msg.setdefault("payload", {})
    msg.setdefault("room", "main")
    msg.setdefault("to", None)
    return msg


def dumps(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False)
