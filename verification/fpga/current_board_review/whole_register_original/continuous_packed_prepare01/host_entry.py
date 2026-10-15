"""Actual converted whole main on Host; original helpers replaced only by declared mocks."""
import shutil
import subprocess
import time
from prepare import HERE, read, save, require, command


def main():
    out=HERE/'host_entry01';out.mkdir()
    source=(HERE/'case.c').read_text()
    needle='unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));'
    require(source.count(needle)==1,'Only Host capacity instruction replacement')
    source=source.replace(needle,'unsigned long vlenb=128;')
    cases=read(HERE/'tuples.json')['cases']
    rows=','.join('{'+','.join(str(c[k]) for k in ('seed','op','mode','start','bytes','registers'))+'}' for c in cases)
    prefix='#include <assert.h>\n#include <stdio.h>\n'
    suffix=r'''
struct Row {unsigned seed,op,mode,start,bytes,n;};
static const struct Row rows[]={ROWS};
static unsigned ordinal;
long replay_write(long no,long fd,long addr,long len){assert(no==64&&fd==1);return fwrite((void*)addr,1,len,stdout);}
static unsigned long mock(unsigned op,const void *iv,void *ov,unsigned long start,unsigned long mode){
    assert(ordinal<1134);struct Row r=rows[ordinal++];
    assert(op==r.op&&start==r.start&&mode==r.mode);
    const uint8_t *in=iv;uint8_t *out=ov;
    for(unsigned i=0;i<1024;++i)assert(in[i]==(uint8_t)(i*37+r.seed*71+3));
    for(unsigned i=0;i<1088;++i)assert(output[i]==0x5b);
    for(unsigned i=start*r.bytes;i<r.n*128;++i)out[i]=in[i];
    return start<<32;
}
'''.replace('ROWS',rows)
    for op in range(20):
        suffix+='unsigned long op_%d(const void *i,void *o,unsigned long s,unsigned long m){return mock(%d,i,o,s,m);}\n'%(op,op)
    suffix+='int main(void){int rc=whole_original_main();assert(rc==0&&ordinal==1134);return rc;}\n'
    with (out/'entry.c').open('x') as f:f.write(prefix+source+suffix)
    cc=shutil.which('gcc');require(cc,'Host compiler')
    flags=['-O2','-fno-tree-vectorize','-fno-tree-slp-vectorize','-fstrict-aliasing',
           '-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-fno-sanitize-recover=all',
           '-Wall','-Wextra','-Werror','-DDETAIL_BYTES=1','-DWHOLE_OP_BEGIN=0','-DWHOLE_OP_END=20']
    command([cc,*flags,'-I'+str(HERE),'-I'+str(HERE/'original'),out/'entry.c','-o',out/'entry'],out/'compile.log',60)
    command([out/'entry'],out/'run.log',60)
    require((out/'run.log').read_text()=='RVV_WHOLE_PASS cases=1134 skips=366 errors=0\n','Actual entry exact summary')
    # Prove the same instrumentation really traps UB without the unavailable runtime library.
    with (out/'ub_probe.c').open('x') as f:f.write('int main(void){volatile unsigned n=64;volatile unsigned long x=1;return (int)(x<<n);}\n')
    command([cc,*flags,out/'ub_probe.c','-o',out/'ub_probe'],out/'ub_compile.log',60)
    began=time.monotonic()
    p=subprocess.Popen([str(out/'ub_probe')],cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    output,_=p.communicate(timeout=10)
    save(out/'ub_exit.json',dict(command=[str(out/'ub_probe')],pid=p.pid,returncode=p.returncode,
                               elapsed_s=time.monotonic()-began,output=output.decode(),expected_nonzero=True))
    require(p.returncode<0,'Actual undefined shift must trap')
    command([__import__('sys').executable,'-B',HERE/'test_gate.py'],out/'gate.log',30)
    save(out/'result.json',dict(status='HOST_ACTUAL_MAIN_AND_GATES_PASS_NOT_REFERENCE',
         actual_main=read(out/'run.log.exit.json'),fresh_gate=read(out/'gate.log.exit.json'),
         ub_trap=read(out/'ub_exit.json'),mock_helpers=True,capacity_replaced_for_Host_only=128))


if __name__=='__main__':main()
