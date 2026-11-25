"""Check both compiler-generated portal guards without relaxing either path."""
import re


def preguard(disassembly, symbols):
    code = {}
    for line in disassembly.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+[0-9a-f]+\s+([a-z][a-z0-9_.]*)\s*(.*)", line)
        if match:
            address, op, operands = match.groups()
            code[int(address, 16)] = (op, operands)
    guards = {pc for pc, (op, args) in code.items() if op == "csrr" and "vstart" in args}
    assert len(guards) == 2, sorted(guards)
    functions = []
    for line in symbols.splitlines():
        match = re.match(r"([0-9a-f]+) ([0-9a-f]+) [tT] (\S+)", line)
        if match:
            start, size, name = match.groups()
            functions.append((int(start, 16), int(start, 16) + int(size, 16), name))
    start, end, name = next(f for f in functions if all(f[0] <= g < f[1] for g in guards))
    calls = {int(m[1], 16): m[2] for m in re.finditer(
        r"^\s*([0-9a-f]+): R_RISCV_CALL_PLT\s+(\S+)", disassembly, re.M)}
    pcs = sorted(pc for pc in code if start <= pc < end)
    edges, reverse = {}, {}
    for i, pc in enumerate(pcs):
        op, args = code[pc]
        targets = [pcs[i + 1]] if i + 1 < len(pcs) else []
        branch = re.search(r"(?:^|,)\s*([0-9a-f]+)\s+<", args)
        if op == "j":
            assert branch, (pc, args)
            targets = [int(branch[1], 16)]
        elif op.startswith("b") and branch:
            targets.append(int(branch[1], 16))
        elif op in ("ret", "jr", "unimp"):
            targets = []
        if pc in guards or calls.get(pc) in ("ggml_abort", "_Unwind_Resume", "__assert_fail"):
            targets = []
        edges[pc] = [p for p in targets if start <= p < end and p in code]
        for target in edges[pc]:
            reverse.setdefault(target, []).append(pc)

    def reach(seed, graph):
        todo, found = [seed], set()
        while todo:
            pc = todo.pop()
            if pc not in found:
                found.add(pc)
                todo.extend(graph.get(pc, []))
        return found

    reachable = reach(start, edges)
    assert guards <= reachable
    reports = []
    admission = set()
    for guard in sorted(guards):
        before = reachable & reach(guard, reverse)
        # LP64D permits callee-saved FP stores in the function prologue. These
        # do not use vector state, perform arithmetic, or change FCSR.
        fp_saves = {pc for pc in before if code[pc][0] == "fsd" and
                    re.fullmatch(r"fs(?:[0-9]|1[01]),\s*[0-9]+\(sp\)", code[pc][1])}
        bad = [(hex(pc), *code[pc]) for pc in sorted(before)
               if code[pc][0].startswith(("v", "f")) and code[pc][0] != "fence" and pc not in fp_saves]
        assert not bad, bad
        invoked = [{"pc": hex(pc), "symbol": calls[pc]} for pc in sorted(before) if pc in calls]
        admitted = {c["symbol"] for c in invoked} & {"ara_resident_linux_admit", "ara_resident_linux_open"}
        assert len(admitted) == 1, invoked
        assert not any("cxa_thread_atexit" in c["symbol"] or "thread_session" in c["symbol"] for c in invoked)
        admission |= admitted
        reports.append(dict(guard=hex(guard), instructions=len(before), admission=sorted(admitted), calls=invoked,
                            lp64d_prologue_fp_saves=[hex(pc) for pc in sorted(fp_saves)]))
    assert admission == {"ara_resident_linux_admit", "ara_resident_linux_open"}
    helpers = [f for f in functions if "tensor_span" in f[2]]
    assert helpers
    for lo, hi, helper in helpers:
        assert not any(op.startswith(("v", "f")) and op != "fence"
                       for pc, (op, _) in code.items() if lo <= pc < hi), helper
    return dict(function=name, guards=reports, scalar_helpers=[f[2] for f in helpers],
                scope="First-guard CFG paths and tensor_span; libc implementations are not certified")
