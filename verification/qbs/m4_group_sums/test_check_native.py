import unittest
from check_native import check_log


def fixture():
    signature=14695981039346656037
    for _ in range(7008):signature=(signature*1099511628211)&((1<<64)-1)
    lines=['M4_SUMS_SCOPE rows=4 k=1536 bytes=7008 whole_prepare=1 trials=4']
    for i,c in enumerate((0,1,1,0)):
        lines.append(f'M4_SUMS_TRIAL id={i} candidate={c} cycles={100 if c else 200} vector=1 fcsr=9 vcsr=5 errors=0 signature={signature:016x}')
    return '\n'.join(lines+['M4_SUMS_RESULT trials=4 errors=0'])


class NativeCheck(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(check_log(fixture(),bytes(7008))['speedup'],2)

    def test_mutations(self):
        t=fixture()
        for x in (t.replace('vector=1','vector=0',1),t.replace('errors=0','errors=1',1),
                  t.replace('id=1 candidate=1','id=1 candidate=0'),
                  t.replace('signature=','signature=0',1),
                  t.replace('M4_SUMS_RESULT trials=4 errors=0','')):
            with self.assertRaises(ValueError):check_log(x,bytes(7008))
        lines=t.splitlines();lines[0],lines[1]=lines[1],lines[0]
        with self.assertRaises(ValueError):check_log('\n'.join(lines),bytes(7008))


if __name__=='__main__':unittest.main()
