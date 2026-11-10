"""Compile/run the architecture model only; never builds or launches QEMU."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


class ArchitectureModelTests(unittest.TestCase):
    source = HERE
    include = ROOT / "software/akv/include"
    output = None

    def compile_and_run(self, sanitizer=False):
        with tempfile.TemporaryDirectory(prefix="akv-model-host-") as temporary:
            directory = Path(temporary) if self.output is None else self.output / ("ubsan" if sanitizer else "optimized")
            if self.output is not None:
                directory.mkdir()
            binary = directory / "model"
            command = ["/usr/bin/gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wshadow", "-pedantic", "-O2", "-I" + str(self.include),
                       str(self.source / "akv_model.c"), str(self.source / "test_akv_model.c"), "-o", str(binary)]
            if sanitizer:
                # Trap on UB without depending on the host's missing libubsan.
                command[1:1] = ["-fsanitize=undefined", "-fsanitize-undefined-trap-on-error",
                                 "-fno-sanitize-recover=all"]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if self.output is not None:
                (directory / "compile.log").write_text(compiled.stdout + compiled.stderr)
                (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            if self.output is not None:
                (directory / "run.log").write_text(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.count("AKV_MODEL_CASE "), 11)
            self.assertIn("AKV_MODEL_HOST_PASS cases=11 arithmetic=callback_contract_not_softfloat", result.stdout)

    def test_optimized_model(self):
        self.compile_and_run()

    def test_undefined_behavior_model(self):
        self.compile_and_run(sanitizer=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", type=Path)
    args, remaining = parser.parse_known_args()
    if args.output is None:
        unittest.main(argv=[sys.argv[0], *remaining])
    else:
        output = args.output.absolute()
        signoff = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
        if output.parent != signoff or output != output.resolve() or output.exists():
            raise ValueError("Use a fresh direct signoff output")
        output.mkdir()
        inputs = output / "inputs"
        inputs.mkdir()
        pins = {}
        def digest(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()
        for name in ("akv_model.h", "akv_model.c", "test_akv_model.c", "test_akv_model.py"):
            source = HERE / name
            shutil.copyfile(source, inputs / name)
            pins[str(source)] = digest(source)
        abi = ROOT / "software/akv/include/akv/akv_abi.h"
        (inputs / "include/akv").mkdir(parents=True)
        shutil.copyfile(abi, inputs / "include/akv/akv_abi.h")
        pins[str(abi)] = digest(abi)
        for path in inputs.rglob("*"):
            if path.is_file():
                pins[str(path)] = digest(path)
        (output / "source-pins.json").write_text(json.dumps(pins, indent=2, sort_keys=True) + "\n")
        ArchitectureModelTests.source = inputs
        ArchitectureModelTests.include = inputs / "include"
        ArchitectureModelTests.output = output
        log = io.StringIO()
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ArchitectureModelTests))
        (output / "host.log").write_text(log.getvalue())
        matched = all(digest(Path(path)) == expected for path, expected in pins.items())
        report = dict(state="HOST_MODEL_CALLBACK_PASS_NOT_QEMU" if result.wasSuccessful() and matched else "FAIL",
                      host_tests=result.testsRun, logical_cases=11, configurations=2,
                      post_pins_match=matched, qemu_built=False, qemu_executed=False,
                      arithmetic_acceptance=False, scope="Architecture/lifecycle/layout and mock-FMA callback order only",
                      source_pins_sha256=digest(output / "source-pins.json"))
        (output / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(log.getvalue(), end="")
        print(json.dumps(report, sort_keys=True))
        raise SystemExit(int(report["state"] == "FAIL"))
