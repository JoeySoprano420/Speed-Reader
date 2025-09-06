
from __future__ import annotations

DIGITS = "0123456789AB"

def b12(n: int, width: int=2) -> str:
    if n < 0:
        raise ValueError("b12 only supports non-negative integers")
    if n == 0:
        s = "0"
    else:
        s = ""
        x = n
        while x:
            x, r = divmod(x, 12)
            s = DIGITS[r] + s
    return s.rjust(width, "0")

class Opcode:
    __slots__ = ("name", "code")
    def __init__(self, name: str, code: int):
        self.name = name; self.code = code
    def __repr__(self) -> str:
        return f"Opcode({self.name}={self.code})"

class UCIO:
    def __init__(self):
        self.by_name = {}
        self.by_code = {}
    def add(self, name: str, code: int):
        if name in self.by_name or code in self.by_code:
            raise ValueError("Duplicate opcode")
        oc = Opcode(name, code)
        self.by_name[name] = oc; self.by_code[code] = oc
        return oc
    def emit(self, name: str) -> int:
        return self.by_name[name].code
    def __getitem__(self, key):
        return self.by_name[key] if isinstance(key, str) else self.by_code[key]
    @property
    def names(self):
        return list(self.by_name.keys())

UCIO_REG = UCIO()

# Core
UCIO_REG.add("NOP", 0)
UCIO_REG.add("SCOPE_ENTER", 1)
UCIO_REG.add("SCOPE_EXIT", 2)
UCIO_REG.add("BIND_CONST", 3)
UCIO_REG.add("BIND_MUT", 4)
UCIO_REG.add("LOAD", 5)
UCIO_REG.add("STORE", 6)
UCIO_REG.add("LITERAL_I64", 7)
UCIO_REG.add("LITERAL_STR", 8)
UCIO_REG.add("PRINT", 9)
UCIO_REG.add("IF_BEGIN", 10)
UCIO_REG.add("IF_ELSE", 11)
UCIO_REG.add("IF_END", 12)
UCIO_REG.add("CMP_GT", 13)
UCIO_REG.add("CMP_GE", 14)
UCIO_REG.add("CMP_LT", 15)
UCIO_REG.add("CMP_LE", 16)
UCIO_REG.add("CMP_EQ", 17)
UCIO_REG.add("CMP_NE", 18)
UCIO_REG.add("JMP_IF_FALSE", 19)
UCIO_REG.add("JMP", 20)
UCIO_REG.add("ADD", 21)
UCIO_REG.add("SUB", 22)
UCIO_REG.add("MUL", 23)
UCIO_REG.add("DIV", 24)
UCIO_REG.add("MOD", 25)
UCIO_REG.add("HALT", 26)

# Hooks & ranges
UCIO_REG.add("HOOK_PRE_RULE", 27)
UCIO_REG.add("HOOK_POST_RULE", 28)
UCIO_REG.add("RANGE_BEGIN", 29)
UCIO_REG.add("RANGE_END", 30)

# Tracing
UCIO_REG.add("TRACE_START", 31)
UCIO_REG.add("TRACE_MARK", 32)
UCIO_REG.add("TRACE_END", 33)

# Functions & Loops
UCIO_REG.add("CALL", 34)          # args: function name (str), argc (int)
UCIO_REG.add("RET", 35)
UCIO_REG.add("FN_LABEL", 36)      # name (str), param_count (int), params..., capture_count, captures...
UCIO_REG.add("LOOP_BEGIN", 37)    # expects cond on stack; skip body if false
UCIO_REG.add("LOOP_END", 38)      # jump back to matching LOOP_BEGIN
UCIO_REG.add("LOOP_CONTINUE", 39)
UCIO_REG.add("LOOP_BREAK", 40)

# Hints for verifier (ignored by VM)
UCIO_REG.add("FOR_HINT", 41)      # a(int), b(int), step(int), inclusive(0/1)

# Fill table to 144 slots to keep codes stable
for i in range(42, 144):
    UCIO_REG.add(f"RES_{i}", i)
