import unittest
from value_reuse_audit import schedule


class ScheduleTest(unittest.TestCase):
    def test_accepted_slice(self):
        s=schedule([17,18,19,20],2,1)
        self.assertEqual((s['commands'],s['value_decodes'],s['eliminated_decodes']),(4,20,0))

    def test_multiple_groups(self):
        s=schedule(list(range(1,21)),2,8)
        self.assertEqual((s['commands'],s['value_decodes'],s['bounded_cache_value_decodes']),
                         (160,480,160))
        self.assertEqual(s['pv_updates'],3360)

    def test_long_nonmonotone(self):
        visible=[65,1,33,32,20]
        s=schedule(visible,3,2)
        visits=[]
        rows=[n for n in visible for _ in range(3)]
        for i in range(0,len(rows),8):visits+=list(range(max(rows[i:i+8])))
        cached=set();calls=0
        for t in visits:
            if t>=32 or t not in cached:calls+=1
            if t<32:cached.add(t)
        self.assertEqual(s['bounded_cache_value_decodes'],calls*2)
        self.assertEqual(s['value_decodes'],len(visits)*2)


if __name__=='__main__':unittest.main()
