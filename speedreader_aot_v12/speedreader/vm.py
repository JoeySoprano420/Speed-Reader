
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .emitter import load_dgm
from .base12 import UCIO_REG

class VMError(Exception): pass

def _is_box(v): return isinstance(v, list) and len(v) == 1

class VM:
    def __init__(self, blob: bytes, stdout=None, trace: bool=False):
        meta, code = load_dgm(blob)
        self.code = code
        self.strings = meta.get("strings", [])
        self.ip = 0
        self.stack: List[Any] = []
        self.env_stack: List[Dict[str, Any]] = [{}]
        self.mut_stack: List[Dict[str, bool]] = [{}]
        self.callstack: List[int] = []
        self.fn_meta = self._index_labels()
        self.out = stdout if stdout is not None else print
        self.trace_enabled = trace
        self.trace_log: List[Dict[str, Any]] = []

    @property
    def env(self) -> Dict[str,Any]:
        return self.env_stack[-1]

    @property
    def mut(self) -> Dict[str,bool]:
        return self.mut_stack[-1]

    def _index_labels(self):
        labels = {}
        i = 0
        def read_varint():
            nonlocal i
            shift=result=0; last=0
            while True:
                b = self.code[i]; i+=1; last=b
                result |= ((b & 0x7F) << shift); shift += 7
                if b<128: break
            if (last & 0x40) and shift < 64:
                result |= - (1<<shift)
            return result
        while i < len(self.code):
            op = self.code[i]; i += 1
            name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
            if name == "FN_LABEL":
                if self.code[i] != 254: raise VMError("FN_LABEL missing name marker")
                i += 1
                name_idx = read_varint()
                fname = self.strings[name_idx] if 0 <= name_idx < len(self.strings) else f"<str#{name_idx}>"
                param_count = read_varint()
                params = []
                for _ in range(param_count):
                    if self.code[i] != 254: raise VMError("FN_LABEL param missing marker")
                    i += 1; pidx = read_varint(); params.append(self.strings[pidx])
                capture_count = read_varint()
                captures = []
                for _ in range(capture_count):
                    if self.code[i] != 254: raise VMError("FN_LABEL capture missing marker")
                    i += 1; cidx = read_varint(); captures.append(self.strings[cidx])
                labels[fname] = {"ip": i, "params": params, "captures": captures}
            elif name in {"LITERAL_I64","SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END","JMP","JMP_IF_FALSE","FOR_HINT"}:
                _ = read_varint()
                if name == "FOR_HINT":
                    _ = read_varint(); _ = read_varint(); _ = read_varint()
            elif name in {"LITERAL_STR","BIND_CONST","BIND_MUT","LOAD","STORE","CALL"}:
                if i < len(self.code) and self.code[i] == 254:
                    i += 1; _ = read_varint()
                    if name == "CALL":
                        _ = read_varint()
        return labels

    def _read_svarint(self) -> int:
        shift = 0; result = 0; last = 0
        while True:
            b = self.code[self.ip]; self.ip += 1
            last = b; result |= ((b & 0x7F) << shift); shift += 7
            if b < 128: break
        if (last & 0x40) and shift < 64:
            result |= - (1 << shift)
        return result

    def _read_str(self) -> str:
        idx = self._read_svarint()
        if 0 <= idx < len(self.strings):
            return self.strings[idx]
        return f"<str#{idx}>"

    def _log(self, opname: str, pre_stack, pre_env):
        if not self.trace_enabled: return
        view_env = {k:(v[0] if _is_box(v) else v) for k,v in self.env.items()}
        self.trace_log.append({"ip": self.ip, "op": opname, "stack_before": list(pre_stack), "env": view_env, "stack_after": list(self.stack)})

    def _resolve_load(self, name: str):
        for env in reversed(self.env_stack):
            if name in env:
                v = env[name]; return v[0] if _is_box(v) else v
        raise VMError(f"Unknown variable {name}")

    def _resolve_store(self, name: str, val: Any):
        for env, mut in zip(reversed(self.env_stack), reversed(self.mut_stack)):
            if name in env:
                if not mut.get(name, False): raise VMError(f"Variable {name} is const")
                v = env[name]
                if _is_box(v): v[0] = val
                else: env[name] = val
                return
        raise VMError(f"Unknown variable {name}")

    def run(self) -> Optional[List[dict]]:
        while self.ip < len(self.code):
            op = self.code[self.ip]; self.ip += 1
            name = UCIO_REG[op].name if op in UCIO_REG.by_code else f"UNK_{op}"
            pre_stack = list(self.stack); pre_env = dict(self.env)
            if name == "HALT":
                self._log(name, pre_stack, pre_env); break
            elif name == "RET":
                self._log(name, pre_stack, pre_env)
                if not self.callstack: break
                self.env_stack.pop(); self.mut_stack.pop(); self.ip = self.callstack.pop(); continue
            elif name == "CALL":
                if self.code[self.ip] != 254: raise VMError("CALL missing name marker")
                self.ip += 1; fname = self._read_str(); argc = self._read_svarint()
                meta = self.fn_meta.get(fname)
                if meta is None: raise VMError(f"Unknown function {fname}")
                params = meta["params"]; caps = meta["captures"]
                if argc != len(params): raise VMError(f"Arg mismatch: expected {len(params)} got {argc}")
                frame = {}; mframe = {}
                for pname in reversed(params):
                    val = self.stack.pop(); frame[pname] = val; mframe[pname] = False
                # bind captures
                for cname in caps:
                    found = False
                    for env, mut in zip(reversed(self.env_stack), reversed(self.mut_stack)):
                        if cname in env:
                            v = env[cname]; frame[cname] = v; mframe[cname] = mut.get(cname, False); found = True; break
                    if not found: raise VMError(f"Capture '{cname}' not found")
                self.env_stack.append(frame); self.mut_stack.append(mframe)
                self.callstack.append(self.ip); self.ip = meta["ip"]; self._log(name, pre_stack, pre_env); continue
            elif name == "LITERAL_I64":
                self.stack.append(self._read_svarint())
            elif name == "LITERAL_STR":
                if self.code[self.ip] != 254: raise VMError("STR missing marker")
                self.ip += 1; self.stack.append(self._read_str())
            elif name == "BIND_CONST":
                if self.code[self.ip] != 254: raise VMError("BIND name missing")
                self.ip += 1; namev = self._read_str(); val = self.stack.pop(); self.env[namev] = val; self.mut[namev] = False
            elif name == "BIND_MUT":
                if self.code[self.ip] != 254: raise VMError("BIND name missing")
                self.ip += 1; namev = self._read_str(); val = self.stack.pop(); self.env[namev] = [val]; self.mut[namev] = True
            elif name == "LOAD":
                if self.code[self.ip] != 254: raise VMError("LOAD name missing")
                self.ip += 1; namev = self._read_str(); self.stack.append(self._resolve_load(namev))
            elif name == "STORE":
                if self.code[self.ip] != 254: raise VMError("STORE name missing")
                self.ip += 1; namev = self._read_str(); val = self.stack.pop(); self._resolve_store(namev, val)
            elif name == "PRINT":
                v = self.stack.pop(); self.out(v)
            elif name == "ADD":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(a+b)
            elif name == "SUB":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(a-b)
            elif name == "MUL":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(a*b)
            elif name == "DIV":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(a//b)
            elif name == "MOD":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(a%b)
            elif name == "CMP_GT":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(1 if a>b else 0)
            elif name == "CMP_GE":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(1 if a>=b else 0)
            elif name == "CMP_LT":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(1 if a<b else 0)
            elif name == "CMP_LE":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(1 if a<=b else 0)
            elif name == "CMP_EQ":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(1 if a==b else 0)
            elif name == "CMP_NE":
                b,a = self.stack.pop(), self.stack.pop(); self.stack.append(1 if a!=b else 0)
            elif name in {"SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END","TRACE_START","TRACE_MARK","TRACE_END","HOOK_PRE_RULE","HOOK_POST_RULE","FN_LABEL","NOP","FOR_HINT"}:
                if name in {"SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END"}:
                    _ = self._read_svarint()
                elif name == "FN_LABEL":
                    if self.code[self.ip] != 254: raise VMError("FN_LABEL inline read")
                    self.ip += 1; _ = self._read_svarint()
                    pc = self._read_svarint()
                    for _ in range(pc):
                        if self.code[self.ip] != 254: raise VMError("FN_LABEL param inline read")
                        self.ip += 1; _ = self._read_svarint()
                    cc = self._read_svarint()
                    for _ in range(cc):
                        if self.code[self.ip] != 254: raise VMError("FN_LABEL capture inline read")
                        self.ip += 1; _ = self._read_svarint()
                elif name == "FOR_HINT":
                    _ = self._read_svarint(); _ = self._read_svarint(); _ = self._read_svarint(); _ = self._read_svarint()
            elif name == "IF_BEGIN":
                cond = self.stack.pop()
                if not cond: self._skip_to_else_or_end()
            elif name == "IF_ELSE":
                self._skip_to_end()
            elif name == "IF_END":
                pass
            elif name == "LOOP_BEGIN":
                cond = self.stack.pop()
                if not cond: self._skip_to_loop_end()
            elif name == "LOOP_END":
                self._jump_back_to_loop_begin()
            elif name == "LOOP_CONTINUE":
                self._jump_back_to_loop_begin(consume=False)
            elif name == "LOOP_BREAK":
                self._skip_to_loop_end()
            elif name == "JMP":
                self.ip = self._read_svarint()
            elif name == "JMP_IF_FALSE":
                target = self._read_svarint(); cond = self.stack.pop()
                if not cond: self.ip = target
            else:
                raise VMError(f"Unsupported opcode {name}")
            self._log(name, pre_stack, pre_env)
        return self.trace_log if self.trace_enabled else None

    def _skip_to_else_or_end(self):
        depth = 1
        while self.ip < len(self.code):
            op = self.code[self.ip]; self.ip += 1
            name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
            if name == "IF_BEGIN": depth += 1
            elif name == "IF_END":
                depth -= 1
                if depth == 0: return
            elif name == "IF_ELSE" and depth == 1:
                return
            self._consume_if_immediate(name)

    def _skip_to_end(self):
        depth = 1
        while self.ip < len(self.code):
            op = self.code[self.ip]; self.ip += 1
            name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
            if name == "IF_BEGIN": depth += 1
            elif name == "IF_END":
                depth -= 1
                if depth == 0: return
            self._consume_if_immediate(name)

    def _skip_to_loop_end(self):
        depth = 1
        while self.ip < len(self.code):
            op = self.code[self.ip]; self.ip += 1
            name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
            if name == "LOOP_BEGIN": depth += 1
            elif name == "LOOP_END":
                depth -= 1
                if depth == 0: return
            self._consume_if_immediate(name)

    def _jump_back_to_loop_begin(self, consume=True):
        depth = 1; j = self.ip - 2
        while j >= 0:
            op = self.code[j]; j -= 1
            name = UCIO_REG[op].name if op in UCIO_REG.by_code else ""
            if name == "LOOP_END": depth += 1
            elif name == "LOOP_BEGIN":
                depth -= 1
                if depth == 0: self.ip = j+1; return
        raise VMError("Matching LOOP_BEGIN not found")

    def _consume_if_immediate(self, name: str):
        if name in {"SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END","JMP","JMP_IF_FALSE"}:
            _ = self._read_svarint()
        elif name in {"LITERAL_STR","BIND_CONST","BIND_MUT","LOAD","STORE","CALL","FN_LABEL"}:
            if self.code[self.ip] == 254:
                self.ip += 1; _ = self._read_svarint()
                if name == "CALL":
                    _ = self._read_svarint()
                elif name == "FN_LABEL":
                    pc = self._read_svarint()
                    for _ in range(pc):
                        if self.code[self.ip] == 254:
                            self.ip += 1; _ = self._read_svarint()
                    cc = self._read_svarint()
                    for _ in range(cc):
                        if self.code[self.ip] == 254:
                            self.ip += 1; _ = self._read_svarint()
