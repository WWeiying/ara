#!/usr/bin/env python3
"""Host-only generator tests. Outputs live in TemporaryDirectory, never apps/bin.

Set LLAMA_TEST_REAL_CAPTURES=1 to validate the imported cases against their
existing captures as well. This checks slicing/layout/provenance, not RVV or
QBS numerical execution, and does not run any simulator.
"""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch


APPS = Path(__file__).resolve().parents[2]
COMMON = APPS / "llama_qwen25_real/common"
BASE = runpy.run_path(str(COMMON / "generate_case.py"))
QBS = runpy.run_path(str(COMMON / "generate_qbs_case.py"))
FORMATS = {
    "q2_K": (256, 84), "q3_K": (256, 110), "q4_0": (32, 18),
    "q4_K": (256, 144), "q5_0": (32, 22), "q5_K": (256, 176),
    "q6_K": (256, 210), "iq4_nl": (32, 18), "q8_0": (32, 34),
}
Q8_0_FORMATS = {"q4_0", "q5_0", "iq4_nl", "q8_0"}
FAMILIES = (
    "iq4_nl_decode_attn_q", "q4_0_decode_attn_q", "q5_0_decode_attn_q",
    "q2k_decode_ffn_down", "q2k_decode_ffn_down_4r", "shape_prefill_n33",
)


@contextlib.contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


class SourceUnionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("LLAMA_CAPTURE_ROOT", None)

    def fixture(self, weight_type, rows=33, inputs=4, x32=False):
        elements, block_bytes = FORMATS[weight_type]
        capture = self.root / "capture"
        source = capture / "decode/operators/probe"
        source.mkdir(parents=True, exist_ok=True)
        k, capture_rows, capture_inputs = elements * 2, rows + 2, inputs + 1
        tensors = {
            f"weight_{weight_type}": (
                bytes(i % 251 for i in range(capture_rows * 2 * block_bytes)),
                [k, capture_rows], weight_type),
            "activation_f32": (
                struct.pack(f"<{k * capture_inputs}f", *range(k * capture_inputs)),
                [k, capture_inputs], "f32"),
            "output_f32": (
                struct.pack(f"<{capture_rows * capture_inputs}f",
                            *range(capture_rows * capture_inputs)),
                [capture_rows, capture_inputs], "f32"),
        }
        for name, (raw, shape, kind) in tensors.items():
            (source / f"{name}.bin").write_bytes(raw)
            write_json(source / f"{name}.json",
                       {"nbytes": len(raw), "shape": shape, "type": kind})
        write_json(capture / "model.json",
                   {"description": "host layout fixture", "llama_commit": "fixture"})
        spec = dict(case_id="host_layout_qbs", capture_root=str(capture),
                    phase="decode", operator="probe", weight_type=weight_type,
                    k=k, rows=rows, inputs=inputs, capture_rows=capture_rows,
                    capture_inputs=capture_inputs, rvv_x32=x32)
        app = self.root / "app"
        app.mkdir(exist_ok=True)
        write_json(app / "case.json", spec)
        (app / "main.c").write_text("", encoding="utf-8")
        return app, spec, source

    def generate(self, app, script):
        output = io.StringIO()
        with working_directory(app), contextlib.redirect_stdout(output):
            runpy.run_path(str(script), run_name="__main__")
        self.assertIn("benchmark_weight_start:", output.getvalue())
        generated = app / "generated"
        provenance = json.loads((generated / "provenance.json").read_text())
        for name, record in provenance["tensors"].items():
            raw = (generated / name).read_bytes()
            self.assertEqual(len(raw), record["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
        return generated, provenance

    def assert_slices(self, generated, spec, source):
        elements, block_bytes = FORMATS[spec["weight_type"]]
        weight_bytes = spec["rows"] * (spec["k"] // elements) * block_bytes
        source_weight = (source / f"weight_{spec['weight_type']}.bin").read_bytes()
        self.assertEqual((generated / "source_weight.bin").read_bytes(),
                         source_weight[:weight_bytes])
        self.assertEqual((generated / "activation_f32.bin").read_bytes(),
                         (source / "activation_f32.bin").read_bytes()
                         [:spec["inputs"] * spec["k"] * 4])
        golden = (source / "output_f32.bin").read_bytes()
        expected = b"".join(golden[i * spec["capture_rows"] * 4:
                                  (i * spec["capture_rows"] + spec["rows"]) * 4]
                            for i in range(spec["inputs"]))
        self.assertEqual((generated / "golden_f32.bin").read_bytes(), expected)

    def assert_r4(self, generated, spec):
        elements, size = FORMATS[spec["weight_type"]]
        blocks = spec["k"] // elements
        rows = spec["rows"]
        raw = (generated / "source_weight.bin").read_bytes()
        expected = b"".join(
            raw[(row * blocks + block) * size:(row * blocks + block + 1) * size]
            if row < rows else bytes(size)
            for group in range(0, rows, 4) for block in range(blocks)
            for row in range(group, group + 4))
        self.assertEqual((generated / "embedded_weight.bin").read_bytes(), expected)

    def test_format_contract(self):
        self.assertEqual(BASE["Q8_0_ACTIVATION_WEIGHTS"], Q8_0_FORMATS)
        self.assertEqual(BASE["WEIGHT_FORMATS"], {
            name: dict(block_elements=elements, block_bytes=size)
            for name, (elements, size) in FORMATS.items()})

    def test_qbs_all_formats_and_activation_layouts(self):
        for weight_type in FORMATS:
            for inputs in (1, 4, 8):
                with self.subTest(weight_type=weight_type, inputs=inputs):
                    app, spec, source = self.fixture(weight_type, inputs=inputs)
                    generated, provenance = self.generate(app, COMMON / "generate_qbs_case.py")
                    self.assert_slices(generated, spec, source)
                    self.assert_r4(generated, spec)
                    activation = "Q8_0" if weight_type in Q8_0_FORMATS else "Q8_K"
                    layout = ("A_M8_INTERLEAVED" if inputs == 8 else
                              "A_M4_INTERLEAVED" if inputs == 4 and activation == "Q8_K"
                              else "A_ROW_MAJOR")
                    self.assertEqual(provenance["qbs"]["activation_profile"], activation)
                    self.assertEqual(provenance["activation_quantization"],
                                     f"F32_to_{activation}_at_runtime")
                    self.assertEqual(provenance["qbs"]["activation_layout"], layout)
                    self.assertEqual(provenance["qbs_activation_pack_in_timed_region"],
                                     layout != "A_ROW_MAJOR")
                    self.assertNotIn("runtime_setup_cycles", provenance)

    def test_rvv_row_major_all_formats(self):
        for weight_type in FORMATS:
            with self.subTest(weight_type=weight_type):
                app, spec, source = self.fixture(weight_type)
                generated, provenance = self.generate(app, COMMON / "generate_case.py")
                self.assert_slices(generated, spec, source)
                self.assertEqual((generated / "embedded_weight.bin").read_bytes(),
                                 (generated / "source_weight.bin").read_bytes())
                activation = "Q8_0" if weight_type in Q8_0_FORMATS else "Q8_K"
                self.assertEqual(provenance["runtime_timed_region"],
                                 f"F32_to_{activation}_plus_quantized_matmul")

    def test_existing_x32_formats(self):
        for weight_type, fields in BASE["RVV_X32_FIELDS"].items():
            with self.subTest(weight_type=weight_type):
                app, spec, source = self.fixture(weight_type, rows=32, x32=True)
                generated, provenance = self.generate(app, COMMON / "generate_case.py")
                self.assert_slices(generated, spec, source)
                size = FORMATS[weight_type][1]
                raw = (generated / "source_weight.bin").read_bytes()
                expected = b"".join(
                    raw[(row * 2 + block) * size + offset + element:
                        (row * 2 + block) * size + offset + element + width]
                    for block in range(2) for offset, length, width in fields
                    for element in range(0, length, width) for row in range(32))
                self.assertEqual((generated / "embedded_weight.bin").read_bytes(), expected)
                self.assertEqual(provenance["embedded_weight_layout"], f"{weight_type}_x32_rvv")

    def test_r4_breaks_hardlink_without_modifying_source(self):
        source, target = self.root / "source", self.root / "target"
        raw = bytes(range(24))
        source.write_bytes(raw)
        os.link(source, target)
        QBS["repack_r4"](source, target, 3, 2, 4)
        self.assertEqual(source.read_bytes(), raw)
        self.assertNotEqual(source.stat().st_ino, target.stat().st_ino)
        self.assertEqual(target.stat().st_size, 32)

    def test_rejects_wrong_weight_metadata(self):
        app, _, source = self.fixture("iq4_nl")
        p = source / "weight_iq4_nl.json"
        metadata = json.loads(p.read_text())
        metadata["type"] = "q4_0"
        write_json(p, metadata)
        with self.assertRaisesRegex(SystemExit, "weight type mismatch"):
            self.generate(app, COMMON / "generate_case.py")

    def test_rejects_truncated_capture(self):
        app, _, source = self.fixture("q2_K")
        (source / "weight_q2_K.bin").write_bytes(b"short")
        with self.assertRaisesRegex(SystemExit, "size mismatch"):
            self.generate(app, COMMON / "generate_case.py")

    def test_rejects_n33_x32(self):
        app, _, _ = self.fixture("q4_K", x32=True)
        with self.assertRaisesRegex(SystemExit, "multiple of 32"):
            self.generate(app, COMMON / "generate_case.py")

    def test_imported_case_contracts(self):
        for family in FAMILIES:
            for mode in ("qbs", "rvv"):
                with self.subTest(family=family, mode=mode):
                    app = APPS / f"llama_qwen25_{family}_{mode}"
                    spec = json.loads((app / "case.json").read_text())
                    source = (app / "main.c").read_text()
                    for key in ("k", "rows", "inputs"):
                        value = re.search(rf"^#define BENCH_{key.upper()} (\d+)$",
                                          source, re.MULTILINE)
                        self.assertIsNotNone(value)
                        self.assertEqual(int(value[1]), spec[key])
                    self.assertIn(f'#define BENCH_CASE_ID "{spec["case_id"]}"', source)
                    self.assertTrue((app / "script/gen_data.py").is_file())
                    if mode == "rvv":
                        self.assertIs(spec["rvv_x32"], False)
                    if family == "shape_prefill_n33" and mode == "rvv":
                        self.assertIn("#define BENCH_RVV_ROW_MAJOR 1", source)

    def test_host_c_block_layouts(self):
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("host C compiler unavailable")
        result = subprocess.run(
            [compiler, "-std=c11", "-x", "c", "-fsyntax-only", "-"],
            input=f'#include "{APPS / "llama_q4km_micro/micro_kernels.h"}"\n',
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.environ.get("LLAMA_TEST_REAL_CAPTURES") == "1",
                         "set LLAMA_TEST_REAL_CAPTURES=1 for archived capture validation")
    def test_real_capture_imported_wrappers(self):
        for family in FAMILIES:
            for mode in ("qbs", "rvv"):
                with self.subTest(family=family, mode=mode):
                    original = APPS / f"llama_qwen25_{family}_{mode}"
                    app = self.root / original.name
                    app.mkdir()
                    for name in ("case.json", "main.c"):
                        shutil.copyfile(original / name, app / name)
                    spec = json.loads((app / "case.json").read_text())
                    capture = Path(spec.get("capture_root", BASE["DEFAULT_CAPTURE_ROOT"]))
                    source = capture / spec["phase"] / "operators" / spec["operator"]
                    generated, _ = self.generate(app, original / "script/gen_data.py")
                    self.assert_slices(generated, spec, source)
                    if mode == "qbs":
                        self.assert_r4(generated, spec)
                    else:
                        self.assertEqual((generated / "embedded_weight.bin").read_bytes(),
                                         (generated / "source_weight.bin").read_bytes())


if __name__ == "__main__":
    unittest.main()
