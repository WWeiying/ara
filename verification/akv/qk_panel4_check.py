"""Bounded interpretation of GNU disassembly, not an ISA/hardware simulator."""
import re
import struct

SINGLE = "akv_v2_compute_scores_f16_d128_gqa6"
PANEL = SINGLE + "_panel4"
ACC = [0, 2, 4, 6, 10, 12]


def instructions(disassembly, symbol):
    result = {}
    active = False
    for line in disassembly.splitlines():
        label = re.fullmatch(r"([0-9a-f]+) <([^>]+)>:", line.strip())
        if label:
            if active:
                break
            active = label[2] == symbol
            continue
        if not active:
            continue
        insn = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([.\w]+)\s*(.*?)\s*$", line)
        if insn:
            operands = insn[4].split("#", 1)[0].strip()
            result[int(insn[1], 16)] = (int(insn[2], 16), insn[3], operands)
    if not result:
        raise ValueError("missing instructions: " + symbol)
    return result


def run_matrix(code, tokens, stride, panel):
    gpr = {"zero": 0, "a0": 0x10000, "a1": 0x20000, "a2": tokens, "a3": stride}
    fpr, provenance, columns = {}, {}, {}
    vrf = bytearray(32 * 128)
    output = bytearray(b"\xa5" * (6 * 256 + 32))
    events, commands = [], []
    pcs = sorted(code)
    successor = dict(zip(pcs, pcs[1:]))
    pc, vl, sew, lmul, steps = pcs[0], 0, 0, 0, 0

    def value(x):
        return gpr[x] if x in gpr else int(x, 0)

    def query(h, d):
        return ((h * 7 + d * 3) % 13) - 6

    def key(t, d):
        return ((t * 5 + d * 11) % 17) - 8

    while True:
        steps += 1
        if steps > 20000 or pc not in code:
            raise ValueError("invalid/unbounded control flow")
        word, op, args = code[pc]
        fields = [v.strip() for v in args.split(",")]
        next_pc = successor.get(pc)
        if word & 0x7f == 0x5b:
            rd, rs1, rs2, funct3, funct7 = ((word >> 7) & 31, (word >> 15) & 31,
                                          (word >> 20) & 31, (word >> 12) & 7, word >> 25)
            width = 4 if panel else 1
            if (rs1, rs2, funct3, funct7) != (10, 0, 7, int(panel)) or (sew, lmul) != (16, 1):
                raise ValueError("custom encoding/configuration")
            dimension = gpr["a0"]
            if dimension % width or dimension + width > 128 or \
                    (panel and rd not in (16, 20)) or (not panel and rd not in (8, 9)):
                raise ValueError("column/group mapping")
            commands.append((dimension, rd))
            for column in range(width):
                reg = rd + column
                if reg in {r + offset for r in ACC for offset in (0, 1)}:
                    raise ValueError("panel overwrites accumulator")
                columns[reg] = dimension + column
                for t in range(64):
                    struct.pack_into("<e", vrf, reg * 128 + t * 2,
                                     key(t, dimension + column) if t < tokens else 0)
        elif op in ("mv", "li"):
            gpr[fields[0]] = value(fields[1])
        elif op in ("add", "addi"):
            gpr[fields[0]] = value(fields[1]) + value(fields[2])
        elif op == "vsetvli":
            if fields[0] != "zero" or fields[4:] != ["ta", "ma"]:
                raise ValueError("vset contract")
            sew, lmul = int(fields[2][1:]), int(fields[3][1:])
            if (sew, lmul) not in ((32, 2), (16, 1)):
                raise ValueError("unsupported vector geometry")
            vl = min(value(fields[1]), 1024 * lmul // sew)
            if vl != tokens:
                raise ValueError("truncated tail")
        elif op == "vmv.v.i":
            reg = int(fields[0][1:])
            if reg not in ACC or fields[1] != "0" or (sew, lmul) != (32, 2):
                raise ValueError("accumulator initialization")
            vrf[reg * 128:reg * 128 + vl * 4] = bytes(vl * 4)
        elif op == "flh":
            match = re.fullmatch(r"(-?\d+)\((\w+)\)", fields[1])
            if not match:
                raise ValueError("query addressing")
            address = value(match[2]) + int(match[1]) - 0x10000
            h, offset = divmod(address, stride)
            d = offset // 2
            if h not in range(6) or offset % 2 or d not in range(128):
                raise ValueError("query range/stride")
            fpr[fields[0]] = query(h, d)
            provenance[fields[0]] = (h, d)
        elif op == "vfwmacc.vf":
            dest, source = int(fields[0][1:]), int(fields[2][1:])
            h, d = provenance[fields[1]]
            if dest != ACC[h] or columns.get(source) != d or (sew, lmul) != (16, 1):
                raise ValueError("FMA head/dimension/register mismatch")
            events.append((d, h))
            for t in range(vl):
                acc = struct.unpack_from("<f", vrf, dest * 128 + t * 4)[0]
                k = struct.unpack_from("<e", vrf, source * 128 + t * 2)[0]
                # This matrix has small integer products/sums, exactly representable
                # in F16/F32. No claim about exceptional FP rounding or FCSR.
                struct.pack_into("<f", vrf, dest * 128 + t * 4, acc + fpr[fields[1]] * k)
        elif op == "vse32.v":
            reg = int(fields[0][1:])
            address = value(fields[1].strip("()")) - 0x20000
            if reg not in ACC or address != ACC.index(reg) * 256 or (sew, lmul) != (32, 2):
                raise ValueError("score layout")
            output[address:address + vl * 4] = vrf[reg * 128:reg * 128 + vl * 4]
        elif op == "bltu":
            if value(fields[0]) < value(fields[1]):
                next_pc = int(fields[2].split()[0], 16)
        elif op == "ret":
            break
        else:
            raise ValueError(f"unexpected instruction {op} {args}")
        pc = next_pc

    if events != [(d, h) for d in range(128) for h in range(6)]:
        raise ValueError("FMA order/count")
    expected_commands = [(d, (16 if (d // 4) % 2 == 0 else 20)) for d in range(0, 128, 4)] \
        if panel else [(d, 8 + d % 2) for d in range(128)]
    if commands != expected_commands:
        raise ValueError("command count/order")
    expected = bytearray(b"\xa5" * len(output))
    for h in range(6):
        for t in range(tokens):
            result = sum(query(h, d) * key(t, d) for d in range(128))
            struct.pack_into("<f", expected, h * 256 + t * 4, result)
    if output != expected:
        raise ValueError("independent matrix oracle or tail canary")
    return bytes(output)


def check(disassembly):
    single, panel = instructions(disassembly, SINGLE), instructions(disassembly, PANEL)
    cases = 0
    for tokens in range(1, 65):
        for stride in (256, 320, 512, 768):
            if run_matrix(single, tokens, stride, False) != run_matrix(panel, tokens, stride, True):
                raise ValueError("singles/panel matrix mismatch")
            cases += 1
    # Checker must catch wrong rd, operand mapping, query increments and stores.
    mutations = []
    for pc, (word, op, args) in panel.items():
        bad = dict(panel)
        if word & 0x7f == 0x5b:
            bad[pc] = ((word & ~(31 << 7)) | (8 << 7), op, args)
            mutations.append(bad)
            break
    for target, old, new in (("vfwmacc.vf", "v0,", "v2,"),
                             ("add", "a4,a4,2", "a4,a4,4"),
                             ("vse32.v", "v0,", "v2,")):
        for pc, (word, op, args) in panel.items():
            if op in (target, "addi" if target == "add" else target) and old in args:
                bad = dict(panel)
                bad[pc] = (word, op, args.replace(old, new, 1))
                mutations.append(bad)
                break
    if len(mutations) != 4:
        raise ValueError("mutation target not found")
    for bad in mutations:
        try:
            run_matrix(bad, 17, 320, True)
        except ValueError:
            pass
        else:
            raise ValueError("checker accepted bad mapping")
    return {"matrix_cases": cases, "checker_mutations": len(mutations),
            "commands_per_tile": {"singles": 128, "panel4": 32},
            "widening_fmas_per_tile": 768}
