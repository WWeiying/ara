import itertools
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import prepare_fast as fast


class Fast(unittest.TestCase):
    def test_only_bounds_and_live_cursor_change(self):
        for identity in fast.SELECTED:
            source = (fast.BASE / 'prepared' / identity / 'case.c').read_text()
            changed = fast.adapt(source, identity)
            normalize = lambda s: re.sub(r'for\(unsigned \w+=\d+;[^;]+;\+\+\w+\)', 'FOR', s)
            if identity == 'reduction_fflags':
                changed = changed.replace('\n        /* 285 preceding fixture reads incremented index only. */\n'
                                          '        index += ((4*4+3)*5+0)*3+0;', '')
            self.assertEqual(normalize(source), normalize(changed))
            condition = ' && '.join(f'{k}=={v}' for k, v in fast.SELECTED[identity].items())
            with self.assertRaises(ValueError):
                fast.adapt(source.replace(condition, condition + ' && 1'), identity)

    def test_original_cursor_and_unique_tuple(self):
        rows = list(itertools.product(range(7), range(4), range(5), range(3)))
        self.assertEqual(rows.index((4, 3, 0, 0)), 285)
        self.assertEqual(3360 + 3 * 420 + rows.index((4, 3, 0, 0)), 4905)
        for name in ('maskslide', 'gather_original'):
            tuples = itertools.product(range(3), range(21), range(8), range(7), range(4), range(4))
            match = tuple(fast.SELECTED[name].values())
            self.assertEqual(sum(t == match for t in tuples), 1)

    def test_host_call_boundary_equivalence(self):
        # Scalar-only mock captures inputs/oracle state, not an RVV implementation.
        records = json.loads((fast.BASE / 'prepared/provenance.json').read_text())['cases']
        for identity in fast.SELECTED:
            directory = fast.BASE / 'prepared' / identity
            source = (directory / 'case.c').read_text()
            reduction = identity == 'reduction_fflags'
            for vlenb in (64, 128):
                traces = []
                for body in (source, fast.adapt(source, identity)):
                    body = body.replace('__asm__ volatile("csrr %0,vlenb":"=r"(max_start));',
                                        f'max_start={vlenb};')
                    body = body.replace('__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));',
                                        f'vlenb={vlenb};')
                    if reduction:
                        body = body.replace('for(unsigned i=0;i<144;++i)output[i]=0x5b;',
                            'printf("FIXTURE %llx %u\\n", (unsigned long long)wanted.bits,wanted.flags);\n'
                            '                for(unsigned i=0;i<144;++i)output[i]=0x5b;')
                    arrays = ('input', 'seed', 'output', 'mask') if reduction else (
                        'input', 'indices', 'indices16', 'output', 'predicate')
                    capture = ''.join(f'dump({a},sizeof({a}));' for a in arrays)
                    support = '''
static unsigned calls;
static void dump(const void *p,unsigned n){
 const unsigned char *b=p;
 for(unsigned i=0;i<n;++i)printf("%02x",b[i]);
 putchar('\\n');
}
long replay_write(long nr,long fd,long p,long n){
 (void)nr;(void)fd;fwrite((void*)p,1,n,stdout);return n;
}
'''
                    support += f'unsigned long capacity(void){{return {vlenb*8//(32 if reduction else 16)};}}\n'
                    for op in range(3 if reduction else 21):
                        support += (f'unsigned long op_{op}(const void*a,const void*b,void*c,'
                                    'unsigned long vl,unsigned long cap,const void*m,unsigned long x,unsigned long y){'
                                    f'++calls;printf("MOCK_CALL {op} %lu %lu %lu %lu\\n",vl,cap,x,y);'
                                    + capture + 'return 0;}\n')
                    support += f'int main(void){{int rc={identity}_main();printf("RETURN %d CALLS %u\\n",rc,calls);return calls!=1;}}'
                    with tempfile.TemporaryDirectory(dir=fast.HERE) as temp:
                        path = Path(temp)
                        (path / 'test.c').write_text('#include <stdio.h>\n' + body + support)
                        defines = next(r['defines'] for r in records if r['id'] == identity)
                        command = ['cc', '-O0', *['-D' + d for d in defines],
                                   '-I' + str(directory / 'original'),
                                   str(path / 'test.c'), '-o', str(path / 'test')]
                        compiled = subprocess.run(command, capture_output=True, text=True)
                        self.assertEqual(compiled.returncode, 0, compiled.stderr)
                        traces.append(subprocess.check_output([str(path / 'test')], timeout=5))
                self.assertEqual(traces[0], traces[1], (identity, vlenb))
                self.assertEqual(traces[0].count(b'MOCK_CALL'), 1)


if __name__ == '__main__':
    unittest.main()
