
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from .lexer import Tok, lex
from .ir import IR
from .lineage import Lineage
from .base12 import UCIO_REG
from .grammar import FIRST_TABLE, HOOKS

@dataclass
class Scope:
    id: int

class Parser:
    _scope_id = 0
    def __init__(self, src: str, hooks: Optional[object]=None):
        self.src = src
        self.toks: List[Tok] = lex(src)
        self.i = 0
        self.ir = IR()
        self.lineage = Lineage()
        self.scope_stack: List[Scope] = []
        self.hooks = hooks
        self.fn_defs: List[str] = []

    def la(self) -> Tok: return self.toks[self.i]
    def la2(self) -> Tok: return self.toks[self.i+1]

    def consume(self, kind: Optional[str]=None, text: Optional[str]=None) -> Tok:
        t = self.la()
        if kind and t.kind != kind: raise SyntaxError(f"Expected {kind} got {t.kind} at {t.start}")
        if text and t.text != text: raise SyntaxError(f"Expected {text} got {t.text} at {t.start}")
        self.i += 1; return t

    def run_hook(self, name: str, *args):
        fn = getattr(self.hooks, name, None) if self.hooks else None
        if callable(fn): fn(self, *args)

    def parse(self) -> IR:
        self.ir.emit("TRACE_START")
        self.program()
        self.ir.emit("TRACE_END")
        self.ir.emit("HALT")
        return self.ir

    def program(self):
        self._rule_enter("program")
        while self.la().kind != "EOF":
            if self.la().kind == "KW" and self.la().text == "fn":
                self.fn_decl()
            else:
                self.stmt()
        self._rule_exit("program")

    def fn_decl(self):
        self.consume("KW","fn")
        name = self.consume("ID").text
        params = []
        self.consume("OP","(")
        if not (self.la().kind == "OP" and self.la().text == ")"):
            params.append(self.consume("ID").text)
            while self.la().kind == "OP" and self.la().text == ",":
                self.consume("OP",","); params.append(self.consume("ID").text)
        self.consume("OP",")")
        captures = []
        if self.la().kind == "KW" and self.la().text == "capture":
            self.consume("KW","capture"); self.consume("OP","[")
            if not (self.la().kind == "OP" and self.la().text == "]"):
                captures.append(self.consume("ID").text)
                while self.la().kind == "OP" and self.la().text == ",":
                    self.consume("OP",","); captures.append(self.consume("ID").text)
            self.consume("OP","]")
        self.consume("OP","{")
        self.ir.emit("FN_LABEL", name, len(params), *params, len(captures), *captures)
        self.scope_enter()
        while not (self.la().kind == "OP" and self.la().text == "}"):
            self.stmt()
        self.consume("OP","}")
        self.scope_exit()
        self.ir.emit("RET")

    def stmt(self):
        self._rule_enter("stmt")
        t = self.la()
        if t.kind == "KW" and t.text == "let":
            self.consume("KW","let")
            mut = False
            if self.la().kind == "KW" and self.la().text == "mut":
                self.consume("KW","mut"); mut = True
            name = self.consume("ID").text
            self.consume("OP","="); self.expr()
            self.ir.emit("BIND_MUT" if mut else "BIND_CONST", name)
        elif t.kind == "KW" and t.text == "print":
            self.consume("KW","print"); self.expr(); self.ir.emit("PRINT")
        elif t.kind == "KW" and t.text == "return":
            self.consume("KW","return")
            if not (self.la().kind == "OP" and self.la().text == "}"):
                self.expr()
            self.ir.emit("RET")
        elif t.kind == "KW" and t.text == "break":
            self.consume("KW","break"); self.ir.emit("LOOP_BREAK")
        elif t.kind == "KW" and t.text == "continue":
            self.consume("KW","continue"); self.ir.emit("LOOP_CONTINUE")
        elif t.kind == "KW" and t.text == "if":
            self.consume("KW","if"); self.expr(); self.ir.emit("IF_BEGIN")
            self.consume("OP","{"); self.scope_enter()
            while not (self.la().kind == "OP" and self.la().text == "}"):
                self.stmt()
            self.consume("OP","}")
            if self.la().kind == "KW" and self.la().text == "else":
                self.ir.emit("IF_ELSE")
                self.consume("KW","else"); self.consume("OP","{"); self.scope_enter()
                while not (self.la().kind == "OP" and self.la().text == "}"):
                    self.stmt()
                self.consume("OP","}"); self.scope_exit()
            self.ir.emit("IF_END"); self.scope_exit()
        elif t.kind == "KW" and t.text == "while":
            self.consume("KW","while"); self.expr(); self.ir.emit("LOOP_BEGIN")
            self.consume("OP","{"); self.scope_enter()
            while not (self.la().kind == "OP" and self.la().text == "}"):
                self.stmt()
            self.consume("OP","}"); self.scope_exit(); self.ir.emit("LOOP_END")
        elif t.kind == "KW" and t.text == "for":
            self.consume("KW","for"); self.consume("OP","(")
            if self.la().kind == "ID" and self.la2().kind == "KW" and self.la2().text == "in":
                var = self.consume("ID").text; self.consume("KW","in")
                a_tok = self.la(); self.expr()
                inclusive = False
                if self.la().kind == "OP" and self.la().text == "..=":
                    self.consume("OP","..="); inclusive = True
                else:
                    self.consume("OP","..")
                b_tok = self.la(); self.expr()
                step_expr_present = False; s_tok = None
                if self.la().kind == "OP" and self.la().text == ";":
                    self.consume("OP",";"); self.consume("KW","step"); s_tok = self.la(); self.expr(); step_expr_present = True
                # bind start->var, end->hidden
                self.ir.emit("BIND_MUT", var)
                end_marker = f"__for_end_{var}"
                self.ir.emit("BIND_CONST", end_marker)
                # FOR_HINT if literals
                a_is_int = a_tok.kind == "INT"; b_is_int = b_tok.kind == "INT"; s_is_int = (not step_expr_present) or (s_tok.kind == "INT")
                if a_is_int and b_is_int and s_is_int:
                    aval = int(a_tok.text); bval = int(b_tok.text); sval = int(s_tok.text) if step_expr_present else 1
                    self.ir.emit("FOR_HINT", aval, bval, sval, 1 if inclusive else 0)
                # cond
                self.ir.emit("LOAD", var); self.ir.emit("LOAD", end_marker)
                if not step_expr_present or (s_is_int and int(s_tok.text) >= 0):
                    self.ir.emit("CMP_LE" if inclusive else "CMP_LT")
                else:
                    self.ir.emit("CMP_GE" if inclusive else "CMP_GT")
                self.ir.emit("LOOP_BEGIN")
                self.consume("OP",")")
                self.consume("OP","{"); self.scope_enter()
                while not (self.la().kind == "OP" and self.la().text == "}"):
                    self.stmt()
                self.consume("OP","}"); self.scope_exit()
                # step
                self.ir.emit("LOAD", var)
                if step_expr_present:
                    if s_is_int: self.ir.emit("LITERAL_I64", int(s_tok.text))
                    else: self.ir.emit("LITERAL_I64", 1)
                else:
                    self.ir.emit("LITERAL_I64", 1)
                self.ir.emit("ADD"); self.ir.emit("STORE", var)
                self.ir.emit("LOOP_END")
            else:
                # classic
                if not (self.la().kind == "OP" and self.la().text == ";"):
                    self.stmt_simple()
                self.consume("OP",";")
                self.expr(); self.ir.emit("LOOP_BEGIN")
                self.consume("OP",";")
                step_start = len(self.ir.code); self.stmt_simple()
                step_ir = self.ir.code[step_start:]; del self.ir.code[step_start:]
                self.consume("OP",")")
                self.consume("OP","{"); self.scope_enter()
                while not (self.la().kind == "OP" and self.la().text == "}"):
                    self.stmt()
                self.consume("OP","}"); self.scope_exit()
                self.ir.code.extend(step_ir); self.ir.emit("LOOP_END")
        elif t.kind == "ID":
            if self.la2().kind == "OP" and self.la2().text == "(":
                name = self.consume("ID").text; self.consume("OP","(")
                args = []
                if not (self.la().kind == "OP" and self.la().text == ")"):
                    args.append(self.expr_value())
                    while self.la().kind == "OP" and self.la().text == ",":
                        self.consume("OP",","); args.append(self.expr_value())
                self.consume("OP",")"); self.ir.emit("CALL", name, len(args))
            else:
                name = self.consume("ID").text; self.consume("OP","="); self.expr(); self.ir.emit("STORE", name)
        else:
            raise SyntaxError(f"Invalid statement at {t.start}")
        self._rule_exit("stmt")

    def stmt_simple(self):
        t = self.la()
        if t.kind == "KW" and t.text == "let":
            self.consume("KW","let")
            mut = False
            if self.la().kind == "KW" and self.la().text == "mut":
                self.consume("KW","mut"); mut = True
            name = self.consume("ID").text; self.consume("OP","="); self.expr()
            self.ir.emit("BIND_MUT" if mut else "BIND_CONST", name)
        elif t.kind == "ID" and self.la2().kind == "OP" and self.la2().text == "(":
            name = self.consume("ID").text; self.consume("OP","(")
            args = []
            if not (self.la().kind == "OP" and self.la().text == ")"):
                args.append(self.expr_value())
                while self.la().kind == "OP" and self.la().text == ",":
                    self.consume("OP",","); args.append(self.expr_value())
            self.consume("OP",")"); self.ir.emit("CALL", name, len(args))
        else:
            name = self.consume("ID").text; self.consume("OP","="); self.expr(); self.ir.emit("STORE", name)

    def expr(self):
        self._rule_enter("expr")
        self.term()
        if self.la().kind == "OP" and self.la().text in (">",">=","<","<=","==","!="):
            op = self.consume("OP").text; self.term(); self._cmp_emit(op)
        self._rule_exit("expr")

    def expr_value(self): self.expr(); return True

    def term(self):
        t = self.la()
        if t.kind == "INT":
            self.consume("INT"); self.ir.emit("LITERAL_I64", int(t.text), src_span=(t.start,t.end))
        elif t.kind == "STR":
            self.consume("STR"); s = t.text[1:-1]; self.ir.emit("LITERAL_STR", s, src_span=(t.start,t.end))
        elif t.kind == "ID":
            self.consume("ID"); self.ir.emit("LOAD", t.text, src_span=(t.start,t.end))
        elif t.kind == "OP" and t.text == "(":
            self.consume("OP","("); self.expr(); self.consume("OP",")")
        else:
            raise SyntaxError(f"Unexpected token {t.kind} {t.text!r} at {t.start}")

    def _cmp_emit(self, op: str):
        m = {">":"CMP_GT", ">=":"CMP_GE", "<":"CMP_LT", "<=":"CMP_LE", "==":"CMP_EQ", "!=":"CMP_NE"}[op]
        self.ir.emit(m)

    def scope_enter(self):
        Parser._scope_id += 1; sid = Parser._scope_id
        self.scope_stack.append(Scope(sid))
        self.ir.emit("SCOPE_ENTER", sid); self.ir.emit("RANGE_BEGIN", sid)

    def scope_exit(self):
        if not self.scope_stack: raise RuntimeError("scope underflow")
        sid = self.scope_stack.pop().id
        self.ir.emit("RANGE_END", sid); self.ir.emit("SCOPE_EXIT", sid)

    def _rule_enter(self, name: str):
        start = self.la().start
        pre, _ = HOOKS.get(name, (None,None))
        if pre: self.ir.emit("HOOK_PRE_RULE"); self.run_hook(pre, name)
        self.ir.emit("TRACE_MARK", name, start)

    def _rule_exit(self, name: str):
        _, post = HOOKS.get(name, (None,None))
        if post: self.ir.emit("HOOK_POST_RULE"); self.run_hook(post, name)

def compile_to_bytes(src: str, hooks=None) -> bytes:
    p = Parser(src, hooks=hooks)
    ir = p.parse()
    return ir.to_blob()
