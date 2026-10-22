from unittest import mock
import unittest
import bind_operand_index_snapshot_branch_targets as b


class Binding(unittest.TestCase):
    def fixture(self):
        point = dict(raw_index=526,native_id='104',vector='7',attributes={'chksum':'3186254472'},
                     native_vector={'vector':'00--------------0111000000000'},
                     expressions=[dict(id='518',index='12',exprstr='requester_metadata_q[6].source_snapshot_replay')])
        return dict(width=752,checksum='1229254119',bits='0'),point

    def test_exact(self):
        row,point = self.fixture()
        with mock.patch.object(b,'points',return_value=[point]):
            self.assertEqual(b.bind(row,{'chksum':'1229254119'})['raw_index'],526)

    def test_already_hit(self):
        row,point = self.fixture()
        row['bits'] = hex(1 << (752-1-526))
        with mock.patch.object(b,'points',return_value=[point]),self.assertRaisesRegex(ValueError,'already hit'):
            b.bind(row,{'chksum':'1229254119'})

    def test_checksum_width_id_and_false_arm(self):
        for key,value in (('width',751),('checksum',None)):
            row,point = self.fixture()
            row[key] = value
            with self.assertRaises(ValueError):
                b.bind(row,{'chksum':'1229254119'})
        for field,value in (('native_id','105'),('vector','6')):
            row,point = self.fixture()
            point[field] = value
            with mock.patch.object(b,'points',return_value=[point]),self.assertRaises(ValueError):
                b.bind(row,{'chksum':'1229254119'})
        row,point = self.fixture()
        point['native_vector']['vector'] = '0'*29
        with mock.patch.object(b,'points',return_value=[point]),self.assertRaisesRegex(ValueError,'true arm'):
            b.bind(row,{'chksum':'1229254119'})


if __name__ == '__main__':
    unittest.main()
