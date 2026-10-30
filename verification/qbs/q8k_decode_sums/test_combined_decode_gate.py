import unittest
from combined_decode_gate import check_dispatch,sources


class CombinedTest(unittest.TestCase):
    def test_dispatch_reconciles(self):
        activity={str(m):dict(groups=[dict(m=1,calls=n),dict(m=4,calls=10)]) for m,n in ((0,7),(1,3))}
        text='Q8K_COMBINED_DISPATCH mode=0 original=7 installed=0\nQ8K_COMBINED_DISPATCH mode=1 original=0 installed=3\n'
        self.assertEqual(len(check_dispatch(text,activity)),2)
        for bad in (text+text,text.replace('installed=3','installed=2'),
                    text.replace('original=7 installed=0','original=0 installed=7')):
            with self.assertRaises(ValueError):check_dispatch(bad,activity)

    def test_original_body_extracted_without_modification(self):
        body='void quantize_row_q8_K(const float *x,void *y,int64_t k) { mock(x,y,k); }\n'
        original,wrapper=sources('ignored\n'+body+'//===================================== Dot products\n')
        self.assertTrue(original.endswith(body.replace('void quantize_row_q8_K(','void decode_original(')))
        self.assertIn('__real_quantize_row_q8_K(x,y,k)',wrapper)
        self.assertIn('else abort()',wrapper)


if __name__=='__main__':unittest.main()
