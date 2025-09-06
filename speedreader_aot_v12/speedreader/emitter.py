
from __future__ import annotations
import json

MAGIC = b"SRDG"

def _load_blob(blob: bytes):
    if not blob.startswith(MAGIC):
        raise ValueError("Bad magic")
    ver = blob[4]
    mlen = int.from_bytes(blob[5:9], "big")
    meta = json.loads(blob[9:9+mlen].decode("utf-8"))
    code = blob[9+mlen:]
    return meta, code

def load_dgm(blob: bytes):
    return _load_blob(blob)
