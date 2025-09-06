
from __future__ import annotations
from typing import List, Tuple
from .base12 import UCIO_REG
from .emitter import _load_blob
import json

def optimize(blob: bytes, strip_trace=True, strip_hooks=True) -> bytes:
    meta, code = _load_blob(blob)
    code = bytearray(code)

    def read_varint(buf, pos):
        shift=result=0
        last=0
        while True:
            b = buf[pos]; pos+=1
            last=b
            result |= ((b & 0x7F) << shift); shift += 7
            if b<128: break
        if (last & 0x40) and shift < 64:
            result |= - (1<<shift)
        return result, pos
    def write_varint(n: int):
        outb = bytearray()
        more=True
        while more:
            byte = n & 0x7F; n >>= 7
            sign_bit = (byte & 0x40) != 0
            if (n == 0 and not sign_bit) or (n == -1 and sign_bit):
                more = False
            else:
                byte |= 0x80
            outb.append(byte)
        return outb

    def is_strip(op):
        name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
        if name == "NOP": return True
        if strip_trace and name in {"TRACE_START","TRACE_MARK","TRACE_END"}: return True
        if strip_hooks and name in {"HOOK_PRE_RULE","HOOK_POST_RULE"}: return True
        return False

    # Pass 1: strip trivials and copy
    i = 0
    out = bytearray()
    while i < len(code):
        op = code[i]; i += 1
        if is_strip(op):
            # skip possible immediates
            if i < len(code) and code[i] == 254:
                i += 1
                while i < len(code):
                    b = code[i]; i += 1
                    if b < 128: break
            elif i < len(code) and (code[i] & 0x80 or code[i] < 128):
                while i < len(code):
                    b = code[i]; i += 1
                    if b < 128: break
            continue
        out.append(op)
        name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
        if name in {"FOR_HINT"}:
            for _ in range(4):
                v, i = read_varint(code, i); out.extend(write_varint(v))
        elif name in {"LITERAL_I64","SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END","JMP","JMP_IF_FALSE"}:
            v, i = read_varint(code, i); out.extend(write_varint(v))
        elif name in {"LITERAL_STR","BIND_CONST","BIND_MUT","LOAD","STORE","CALL","FN_LABEL"}:
            if i < len(code) and code[i] == 254:
                out.append(254); i += 1
                v, i = read_varint(code, i)
                out.extend(write_varint(v))
                if name == "CALL":
                    argc, i = read_varint(code, i); out.extend(write_varint(argc))
                if name == "FN_LABEL":
                    pc, i = read_varint(code, i); out.extend(write_varint(pc))
                    for _ in range(pc):
                        if code[i] == 254:
                            out.append(254); i += 1
                            pv, i = read_varint(code, i); out.extend(write_varint(pv))
                    cc, i = read_varint(code, i); out.extend(write_varint(cc))
                    for _ in range(cc):
                        if code[i] == 254:
                            out.append(254); i += 1
                            cv, i = read_varint(code, i); out.extend(write_varint(cv))
    code = out

    # Pass 2: fold arithmetic + compares
    stack: List[Tuple[bool,int]] = []
    i = 0
    out = bytearray()
    while i < len(code):
        op = code[i]; i += 1
        name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
        if name == "LITERAL_I64":
            val, i = read_varint(code, i)
            stack.append((True, val))
            out.append(op); out.extend(write_varint(val))
        elif name in {"ADD","SUB","MUL"} and len(stack) >= 2 and all(s[0] for s in stack[-2:]):
            b = stack.pop()[1]; a = stack.pop()[1]
            val = (a+b) if name=="ADD" else (a-b) if name=="SUB" else (a*b)
            stack.append((True, val))
            out.append(UCIO_REG.emit("LITERAL_I64")); out.extend(write_varint(val))
        elif name in {"CMP_GT","CMP_GE","CMP_LT","CMP_LE","CMP_EQ","CMP_NE"} and len(stack) >= 2 and all(s[0] for s in stack[-2:]):
            b = stack.pop()[1]; a = stack.pop()[1]
            if name == "CMP_GT": val = 1 if a>b else 0
            elif name == "CMP_GE": val = 1 if a>=b else 0
            elif name == "CMP_LT": val = 1 if a<b else 0
            elif name == "CMP_LE": val = 1 if a<=b else 0
            elif name == "CMP_EQ": val = 1 if a==b else 0
            else: val = 1 if a!=b else 0
            stack.append((True, val))
            out.append(UCIO_REG.emit("LITERAL_I64")); out.extend(write_varint(val))
        else:
            stack.clear()
            out.append(op)
            if name in {"FOR_HINT"}:
                for _ in range(4):
                    v, i = read_varint(code, i); out.extend(write_varint(v))
            elif name in {"LITERAL_STR","BIND_CONST","BIND_MUT","LOAD","STORE","CALL","FN_LABEL"}:
                if i < len(code) and code[i] == 254:
                    out.append(254); i += 1
                    v, i = read_varint(code, i); out.extend(write_varint(v))
                    if name == "CALL":
                        argc, i = read_varint(code, i); out.extend(write_varint(argc))
                    if name == "FN_LABEL":
                        pc, i = read_varint(code, i); out.extend(write_varint(pc))
                        for _ in range(pc):
                            if code[i] == 254:
                                out.append(254); i += 1
                                pv, i = read_varint(code, i); out.extend(write_varint(pv))
                        cc, i = read_varint(code, i); out.extend(write_varint(cc))
                        for _ in range(cc):
                            if code[i] == 254:
                                out.append(254); i += 1
                                cv, i = read_varint(code, i); out.extend(write_varint(cv))
            elif name in {"SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END","JMP","JMP_IF_FALSE"}:
                v, i = read_varint(code, i); out.extend(write_varint(v))

    meta_bytes = json.dumps({"strings": meta.get("strings", [])}, ensure_ascii=False).encode("utf-8")
    header = b"SRDG" + bytes([1]) + len(meta_bytes).to_bytes(4, "big")
    return header + meta_bytes + bytes(out)
