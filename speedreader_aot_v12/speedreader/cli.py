
from __future__ import annotations
import argparse, sys, json
from .parser import compile_to_bytes
from .optimizer import optimize
from .verifier import verify, VerifyError
from .emitter import load_dgm, _load_blob
from .base12 import UCIO_REG
from .vm import VM

def read_file(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()

def write_file(p, b):
    with open(p, "wb") as f:
        f.write(b)

def disasm(blob: bytes):
    meta, code = _load_blob(blob)
    strings = meta.get("strings", [])
    i = 0
    def read_varint():
        nonlocal i
        shift=result=0; last=0
        while True:
            b = code[i]; i+=1; last=b
            result |= ((b & 0x7F) << shift); shift += 7
            if b<128: break
        if (last & 0x40) and shift < 64:
            result |= - (1<<shift)
        return result
    out = []
    while i < len(code):
        op = code[i]; i += 1
        name = UCIO_REG[op].name if op in UCIO_REG.by_code else f"UNK_{op}"
        row = [name]
        if name in {"LITERAL_I64","SCOPE_ENTER","SCOPE_EXIT","RANGE_BEGIN","RANGE_END","JMP","JMP_IF_FALSE"}:
            row.append(str(read_varint()))
        elif name == "FOR_HINT":
            row.append(f"a={read_varint()}"); row.append(f"b={read_varint()}"); row.append(f"s={read_varint()}"); row.append(f"inc={read_varint()}")
        elif name in {"LITERAL_STR","BIND_CONST","BIND_MUT","LOAD","STORE","CALL","FN_LABEL"}:
            if i < len(code) and code[i] == 254:
                i += 1; sidx = read_varint(); sval = strings[sidx] if 0 <= sidx < len(strings) else f"<str#{sidx}>"
                row.append(sval)
                if name == "CALL":
                    row.append(f"argc={read_varint()}")
                if name == "FN_LABEL":
                    pc = read_varint(); row.append(f"params={pc}")
                    for _ in range(pc):
                        if i < len(code) and code[i] == 254:
                            i += 1; pidx = read_varint(); row.append(f"p:{strings[pidx]}")
                    cc = read_varint(); row.append(f"captures={cc}")
                    for _ in range(cc):
                        if i < len(code) and code[i] == 254:
                            i += 1; cidx = read_varint(); row.append(f"c:{strings[cidx]}")
        out.append(" ".join(row))
    return "\n".join(out)

def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile")
    c.add_argument("src")
    c.add_argument("--opt", action="store_true")
    c.add_argument("--verify", action="store_true")
    c.add_argument("--disasm", action="store_true")

    r = sub.add_parser("run")
    r.add_argument("src")
    r.add_argument("--opt", action="store_true")
    r.add_argument("--trace", action="store_true")
    r.add_argument("--fuel", type=int, default=10000)

    args = ap.parse_args(argv)

    if args.cmd == "compile":
        src = read_file(args.src)
        blob = compile_to_bytes(src)
        if args.opt:
            blob = optimize(blob)
        if args.verify:
            try:
                verify(blob, {"PRINT": 1_000_000, "MUTATE": 1_000_000, "LOOP_FUEL": 1_000_000})
            except VerifyError as e:
                print(f"[verify error] {e}", file=sys.stderr); sys.exit(2)
        if args.disasm:
            print(disasm(blob))
        else:
            sys.stdout.buffer.write(blob)
    elif args.cmd == "run":
        src = read_file(args.src)
        blob = compile_to_bytes(src)
        if args.opt:
            blob = optimize(blob)
        vm = VM(blob, trace=args.trace)
        trace = vm.run()
        if args.trace:
            print(json.dumps(trace, indent=2))

if __name__ == "__main__":
    main()
