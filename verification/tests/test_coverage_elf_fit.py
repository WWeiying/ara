import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "verification/tools/soc-venv/bin/python"
CHECKER = ROOT / "verification/coverage/check_elf_fit.py"


def make_elf(path: Path, address: int, memory_bytes: int) -> None:
    ident = b"\x7fELF" + bytes((2, 1, 1, 0)) + bytes(8)
    header = struct.pack("<HHIQQQIHHHHHH", 2, 243, 1, address, 64, 0, 0,
                         64, 56, 1, 0, 0, 0)
    segment = struct.pack("<IIQQQQQQ", 1, 5, 0, address, address, 0x80,
                          memory_bytes, 0x1000)
    path.write_bytes((ident + header + segment).ljust(0x80, b"\0"))


@unittest.skipUnless(PYTHON.is_file(), "verification pyelftools environment is unavailable")
class CoverageElfFitTest(unittest.TestCase):
    def test_ram_boundary_is_checked_from_load_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fitting = root / "fit.elf"
            crossing = root / "cross.elf"
            make_elf(fitting, 0x800F0000, 0x10000)
            make_elf(crossing, 0x800F0000, 0x10001)
            unaligned = root / "unaligned.elf"
            make_elf(unaligned, 0x800F0001, 0x10000)
            for path, expected in ((fitting, "PASS"), (crossing, "FAIL"),
                                   (unaligned, "FAIL")):
                output = root / f"{path.stem}.json"
                command = [str(PYTHON), str(CHECKER), "--elf", str(path),
                           "--ram-bytes", "1048576", "--ram-word-bytes", "16",
                           "--output", str(output)]
                run = subprocess.run(command, capture_output=True, text=True,
                                     check=False)
                self.assertEqual(run.returncode, 0 if expected == "PASS" else 1,
                                 run.stdout + run.stderr)
                self.assertEqual(json.loads(output.read_text())["status"], expected)


if __name__ == "__main__":
    unittest.main()
