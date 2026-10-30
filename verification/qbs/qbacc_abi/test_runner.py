import unittest

import run


class CheckerTests(unittest.TestCase):
    def test_c_mutations(self):
        lines = [f"CAP vlen={v} index={i} word=0000000000000000"
                 for v in run.VLENS for i in range(256) if i != 4]
        lines.append(run.C_PASS)
        log = "\n".join(lines) + "\n"
        self.assertEqual(len(run.check_c(log)), 2295)
        for bad in (log.replace(run.C_PASS, run.C_PASS + "_BOGUS"),
                    log + "extra\n", "\n".join(lines[1:]),
                    log.replace("index=0 ", "index=4 "),
                    log.replace("CAP vlen=0", "CAP extra=1 vlen=0"),
                    log.replace("word=0000000000000000", "word=xxxxxxxxxxxxxxxx", 1)):
            with self.subTest(bad=bad[:80]), self.assertRaises(ValueError):
                run.check_c(bad)

    def test_sv_mutations(self):
        run.check_sv("VCS banner\n" + run.SV_PASS + "\n$finish\n")
        for bad in ("", run.SV_PASS + "_BOGUS", run.SV_PASS + " extra=1",
                    run.SV_PASS + "\n" + run.SV_PASS,
                    run.SV_PASS + "\nError: mismatch",
                    run.SV_PASS + "\nFatal: mismatch"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run.check_sv(bad)


if __name__ == "__main__":
    unittest.main()
