import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from rtl_build import cases, HOST_FLAGS, HERE
from rtl_check import check_output


class HostOracleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.exe = cls.root / "oracle"
        subprocess.run(["/usr/bin/gcc", *HOST_FLAGS, HERE / "rtl_oracle.c", "-lm", "-o", cls.exe],
                       check=True, capture_output=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def invoke(self, q, k):
        (self.root / "q").write_bytes(q)
        (self.root / "k").write_bytes(k)
        result = subprocess.run([self.exe, self.root / "q", self.root / "k", self.root / "g"],
                                check=True, capture_output=True, text=True, timeout=30)
        return (self.root / "g").read_bytes(), result.stdout.splitlines()

    def test_global_head_token_stride_and_tails(self):
        q = b"".join(struct.pack("<e", float(h + 1)) * 128 for h in range(12))
        k = b"".join(struct.pack("<e", float(h * 256 + t + 1)) * 128
                     for h in range(2) for t in range(256))
        g, lines = self.invoke(q, k)
        self.assertEqual(len(g), 12288)
        for c in cases():
            self.assertTrue(lines[c["id"]].endswith(" fcsr=0"))
            for row in range(6):
                for token in range(64):
                    offset = (c["id"] * 384 + row * 64 + token) * 4
                    expected = (struct.pack("<f", float(128 * (c["head"] * 6 + row + 1) *
                                                        (c["head"] * 256 + c["tile"] + token + 1)))
                                if token < c["vl"] else b"\xa5" * 4)
                    self.assertEqual(g[offset:offset+4], expected)

    def test_inexact_flag_and_order(self):
        q = struct.pack("<e", 1.0) * (12 * 128)
        krow = struct.pack("<e", 16384.0) + struct.pack("<H", 1) + b"\0" * (126 * 2)
        g, lines = self.invoke(q, krow * (2 * 256))
        self.assertTrue(all(line.endswith(" fcsr=1") for line in lines))
        for c in cases():
            self.assertEqual(g[c["id"] * 1536:c["id"] * 1536 + 4], struct.pack("<f", 16384.0))

    def test_half_subnormal_and_signed_zero(self):
        q = struct.pack("<H", 1) * (12 * 128)
        krow = struct.pack("<e", 1.0) * 127 + struct.pack("<e", -0.0)
        g, lines = self.invoke(q, krow * (2 * 256))
        self.assertTrue(all(line.endswith(" fcsr=0") for line in lines))
        for c in cases():
            self.assertEqual(g[c["id"] * 1536:c["id"] * 1536 + 4], struct.pack("<f", 127 * 2**-24))


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.cases = [dict(c, fcsr=1) for c in cases()]
        self.golden = b"".join(struct.pack("<I", 0x3f800000 + i) for i in range(8 * 384))
        rows = ["RTL_QK_CAP native=1 panel4=1 pairs=8"]
        for c in self.cases:
            i, vl = c["id"], c["vl"]
            for mode in (0, 1):
                rows.append(f"RTL_QK_BEGIN case={i} mode={mode} kvhead={c['head']} tile={c['tile']} vl={vl} stride={c['stride']}")
                for row in range(6):
                    values = struct.unpack_from("<" + "I" * vl, self.golden, (i * 384 + row * 64) * 4)
                    rows.append(f"RTL_QK_ROW case={i} mode={mode} row={row} count={vl} bits=" +
                                "".join(f"{x:08x}" for x in values))
                rows.append(f"RTL_QK_END case={i} mode={mode} outputs={6*vl} tailwords={6*(64-vl)} guardbytes=512 inputbytes=34688 fcsr=1 vcsr=5 errors=0")
        rows += ["RTL_QK_SUITE_PASS pairs=8 runs=16 outputs=3240 tailwords=2904", "Core Test *** SUCCESS"]
        self.text = "\n".join(rows) + "\n"

    def test_complete_fixture(self):
        self.assertEqual(check_output(self.text, self.cases, self.golden)["outputs"], 3240)

    def test_bad_evidence(self):
        lines = self.text.splitlines()
        bad = ["PASS\nCore Test *** SUCCESS\n", "\n".join(lines[1:]),
               "\n".join(lines[:2] + lines[3:]), self.text + lines[2] + "\n",
               self.text.replace("bits=3f800000", "bits=3f800001", 1),
               self.text.replace("fcsr=1", "fcsr=0", 1),
               self.text.replace("vcsr=5", "vcsr=0", 1),
               self.text.replace("errors=0", "errors=1", 1),
               self.text.replace("tailwords=378", "tailwords=0", 1),
               self.text.replace("Core Test *** SUCCESS", ""),
               self.text + "TIMEOUT\n", self.text + "Core Test *** SUCCESS\n",
               self.text.replace("stride=320", "stride=256", 1),
               self.text.replace("native=1", "native=0", 1)]
        for index, text in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(ValueError):
                check_output(text, self.cases, self.golden)


if __name__ == "__main__":
    unittest.main()
