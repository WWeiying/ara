import unittest

from export_m4_prepare_oracle import check_output


class OracleProtocolTests(unittest.TestCase):
    def protocol(self):
        data = bytes(i % 256 for i in range(3808))
        lines = ["M4_ORACLE_BEGIN m=4 k=896 elements=3584 bytes=3808 vlen=1024",
                 "M4_ORACLE_CSR initial_fcsr=0 initial_vcsr=5 fcsr=1 vcsr=5"]
        lines += [f"M4_ORACLE_HEX offset={i} data={data[i:i+64].hex()}"
                  for i in range(0, 3808, 64)]
        lines += ["M4_ORACLE_END bytes=3808", "M4_ORACLE_EXIT=0"]
        return data, "\n".join(lines) + "\n"

    def test_complete(self):
        data, text = self.protocol()
        result, state = check_output(text)
        self.assertEqual(result, data)
        self.assertEqual(state["fcsr"], 1)

    def test_reject(self):
        _, text = self.protocol()
        for bad in (text.replace("offset=64 ", "offset=65 "),
                    text.replace("M4_ORACLE_EXIT=0", "M4_ORACLE_EXIT=1"),
                    text.replace("fcsr=1 vcsr=5", "fcsr=33 vcsr=5"),
                    text.replace("vlen=1024", "vlen=128"),
                    text + text, text + "Kernel panic\n", text[:-20]):
            with self.subTest(text=bad), self.assertRaises(ValueError):
                check_output(bad)


if __name__ == "__main__":
    unittest.main()
