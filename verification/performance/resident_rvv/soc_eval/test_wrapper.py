"""Source and scalar-control-flow host tests only: no compile, EDA, or RVV execution."""
import hashlib
from pathlib import Path
import re
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PINNED_INPUTS = {
    "verification/performance/resident_rvv/pv_prepare/prepare.S":
        "8d039dd90da0b00497429be90483d0ed9f3576c1400f458889e9e8cd380968be",
    "verification/performance/resident_rvv/rotation/main.c":
        "5187bd4757bf51a6779b2b320a6c6efa10efcb5df52c6344cf6072b4725d90ce",
    "verification/performance/resident_rvv/rotation/pv_rotation.S":
        "42cae9574432604db17e5ef9a30f7b074dbd009c3cc25594e741707a564c863f",
    "verification/performance/akv_pair_eval/main.c":
        "2831a828d0389d387cb86eed34f14b592ff8d0b0d32e79f48767dcb1e8cc5da4",
}


def instructions(source):
    code, labels = [], {}
    for raw in source.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line.endswith(":"):
            labels[line[:-1]] = len(code)
        elif not line.startswith(".") or line.startswith(".word"):
            op, _, operands = line.partition(" ")
            code.append((op, [part.strip() for part in operands.split(",") if part.strip()]))
    return code, labels


def wrapper_path(source, selected, tokens=9, dimension=96):
    """Interpret scalar glue; preparation and the custom op are explicit stubs."""
    code, labels = instructions(source)
    initial = dict(a0=0x1000, a1=0x2000, a2=0x3000, a3=tokens, a4=dimension,
                   a5=0x55, ra=0x12345678, sp=0x9000)
    regs, memory, events = dict(initial), {0x4000: selected}, []
    pc, vl = 0, None

    def get(reg):
        return 0 if reg == "zero" else regs[reg]

    def address(operand):
        match = re.fullmatch(r"(-?\d*)\((\w+)\)", operand)
        if match is None:
            raise ValueError("Unsupported address: " + operand)
        return int(match[1] or "0") + get(match[2])

    for _ in range(100):
        op, args = code[pc]
        pc += 1
        if op == "la":
            if args[1] != "resident_pv_rotation_selected":
                raise ValueError("Wrong selection symbol")
            regs[args[0]] = 0x4000
        elif op in ("lw", "ld"):
            regs[args[0]] = memory[address(args[1])]
        elif op == "sd":
            memory[address(args[1])] = get(args[0])
        elif op == "li":
            regs[args[0]] = int(args[1], 0)
        elif op == "addi":
            regs[args[0]] = get(args[1]) + int(args[2], 0)
        elif op == "ori":
            regs[args[0]] = get(args[1]) | int(args[2], 0)
        elif op == "bnez":
            if get(args[0]) != 0:
                pc = labels[args[1]]
        elif op == "beq":
            if get(args[0]) == get(args[1]):
                pc = labels[args[2]]
        elif op == "j":
            pc = labels[args[0]]
        elif op == "tail":
            events.append(("tail", args[0]))
            return initial, regs, events
        elif op == "call":
            if args != ["resident_pv_prepare"] or get("sp") % 16:
                raise ValueError("Wrong helper or unaligned call stack")
            events.append(("prepare", tuple(get("a" + str(i)) for i in range(6))))
            regs.update(ra=0xBADCA11, t0=0xBAD0, t1=0xBAD1)
        elif op == ".word":
            events.append(("custom", int(args[0], 0), get("a0")))
        elif op == "vsetvli":
            if args[0] != "zero" or args[2:] != ["e16", "m2", "ta", "ma"]:
                raise ValueError("Wrong result-store geometry")
            vl = min(get(args[1]), 128)
        elif op == "vse16.v":
            events.append(("store", args[0], address(args[1]), 2 * vl))
        elif op == "ret":
            return initial, regs, events
        else:
            raise ValueError("Unsupported wrapper instruction: " + op)
    raise ValueError("Wrapper control flow did not terminate")


def candidate_contract(source, tokens, dimension):
    initial, regs, events = wrapper_path(source, 1, tokens, dimension)
    for reg in ("ra", "sp", "a1", "a4"):
        if regs[reg] != initial[reg]:
            raise ValueError("Unrestored " + reg)
    control = (tokens - 1) | 64 | ({64: 0, 128: 1, 96: 2}[dimension] << 7)
    expected = [("prepare", tuple(initial["a" + str(i)] for i in range(5)) + (2,)),
                ("custom", 0x0485705B, control),
                ("store", "v0", initial["a1"], 2 * dimension),
                ("store", "v2", initial["a1"] + 512, 2 * dimension)]
    if events != expected:
        raise ValueError("Wrong preparation/control/store order or geometry")


class SocEvaluationWrapper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asm = (HERE / "pv.S").read_text()
        cls.main = (HERE / "main.c").read_text()
        cls.smoke = (HERE / "smoke.c").read_text()

    def test_sealed_dependencies_are_unchanged(self):
        for path, digest in PINNED_INPUTS.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_inherited_abba_and_strong_control_link_contract(self):
        self.assertIn("int resident_pv_rotation_always = 1;", self.main)
        self.assertIn('#include "../rotation/main.c"', self.main)
        self.assertIn("-D__wrap_akv_experimental_pv_f16_pair=resident_pv_rotation_body", self.main)
        self.assertIn("-Dresident_pv_rotation_selected=resident_pv_rotation_always", self.main)
        self.assertNotIn("__real_akv_experimental_pv_f16_pair", self.asm)

    def test_arm_zero_tail_calls_strong_rotation_without_preparation(self):
        initial, regs, events = wrapper_path(self.asm, 0)
        self.assertEqual(events, [("tail", "resident_pv_rotation_body")])
        for reg, value in initial.items():
            self.assertEqual(regs[reg], value)

    def test_candidate_control_return_and_active_store_spans(self):
        for dimension in (64, 96, 128):
            for tokens in range(1, 65):
                with self.subTest(dimension=dimension, tokens=tokens):
                    candidate_contract(self.asm, tokens, dimension)

    def test_exact_custom_encoding(self):
        words = [int(args[0], 0) for op, args in instructions(self.asm)[0] if op == ".word"]
        self.assertEqual(words, [0x0485705B])
        word = words[0]
        self.assertEqual((word & 127, (word >> 12) & 7, word >> 25), (0x5B, 7, 2))
        self.assertEqual(((word >> 7) & 31, (word >> 15) & 31, (word >> 20) & 31), (0, 10, 8))

    def test_no_nested_timing_flags_or_capture_work(self):
        ops = [op for op, _ in instructions(self.asm)[0]]
        self.assertEqual(ops.count("call"), 1)
        self.assertEqual(ops.count("vse16.v"), 2)
        self.assertFalse(set(ops) & {"rdcycle", "frcsr", "fscsr", "csrw", "csrwi"})

    def test_scalar_glue_mutations_are_rejected(self):
        for old, new in (("ld              ra, 0(sp)", "li              ra, 0"),
                         ("li              a5, 2", "li              a5, 1"),
                         ("ori             a0, a0, 256", "ori             a0, a0, 128"),
                         ("addi            t0, a1, 512", "addi            t0, a1, 256"),
                         ("vse16.v         v2, (t0)", "vse16.v         v0, (t0)"),
                         ("0x0485705b", "0x048570db")):
            self.assertIn(old, self.asm)
            with self.subTest(mutation=new), self.assertRaises(ValueError):
                candidate_contract(self.asm.replace(old, new, 1), 9, 96)

    def test_smoke_executes_one_candidate_not_the_included_abba_main(self):
        self.assertIn("#define main resident_soc_eval_abba_main", self.smoke)
        self.assertIn('#include "main.c"', self.smoke)
        self.assertIn("#undef main", self.smoke)
        self.assertIn("selected_arm = 1;", self.smoke)
        self.assertEqual(self.smoke.count("full_call(&groups)"), 1)
        self.assertNotIn("resident_soc_eval_abba_main(", self.smoke)

    def test_smoke_identity_csr_and_bitwise_output_checks(self):
        for text in ("SMOKE_EXPECT_FCSR = 3", "initial_fcsr != 0", "initial_vcsr != 0",
                     "initial_vstart != 0", "fcsr != SMOKE_EXPECT_FCSR", "vcsr != 0", "vstart != 0",
                     "status != AKV_STATUS_OK", "groups != 1", "resident_pv_rotation_selected != 1",
                     "PAIR_EXPECT_QUERY_HASH", "PAIR_EXPECT_GUARD_HASH", "PAIR_EXPECT_DATA_BYTES",
                     "PAIR_EXPECT_DATA_HASH", "memcmp(query.value, decode_query_f16",
                     "memcpy(&expected, &native_golden[i]", "errors += actual != expected;",
                     'printf("SMOKE_OUT index=%u bits=%08x expected=%08x',
                     'printf("SMOKE_DONE calls=1 errors=%lu', "return errors != 0;"):
            self.assertIn(text, self.smoke)
        self.assertNotIn("near(", self.smoke)
        self.assertIn("i < HEADS * DIM", self.smoke)

    def test_smoke_drains_and_samples_before_reporting(self):
        call = self.smoke.index("full_call(&groups)")
        drain = self.smoke.index("drain();", call)
        csr = self.smoke.index("read_csr(&fcsr, &vcsr, &vstart)", drain)
        report = self.smoke.index('printf("SMOKE_META')
        self.assertLess(call, drain)
        self.assertLess(drain, csr)
        self.assertLess(csr, report)
        self.assertLess(self.smoke.index("vlenb != 128"), call)
        self.assertLess(self.smoke.index("reset_csr();"), call)


if __name__ == "__main__":
    unittest.main()
