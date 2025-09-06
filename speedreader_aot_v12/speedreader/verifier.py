
from __future__ import annotations
from typing import Dict, Tuple, List
from .emitter import _load_blob
from .base12 import UCIO_REG

class VerifyError(Exception): pass

def verify(blob: bytes, budgets: Dict[str,int] = None) -> None:
    budgets = budgets or {"PRINT": 1000, "MUTATE": 1000, "LOOP_FUEL": 10000}
    meta, code = _load_blob(blob)

    scope_depth = range_depth = if_depth = loop_depth = 0
    prints = mutations = 0
    loops_unknown = 0

    i = 0
    def read_varint():
        nonlocal i
        shift=result=0
        last=0
        while True:
            b = code[i]; i+=1
            last=b
            result |= ((b & 0x7F) << shift); shift += 7
            if b<128: break
        if (last & 0x40) and shift < 64:
            result |= - (1<<shift)
        return result

    stack: List[Tuple[bool,int]] = []

    while i < len(code):
        op = code[i]; i += 1
        name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
        if name == "LITERAL_I64":
            v = read_varint(); stack.append((True, v))
        elif name == "FOR_HINT":
            a = read_varint(); b = read_varint(); s = read_varint(); inc = read_varint()
            if s == 0:
                raise VerifyError("FOR_HINT step cannot be zero")
            if inc not in (0,1):
                raise VerifyError("FOR_HINT inclusive must be 0 or 1")
            if s > 0:
                bound = b + (1 if inc==1 else 0)
                iters = max(0, (bound - a + s - 1)//s)
            else:
                bound = b - (1 if inc==1 else 0)
                iters = max(0, (a - bound + (-s) - 1)//(-s))
            if iters > budgets.get("LOOP_FUEL", 1e9):
                raise VerifyError(f"Range-for exceeds LOOP_FUEL: {iters} > {budgets['LOOP_FUEL']}")
        elif name == "LITERAL_STR":
            if code[i] != 254: raise VerifyError("STR missing marker")
            i += 1; _ = read_varint(); stack.append((False,0))
        elif name in {"ADD","SUB","MUL"} and len(stack) >= 2 and all(s[0] for s in stack[-2:]):
            b = stack.pop()[1]; a = stack.pop()[1]
            val = (a+b) if name=="ADD" else (a-b) if name=="SUB" else (a*b)
            stack.append((True, val))
        elif name in {"CMP_GT","CMP_GE","CMP_LT","CMP_LE","CMP_EQ","CMP_NE"} and len(stack) >= 2 and all(s[0] for s in stack[-2:]):
            b = stack.pop()[1]; a = stack.pop()[1]
            if name == "CMP_GT": val = 1 if a>b else 0
            elif name == "CMP_GE": val = 1 if a>=b else 0
            elif name == "CMP_LT": val = 1 if a<b else 0
            elif name == "CMP_LE": val = 1 if a<=b else 0
            elif name == "CMP_EQ": val = 1 if a==b else 0
            else: val = 1 if a!=b else 0
            stack.append((True, val))
        elif name in {"LOAD","STORE","BIND_CONST","BIND_MUT"}:
            if name == "LOAD":
                if i < len(code) and code[i] == 254: i += 1; _ = read_varint()
                stack.append((False,0))
            else:
                if i < len(code) and code[i] == 254: i += 1; _ = read_varint()
                if name == "STORE":
                    if not stack: raise VerifyError("STORE with empty stack")
                    stack.pop()
                if name == "BIND_MUT": mutations += 1
        elif name == "PRINT":
            prints += 1
            if stack: stack.pop()
        elif name == "IF_BEGIN":
            cond = stack.pop() if stack else (False,0); if_depth += 1
        elif name == "IF_ELSE":
            pass
        elif name == "IF_END":
            if_depth -= 1
        elif name == "LOOP_BEGIN":
            loop_depth += 1
            cond = stack.pop() if stack else (False,0)
            if not cond[0]:
                loops_unknown += 1
        elif name == "LOOP_END":
            loop_depth -= 1
        elif name in {"SCOPE_ENTER"}:
            scope_depth += 1; _ = read_varint()
        elif name in {"SCOPE_EXIT"}:
            scope_depth -= 1; _ = read_varint()
        elif name in {"RANGE_BEGIN"}:
            range_depth += 1; _ = read_varint()
        elif name in {"RANGE_END"}:
            range_depth -= 1; _ = read_varint()
        elif name in {"JMP","JMP_IF_FALSE"}:
            _ = read_varint()
        elif name == "FN_LABEL":
            if i < len(code) and code[i] == 254:
                i += 1; _ = read_varint()   # name idx
                pc = read_varint()         # param count
                for _ in range(pc):
                    if code[i] == 254: i += 1; _ = read_varint()
                cc = read_varint()         # capture count
                if cc > 0 and scope_depth > 1:
                    raise VerifyError("Capturing non-global variables in a non-global function is disallowed")
                for _ in range(cc):
                    if code[i] == 254: i += 1; _ = read_varint()
        elif name == "CALL":
            if i < len(code) and code[i] == 254:
                i += 1; _ = read_varint(); _ = read_varint()
        else:
            pass

        if scope_depth < 0 or range_depth < 0 or if_depth < 0 or loop_depth < 0:
            raise VerifyError("Structural underflow detected")

    if if_depth or loop_depth or scope_depth or range_depth:
        raise VerifyError("Unbalanced structures detected")
    if prints > budgets.get("PRINT", 1e9):
        raise VerifyError(f"PRINT budget exceeded: {prints} > {budgets['PRINT']}")
    if mutations > budgets.get("MUTATE", 1e9):
        raise VerifyError(f"Mutation budget exceeded: {mutations} > {budgets['MUTATE']}")
    if loops_unknown > 0 and budgets.get("LOOP_FUEL", 0) <= 0:
        raise VerifyError(f"Loop termination requires fuel bound; set LOOP_FUEL >= {loops_unknown}")
