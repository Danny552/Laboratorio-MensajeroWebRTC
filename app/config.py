import logging
import os

NODE_NAME = os.getenv("NODE_NAME", "nodo")
PEER_URL = os.getenv("PEER_URL", "")          # p. ej. ws://nodo-b:8000/ws/peer
PEER_TOKEN = os.getenv("PEER_TOKEN", "dev-secret")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format=f"%(asctime)s [{NODE_NAME}] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
