import unittest

from build import DEMANGLED_SPECIALIZATION, verify_map


class LinkMapTests(unittest.TestCase):
    def test_exact_owner(self):
        verify_map(DEMANGLED_SPECIALIZATION + " tile-support/ggml/src/libggml-cpu.a(repack.cpp.o)\n")

    def test_wrong_missing_duplicate_owner(self):
        good = DEMANGLED_SPECIALIZATION + " tile-support/ggml/src/libggml-cpu.a(repack.cpp.o)\n"
        for text in ("", good + good, good.replace("repack.cpp.o", "test.cpp.o"),
                     good.replace("libggml-cpu.a", "libfake.a"),
                     good.replace(DEMANGLED_SPECIALIZATION, DEMANGLED_SPECIALIZATION + "_BOGUS")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                verify_map(text)


if __name__ == "__main__":
    unittest.main()
