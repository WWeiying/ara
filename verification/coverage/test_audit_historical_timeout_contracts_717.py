import struct
import unittest

from audit_historical_timeout_contracts_717 import code_at, summarize


class StaticTests(unittest.TestCase):
    def test_invalid_elf_rejected(self):
        with self.assertRaises(ValueError):
            code_at(b"not ELF", 0x80000000, 4)

    def test_exact_executable_address(self):
        blob = bytearray(132)
        blob[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<HHIQQQIHHHHHH", blob, 16,
                         2, 243, 1, 0x80000000, 0, 64, 0, 64, 0, 0, 64, 1, 0)
        struct.pack_into("<IIQQQQIIQQ", blob, 64,
                         0, 1, 6, 0x80000000, 128, 4, 0, 0, 4, 0)
        blob[128:] = b"\xf3\x99\x55\x30"
        self.assertEqual(code_at(blob, 0x80000000, 4), b"\xf3\x99\x55\x30")
        with self.assertRaises(ValueError):
            code_at(blob, 0x80000002, 4)

    def test_request_is_not_retired_custom(self):
        row = dict(event="retire", cycle="2", order="0", rd="0", rd_wdata="0",
                   pc="800001ee", insn="f1e58593", trap="0")
        request = dict(row, event="cvx_req", cycle="3", insn="00b5205b")
        result = summarize([row, request])
        self.assertEqual(result["retired_custom"], [])
        self.assertEqual(result["events"]["cvx_req"], 1)


if __name__ == "__main__":
    unittest.main()
