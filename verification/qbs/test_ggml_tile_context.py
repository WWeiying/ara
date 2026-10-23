import json
import re
import unittest
from collections import Counter

from check_ggml_tile_context import RUNS, SHAPES, Shape, check_output, expected_dispatch


# Exact run-0 EXEC records from worker01; independent of fixture counters.
PRODUCTION_EXEC = (
    "GGML_RISCV_QBS_EXEC type=Q4_K gemv_calls=0 gemm_calls=10 "
    "input_rows=56 output_rows=370 activation_elements=43008 output_elements=2072 "
    "dot_elements=1591296 split_calls=0 commands_m1=0 commands_m2=0 commands_m3=0 "
    "commands_m4=28 commands_m5=0 commands_m6=0 commands_m7=0 commands_m8=0 "
    "native_qbexec=28 emulated_commands=0 command_dot_elements=1591296 "
    "segmented_commands=0 context_fill=0 context_reuse=0 context_release=0",
    "GGML_RISCV_QBS_EXEC type=Q8_0 gemv_calls=2 gemm_calls=20 "
    "input_rows=112 output_rows=814 activation_elements=74688 output_elements=4144 "
    "dot_elements=2763456 split_calls=0 commands_m1=20 commands_m2=0 commands_m3=4 "
    "commands_m4=48 commands_m5=0 commands_m6=0 commands_m7=0 commands_m8=0 "
    "native_qbexec=72 emulated_commands=0 command_dot_elements=2763456 "
    "segmented_commands=0 context_fill=0 context_reuse=0 context_release=0",
)


def record(label, **fields):
    return label + " " + " ".join(f"{key}={value}" for key, value in fields.items())


def fixture(force_direct_runs=(), reverse_parallel=False):
    """Emit complete protocol evidence, including independent summary records."""
    lines = ["Linux guest boot"]
    for run, (context, wide, threads) in enumerate(RUNS):
        lines.append(record("QBS_TILE_RUN_BEGIN", run=run, context=context, wide=wide, threads=threads))
        summaries = {"q8_0": Counter(), "q4_K": Counter()}
        seq, generation, total_bytes = 0, 0, 0
        for case, shape in enumerate(SHAPES):
            for epoch in (0, 1):
                graph_seq = case * 2 + epoch + 1
                lines.append(record("QBS_TILE_GRAPH_BEGIN", case=case, type=shape.kind,
                                    m=shape.m, n=shape.n, k_blocks=shape.blocks, threads=threads, epoch=epoch))
                calls, commands, selected = expected_dispatch(shape, context, wide, threads)
                if run in force_direct_runs:
                    commands = [(m, n, kb, 0) for m, n, kb, _ in commands]
                tail = shape.m % 8
                stored_m = shape.m + (8 - tail if selected and tail >= 5 else 0)
                payload = stored_m * shape.blocks * shape.activation_bytes
                total_bytes += payload
                lines.append(record("GGML_RISCV_QBS_LIFETIME", seq=graph_seq, graph_epoch=graph_seq,
                                    weight_type=shape.kind, weight_profile=shape.profiles[0],
                                    activation_profile=shape.profiles[1], m=shape.m, n=37,
                                    k=shape.blocks * shape.elements, bytes=payload,
                                    digest=f"{0x100000 + wide * 1000 + graph_seq:016x}",
                                    quantize_time_valid=int(threads == 1), quantize_time_us=int(threads == 1)))
                counts = summaries[shape.kind]
                for kind, mode, k, m, n, split in calls:
                    lines.append(record("GGML_RISCV_QBS_CALL", type=kind, mode=mode, k=k,
                                        input_rows=m, output_rows=n, split_k=split))
                    counts[mode + "_calls"] += 1
                    counts["input_rows"] += m
                    counts["output_rows"] += n
                    counts["activation_elements"] += m * k
                    counts["output_elements"] += m * n
                    counts["dot_elements"] += m * n * k
                command_lines = []
                for index, (m, n, kb, access) in enumerate(commands):
                    seq += 1
                    linked = int(threads == 1 or index % 3 == 0)
                    command_lines.append(record("GGML_RISCV_QBS_COMMAND", seq=seq,
                                                graph_epoch=graph_seq if linked else 0,
                                                activation_seq=graph_seq if linked else 0, linked=linked,
                                                weight_type=shape.kind, weight_profile=shape.profiles[0],
                                                activation_profile=shape.profiles[1], m=m, n=n, k_blocks=kb,
                                                access=access, context_id=0,
                                                context_generation=generation if access else 0,
                                                segmented=0, emulated=0))
                    counts["commands_m" + str(m)] += 1
                    counts["native_qbexec"] += 1
                    counts["command_dot_elements"] += m * n * kb * shape.elements
                    if access:
                        counts[{1: "context_fill", 2: "context_reuse", 3: "context_release"}[access]] += 1
                lines.extend(reversed(command_lines) if threads == 3 and reverse_parallel else command_lines)
                if any(c[3] for c in commands):
                    generation = (generation + 1) % 256
                lines.append(record("QBS_TILE_GRAPH_PASS", outputs=shape.m * shape.n,
                                    digest=f"{0x200000 + wide * 1000 + threads * 100 + graph_seq:016x}",
                                    max_error="1e-7"))
        lines.append(record("QBS_TILE_GRAPH_SUITE_PASS", cases=2 * len(SHAPES)))
        lines.append(record("GGML_RISCV_QBS_LIFETIME_SUMMARY", quantizations=2 * len(SHAPES),
                            exact_reuse_candidates=0, quantized_bytes=total_bytes, reusable_quantized_bytes=0,
                            quantizations_with_time=2 * len(SHAPES) if threads == 1 else 0,
                            quantize_time_us=2 * len(SHAPES) if threads == 1 else 0,
                            reusable_quantize_time_us=0, graph_epochs=2 * len(SHAPES),
                            cross_op_fill=0, cross_op_reuse=0, cross_op_release=0,
                            cross_op_quantization_skips=0, cross_op_activation_bytes_saved=0))
        for kind, counts in summaries.items():
            fields = ("gemv_calls gemm_calls input_rows output_rows activation_elements output_elements "
                      "dot_elements split_calls").split()
            fields += [f"commands_m{m}" for m in range(1, 9)]
            fields += ("native_qbexec emulated_commands command_dot_elements segmented_commands "
                       "context_fill context_reuse context_release").split()
            summary_type = {"q4_K": "Q4_K", "q8_0": "Q8_0"}[kind]
            lines.append(record("GGML_RISCV_QBS_EXEC", type=summary_type, **{key: counts[key] for key in fields}))
        lines.append(record("QBS_TILE_RUN_END", run=run, exit=0))
    lines.append("GUEST_TEST_EXIT=0")
    return "\n".join(lines) + "\n"


def mutate_line(text, prefix, transform, *, run=0, case=0, epoch=0):
    lines = text.splitlines()
    inside_run = inside_graph = False
    for index, line in enumerate(lines):
        if line.startswith("QBS_TILE_RUN_BEGIN"):
            inside_run = line.startswith(f"QBS_TILE_RUN_BEGIN run={run} ")
        if line.startswith("QBS_TILE_GRAPH_BEGIN"):
            inside_graph = line.startswith(f"QBS_TILE_GRAPH_BEGIN case={case} ") and line.endswith(f"epoch={epoch}")
        if inside_run and inside_graph and line.startswith(prefix):
            lines[index] = transform(line)
            return "\n".join(lines) + "\n"
    raise AssertionError("Fixture record not found: " + prefix)


class DispatchPolicyTests(unittest.TestCase):
    def commands(self, kind, m, kb, wide=0, context=1, threads=1):
        return expected_dispatch(Shape(kind, m, kb), context, wide, threads)[1]

    def test_manifest_is_fixed(self):
        self.assertEqual(len(SHAPES), 16)
        self.assertEqual([(s.kind, s.m, s.blocks) for s in SHAPES], [
            ("q8_0", 1, 1), ("q8_0", 3, 17), ("q8_0", 4, 28),
            ("q8_0", 4, 32), ("q8_0", 4, 33), ("q8_0", 5, 1),
            ("q8_0", 5, 17), ("q8_0", 5, 28), ("q8_0", 8, 17),
            ("q8_0", 8, 28), ("q8_0", 9, 17), ("q4_K", 4, 2),
            ("q4_K", 4, 4), ("q4_K", 4, 5), ("q4_K", 8, 2), ("q4_K", 8, 3)])

    def test_exact_n37_patterns(self):
        self.assertEqual(self.commands("q8_0", 4, 28), [(4, 32, 28, 1), (4, 5, 28, 3)])
        self.assertEqual(self.commands("q8_0", 8, 17), [(4, 32, 17, 1), (4, 5, 17, 3)] * 2)
        self.assertEqual(self.commands("q8_0", 8, 17, 1),
                         [(8, 16, 17, 1), (8, 16, 17, 2), (8, 5, 17, 3)])
        self.assertEqual(self.commands("q8_0", 9, 17, 1),
                         [(8, 16, 17, 1), (8, 16, 17, 2), (8, 5, 17, 3),
                          (1, 32, 17, 1), (1, 5, 17, 3)])

    def test_capacity_fallback_and_single_block(self):
        for kind, m, kb, wide, eligible in (
                ("q8_0", 5, 1, 1, True), ("q8_0", 5, 17, 1, True),
                ("q8_0", 5, 28, 1, False), ("q8_0", 8, 32, 1, False),
                ("q8_0", 4, 32, 0, True), ("q8_0", 4, 33, 0, False),
                ("q8_0", 9, 28, 1, False), ("q4_K", 4, 4, 0, True),
                ("q4_K", 4, 5, 0, False), ("q4_K", 8, 2, 1, True),
                ("q4_K", 8, 3, 1, False), ("q4_K", 8, 4, 1, False)):
            with self.subTest(kind=kind, m=m, kb=kb, wide=wide):
                commands = self.commands(kind, m, kb, wide)
                self.assertEqual(any(c[3] for c in commands), eligible)
                self.assertTrue(all(c[2] == kb for c in commands))

    def test_mixed_tail_is_plan_wide_fallback(self):
        for m, wide in ((3, 0), (6, 0), (7, 0), (10, 1), (11, 1), (12, 1)):
            with self.subTest(m=m, wide=wide):
                self.assertTrue(all(c[3] == 0 for c in self.commands("q8_0", m, 1, wide)))

    def test_wide_policy_is_not_forced_or_context_aware(self):
        self.assertFalse(expected_dispatch(Shape("q4_K", 5, 2), 1, 1, 1)[2])
        self.assertTrue(expected_dispatch(Shape("q4_K", 6, 2), 1, 1, 1)[2])
        self.assertTrue(expected_dispatch(Shape("q8_0", 8, 28), 1, 1, 1)[2])
        self.assertTrue(all(c[3] == 0 for c in self.commands("q8_0", 8, 28, 1)))

    def test_parallel_singleton_output_plans(self):
        self.assertEqual(Counter(self.commands("q8_0", 9, 17, 1, threads=3)),
                         Counter({(8, 4, 17, 0): 9, (1, 4, 17, 0): 9,
                                  (8, 1, 17, 0): 1, (1, 1, 17, 0): 1}))


class OutputCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = fixture()

    def reject(self, text):
        with self.assertRaises(ValueError):
            check_output(text)

    def test_accepts_full_native_evidence(self):
        result = check_output(self.good)
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(result["graphs"], 192)
        self.assertEqual([r["context_eligible_graphs"] for r in result["runs"]], [0, 26, 0, 20, 0, 0])
        self.assertTrue(all(r["outputs"] == sum(2 * s.m * 37 for s in SHAPES) for r in result["runs"]))
        json.dumps(result)

    def test_parallel_trace_may_arrive_out_of_sequence(self):
        check_output(fixture(reverse_parallel=True))

    def test_crlf_guest_console(self):
        check_output(self.good.replace("\n", "\r\n"))

    def test_context_eligibility_cannot_be_self_reported_away(self):
        self.reject(fixture(force_direct_runs=(1, 3)))

    def test_fake_pass_without_native_work(self):
        self.reject("\n".join(line for line in self.good.splitlines()
                              if not line.startswith("GGML_RISCV_QBS_COMMAND")))
        self.reject("QBS_TILE_GRAPH_SUITE_PASS cases=32\nGUEST_TEST_EXIT=0\n")

    def test_run_and_graph_coverage(self):
        for broken in (
                self.good.replace("QBS_TILE_RUN_END run=1 exit=0", "QBS_TILE_RUN_END run=1 exit=1"),
                self.good.replace("run=4 context=0 wide=1 threads=3", "run=4 context=0 wide=1 threads=1"),
                self.good.replace("QBS_TILE_GRAPH_SUITE_PASS cases=32", "QBS_TILE_GRAPH_SUITE_PASS cases=31", 1),
                self.good.replace("QBS_TILE_GRAPH_BEGIN case=1 ", "QBS_TILE_GRAPH_BEGIN case=0 ", 1),
                self.good.replace("GUEST_TEST_EXIT=0", "GUEST_TEST_EXIT=1"),
                self.good.replace("GUEST_TEST_EXIT=0", ""), self.good + "GUEST_TEST_EXIT=0\n",
                self.good + self.good):
            with self.subTest(tail=broken[-90:]):
                self.reject(broken)

    def test_missing_duplicate_or_malformed_records(self):
        for prefix in ("GGML_RISCV_QBS_CALL", "GGML_RISCV_QBS_COMMAND",
                       "GGML_RISCV_QBS_LIFETIME ", "QBS_TILE_GRAPH_PASS"):
            for transform in (lambda line: "", lambda line: line + "\n" + line,
                              lambda line: "broken-prefix " + line):
                with self.subTest(prefix=prefix, transform=transform):
                    self.reject(mutate_line(self.good, prefix, transform))

    def test_bad_native_command_fields(self):
        for old, new in (("emulated=0", "emulated=1"), ("segmented=0", "segmented=1"),
                         ("weight_profile=6", "weight_profile=1"), ("activation_profile=2", "activation_profile=1"),
                         ("k_blocks=1", "k_blocks=2"), ("n=32", "n=31"), ("m=1", "m=2"),
                         ("linked=1", "linked=0"), ("graph_epoch=1", "graph_epoch=0"),
                         ("activation_seq=1", "activation_seq=2"), ("seq=1 ", "seq=2 "),
                         ("context_id=0", "context_id=1"), ("context_generation=0", "context_generation=256")):
            with self.subTest(old=old, new=new):
                self.reject(mutate_line(self.good, "GGML_RISCV_QBS_COMMAND", lambda line: line.replace(old, new)))

    def test_context_lifecycle_and_capacity(self):
        for case, run, old, new in ((0, 1, "access=1", "access=2"),
                                    (0, 1, "context_generation=0", "context_generation=1"),
                                    (4, 1, "access=0", "access=1"),
                                    (9, 3, "access=0", "access=1"),
                                    (14, 5, "access=0", "access=1")):
            with self.subTest(case=case, run=run, old=old):
                self.reject(mutate_line(self.good, "GGML_RISCV_QBS_COMMAND", lambda line: line.replace(old, new),
                                        case=case, run=run))
        self.reject(self.good.replace("access=3 ", "access=2 ", 1))

    def test_same_total_work_but_wrong_per_tile_columns(self):
        # The sum is still 37 outputs, but the expected N32/N5 mapping is lost.
        broken = mutate_line(self.good, "GGML_RISCV_QBS_COMMAND", lambda line: line.replace("n=32", "n=31"))
        broken = broken.replace("m=1 n=5 k_blocks=1 access=0", "m=1 n=6 k_blocks=1 access=0", 1)
        self.reject(broken)

    def test_numerical_evidence_and_epoch_freshness(self):
        for transform in (lambda line: line.replace("outputs=37", "outputs=36"),
                          lambda line: re.sub(r"digest=\w+", "digest=123", line),
                          lambda line: line.replace("max_error=1e-7", "max_error=nan"),
                          lambda line: line.replace("max_error=1e-7", "max_error=inf"),
                          lambda line: line.replace("max_error=1e-7", "max_error=-1")):
            self.reject(mutate_line(self.good, "QBS_TILE_GRAPH_PASS", transform))
        first = re.search(r"QBS_TILE_GRAPH_PASS outputs=37 digest=(\w+)", self.good).group(1)
        self.reject(mutate_line(self.good, "QBS_TILE_GRAPH_PASS",
                                lambda line: re.sub(r"digest=\w+", "digest=" + first, line), epoch=1))
        self.reject(mutate_line(self.good, "GGML_RISCV_QBS_LIFETIME ",
                                lambda line: line.replace("digest=0000000000100002", "digest=0000000000100001"), epoch=1))

    def test_on_off_digest_pairing(self):
        self.reject(mutate_line(self.good, "QBS_TILE_GRAPH_PASS",
                                lambda line: re.sub(r"digest=\w+", "digest=0123456789abcdef", line), run=1))
        self.reject(mutate_line(self.good, "GGML_RISCV_QBS_LIFETIME ",
                                lambda line: re.sub(r"digest=\w+", "digest=0123456789abcdef", line), run=3))

    def test_summary_is_checked_not_trusted(self):
        self.reject(re.sub(r"native_qbexec=\d+", "native_qbexec=0", self.good, count=1))
        self.reject(self.good.replace("cross_op_fill=0", "cross_op_fill=1", 1))
        self.reject(self.good.replace("graph_epochs=32", "graph_epochs=31", 1))
        self.reject("\n".join(line for line in self.good.splitlines()
                              if not line.startswith("GGML_RISCV_QBS_EXEC")))

    def test_exact_production_exec_records(self):
        log = self.good
        for line in PRODUCTION_EXEC:
            kind = line.split()[1]
            log = re.sub(r"^GGML_RISCV_QBS_EXEC " + kind + r" .*?$",
                         lambda _: line, log, count=1, flags=re.M)
        result = check_output(log)
        self.assertEqual(result["runs"][0]["native_commands"], 100)
        self.assertEqual(result["runs"][0]["command_dot_elements"], 4354752)
        self.assertEqual(result["runs"][0]["outputs"], 6216)
        for old, new in (("native_qbexec=28", "native_qbexec=29"),
                         ("output_elements=2072", "output_elements=2073"),
                         ("emulated_commands=0", "emulated_commands=1")):
            with self.subTest(field=old):
                self.reject(log.replace(PRODUCTION_EXEC[0], PRODUCTION_EXEC[0].replace(old, new), 1))

    def test_exec_type_mapping_is_exact_and_duplicates_rejected(self):
        for original, alternatives in (
                ("Q4_K", ("q4_K", "q4_k", "Q4_k", "Q4_0", "Q8_0", "UNKNOWN")),
                ("Q8_0", ("q8_0", "q8_0x", "Q8_K", "Q4_K"))):
            for changed in alternatives:
                with self.subTest(original=original, changed=changed):
                    self.reject(self.good.replace("GGML_RISCV_QBS_EXEC type=" + original,
                                                  "GGML_RISCV_QBS_EXEC type=" + changed, 1))

    def test_exec_normalization_does_not_apply_to_commands_or_calls(self):
        self.reject(mutate_line(self.good, "GGML_RISCV_QBS_CALL",
                                lambda line: line.replace("type=q8_0", "type=Q8_0")))
        self.reject(mutate_line(self.good, "GGML_RISCV_QBS_COMMAND",
                                lambda line: line.replace("weight_type=q8_0", "weight_type=Q8_0")))

    def test_failures_anywhere_are_rejected(self):
        for marker in ("QBS_TILE_GRAPH_FAIL reason=numerical_mismatch", "Fatal: failed",
                       "QBS_TILE_GRAPH_MISMATCH", "Kernel panic - not syncing"):
            with self.subTest(marker=marker):
                self.reject(self.good + marker + "\n")


if __name__ == "__main__":
    unittest.main()
