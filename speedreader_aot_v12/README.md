
# SpeedReader AOT Virtual Mapping (v1.2)

- Deterministic LL(1) front-end to UCIO (dodecagram base‑12) opcodes
- Optimizer (peephole + const-fold + compare-fold)
- Verifier with budgets and `FOR_HINT` loop proofs
- VM with frames, shadowing, upvalues via boxed mutables, closures
- CLI to compile, optimize, verify, disassemble, and run

## Quickstart
```bash
python3 cli.py compile examples/closures_range.sr --opt --verify --disasm
python3 cli.py run examples/closures_range.sr --trace
```

## Grammar Notes
- Functions: `fn name(a,b) capture[x,y] { ... }`
- Loops: `while cond {}`, `for (init; cond; step) {}`, `for (x in a..b; step s) {}` and inclusive `..=`.
- `print expr` writes top of stack to stdout.
