"""Host-only checks for frozen simulator identity in terminal re-audits."""

from pathlib import Path
import tempfile
import unittest

from ara_verify.terminal_reaudit import simulator_image, spike_image


class TerminalReauditTests(unittest.TestCase):
    def test_simulator_image_requires_and_hashes_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "simv"
            simv.write_bytes(b"launcher")
            with self.assertRaisesRegex(ValueError, "libraries are missing"):
                simulator_image(simv)
            library = root / "simv.daidir" / "rtl.so"
            library.parent.mkdir()
            library.write_bytes(b"design")
            image = simulator_image(simv)
            self.assertEqual(set(image), {"simv", "simv.daidir/rtl.so"})
            library.write_bytes(b"changed")
            self.assertNotEqual(image, simulator_image(simv))

    def test_spike_command_must_use_same_elf_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            case.mkdir()
            elf = root / "test.elf"
            elf.write_bytes(b"elf")
            binary = root / "spike"
            binary.write_bytes(b"spike")
            command = [str(binary), f"--log={case / 'spike_commit.log'}", str(elf)]
            self.assertEqual(spike_image(command, case, elf), binary)
            for bad in (command[:-1] + [str(root / "other.elf")],
                        [str(binary), "--log=/tmp/other.log", str(elf)],
                        [str(root / "missing"), *command[1:]]):
                with self.subTest(command=bad), self.assertRaises(ValueError):
                    spike_image(bad, case, elf)


if __name__ == "__main__":
    unittest.main()
