
from __future__ import annotations
from dataclasses import dataclass
from typing import List

KEYWORDS = {
    "let","mut","print","if","else","true","false",
    "fn","return","while","break","continue","for","in","capture","step"
}

@dataclass
class Tok:
    kind: str
    text: str
    start: int
    end: int

def lex(src: str) -> List[Tok]:
    i = 0
    out: List[Tok] = []
    while i < len(src):
        ch = src[i]
        if ch.isspace():
            i += 1; continue
        if ch.isalpha() or ch == "_":
            j = i+1
            while j < len(src) and (src[j].isalnum() or src[j] == "_"):
                j += 1
            t = src[i:j]
            kind = "KW" if t in KEYWORDS else "ID"
            out.append(Tok(kind, t, i, j)); i = j; continue
        if ch.isdigit():
            j = i+1
            while j < len(src) and src[j].isdigit():
                j += 1
            out.append(Tok("INT", src[i:j], i, j)); i = j; continue
        if i+2 < len(src) and src[i:i+3] == "..=":
            out.append(Tok("OP", "..=", i, i+3)); i += 3; continue
        if i+1 < len(src) and src[i:i+2] in {"==","!=",">=","<=",".."}:
            out.append(Tok("OP", src[i:i+2], i, i+2)); i += 2; continue
        if ch in "+-*/%(){}=<>!,;[]":
            out.append(Tok("OP", ch, i, i+1)); i += 1; continue
        if ch == '"':
            j = i+1
            while j < len(src) and src[j] != '"':
                if src[j] == "\\": j += 1
                j += 1
            j += 1
            out.append(Tok("STR", src[i:j], i, j)); i = j; continue
        if ch == "#":
            j = i
            while j < len(src) and src[j] != "\n":
                j += 1
            i = j; continue
        raise SyntaxError(f"Unknown char {ch!r} at {i}")
    out.append(Tok("EOF", "", len(src), len(src)))
    return out
