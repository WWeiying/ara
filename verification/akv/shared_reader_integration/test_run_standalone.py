import unittest
from run_standalone import check_log


class StandaloneAcceptanceTests(unittest.TestCase):
    def test_complete_qbs_collection(self):
        marker='QBS engine PASS: 36 functional cases plus four fault classes'
        self.assertEqual(check_log(marker,'qbs',0),marker)
        for text,code in ((marker,1),(marker.replace('36','35'),0),
                          (marker+'\n'+marker,0),(marker+'\nFatal: bad',0)):
            with self.assertRaises(ValueError):
                check_log(text,'qbs',code)


if __name__=='__main__':
    unittest.main()
