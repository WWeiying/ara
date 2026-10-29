import unittest
from archive_identity import HEADER,members


def archive(payload=b'abc',mtime=b'100',name=b'same.o/'):
    header=HEADER.pack(name.ljust(16),mtime.ljust(12),b'1002'.ljust(6),b'1001'.ljust(6),
        b'100660'.ljust(8),str(len(payload)).encode().ljust(10),b'`\n')
    return b'!<arch>\n'+header+payload+(b'\n' if len(payload)&1 else b'')


class ArchiveTest(unittest.TestCase):
    def test_timestamp_only(self):
        self.assertEqual(members(archive()),members(archive(mtime=b'200')))
        self.assertNotEqual(members(archive()),members(archive(payload=b'abd')))
        self.assertNotEqual(members(archive()),members(archive(name=b'other.o/')))
        self.assertNotEqual(members(archive()),members(archive().replace(b'3         ',b'0000000003',1)))

    def test_duplicate_members(self):
        raw=archive()+archive(payload=b'def')[8:]
        result=members(raw)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['name'],result[1]['name'])
        self.assertNotEqual(result[0]['sha256'],result[1]['sha256'])

    def test_reject_corruption(self):
        for raw in (b'!<thin>\n',archive()[:-1],archive()[:-3],archive()+b'x',
                    archive().replace(b'`\n',b'xx',1)):
            with self.subTest(raw=raw[:8]),self.assertRaises(ValueError):members(raw)


if __name__=='__main__':unittest.main()
