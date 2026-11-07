import unittest
from complete_f16_native import function_bytes


class IncludedAssemblyIdentity(unittest.TestCase):
    def test_function_bytes_ignore_only_unowned_alignment_padding(self):
        actual=function_bytes(b'abcXYZ', 'a T 0 3\nb T 3 3', ('a','b'))
        separate={**function_bytes(b'abc\x01\x00','a T 0 3',('a',),True),
                  **function_bytes(b'XYZ','b T 0 3',('b',),True)}
        self.assertEqual(actual,separate)
        self.assertNotEqual(actual,function_bytes(b'abcXWZ','a T 0 3\nb T 3 3',('a','b')))

    def test_missing_duplicate_nontext_unsized_or_bounds_rejected(self):
        for text in ('a T 0 3\na T 0 3','a D 0 3','a T 0','a T 0 4','a T 0 0','b T 0 3'):
            with self.subTest(text=text),self.assertRaises(ValueError):function_bytes(b'abc',text,('a',))
        with self.assertRaises(ValueError):function_bytes(b'abcXYZ','a T 0 3\nb T 3 3',('a',),True)


if __name__=='__main__':unittest.main()
