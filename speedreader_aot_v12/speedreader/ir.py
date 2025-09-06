
from __future__ import annotations
from typing import List, Tuple, Any, Dict
import json
from .base12 import UCIO_REG

def _svarint(n: int) -> bytes:
    # ZigZag-like signed varint (two's complement continuation-friendly)
    out = bytearray()
    more = True
    while more:
        byte = n & 0x7F
        n >>= 7
        sign_bit = (byte & 0x40) != 0
        if (n == 0 and not sign_bit) or (n == -1 and sign_bit):
            more = False
        else:
            byte |= 0x80
        out.append(byte)
    return bytes(out)

class IR:
    def __init__(self):
        self.code: List[int] = []  # stream of opcodes and immediates (as ints/markers)
        self.strings: Dict[str,int] = {}
        self.strtab: List[str] = []

    def _str_idx(self, s: str) -> int:
        if s in self.strings:
            return self.strings[s]
        idx = len(self.strtab)
        self.strings[s] = idx; self.strtab.append(s)
        return idx

    def emit(self, name: str, *args, src_span=None):
        op = UCIO_REG.emit(name)
        self.code.append(op)
        if name in {"LITERAL_I64","SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END","JMP","JMP_IF_FALSE"}:
            self.code.extend(_svarint(int(args[0])))
        elif name in {"FOR_HINT"}:
            a,b,s,inc = args
            self.code.extend(_svarint(int(a))); self.code.extend(_svarint(int(b)))
            self.code.extend(_svarint(int(s))); self.code.extend(_svarint(int(inc)))
        elif name in {"LITERAL_STR","BIND_CONST","BIND_MUT","LOAD","STORE","CALL","FN_LABEL"}:
            # string immediates are tagged by 254 then string index
            if name == "CALL":
                fname, argc = args
                self.code.append(254); self.code.extend(_svarint(self._str_idx(fname)))
                self.code.extend(_svarint(int(argc)))
            elif name == "FN_LABEL":
                fname = args[0]; pcount = int(args[1])
                self.code.append(254); self.code.extend(_svarint(self._str_idx(fname)))
                self.code.extend(_svarint(pcount))
                # param names
                pos = 2
                for _ in range(pcount):
                    self.code.append(254); self.code.extend(_svarint(self._str_idx(str(args[pos])))); pos+=1
                # capture count and names (optional; default 0 if not provided)
                if pos < len(args):
                    ccount = int(args[pos]); pos+=1
                else:
                    ccount = 0
                self.code.extend(_svarint(ccount))
                for _ in range(ccount):
                    self.code.append(254); self.code.extend(_svarint(self._str_idx(str(args[pos])))); pos+=1
            else:
                name_str = str(args[0])
                self.code.append(254); self.code.extend(_svarint(self._str_idx(name_str)))
        return op

    def to_blob(self) -> bytes:
        meta = {"strings": self.strtab}
        meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
        header = b"SRDG" + bytes([1]) + len(meta_bytes).to_bytes(4, "big")
        return header + meta_bytes + bytes(self.code)
