#!/usr/bin/env python3
"""Independent FP16 model against the unchanged C oracle; no ISA execution."""
import subprocess
import sys
sys.dont_write_bytecode=True
from software_prepare import HERE,NAME,base,DEFS,save,sha
from model import require
sys.path.insert(0,str(HERE.parent/'fp_comparison_original'))
from prepare_prefix import HOST as OLD_HOST

def main():
    out=HERE/'host01';out.mkdir(exist_ok=False)
    host=OLD_HOST.replace('b[op<4?i:0]','op<4?b[i]:0x7e00')
    start=host.index('    if(calls==HOST_CALLS){')
    end=host.index('\n}',start)
    host=host[:start]+'''
    if(calls==HOST_CALLS){
        if(HOST_MUTATION==1)o[0]^=1;
        if(HOST_MUTATION==2)flags^=16;
        if(HOST_MUTATION==3)o[-1]^=1;
        if(HOST_MUTATION==4)o[2]^=1;
        if(HOST_MUTATION==8)o[0]|=1; /* Wrong raw scalar zero equality. */
    }
    if(HOST_MUTATION==7 && calls==1)o[0]^=1; /* VL0 is not mask agnostic. */
    return ((unsigned long)flags<<32)|(HOST_MUTATION==5 && calls==HOST_CALLS);
'''+host[end:]
    results=[]
    for mutation in range(9):
        p=out/f'mutation{mutation}.c'
        p.write_text((HERE/'software/case.c').read_text()+'\n'+host+'\n'+'\n'.join(
            f'unsigned long op_{i}(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){{return emulate({i},a,b,o,vl,cap,m,start,flags);}}' for i in range(10))+
            '\nint main(void){for(unsigned op=0;op<6;++op)for(unsigned a=0;a<16;++a)for(unsigned b=0;b<16;++b){struct fixture r=independent(op,inputs[a],inputs[b]);if(r.bit!=expected[op][a][b].bit||r.flags!=expected[op][a][b].flags)abort();}return '+NAME+'_main();}\n')
        exe=p.with_suffix('');base.command(['/usr/bin/gcc','-O2',*['-D'+d for d in DEFS],'-DHOST_CAP=16','-DHOST_CALLS=265',f'-DHOST_MUTATION={mutation}','-I'+str(HERE/'software/original'),p,'-o',exe],exe.with_suffix('.compile.log'))
        r=subprocess.run([exe],capture_output=True,text=True,timeout=10);exe.with_suffix('.log').write_text(r.stdout+r.stderr)
        positive=mutation in (0,6)
        require((r.returncode==0 and 'cases=265 errors=0' in r.stdout) if positive else (r.returncode==1 and 'RVV_FP_COMPARE_DETAIL' in r.stdout),'Host mutation '+str(mutation))
        results.append(dict(mutation=mutation,status='PASS' if positive else 'EXPECTED_REJECTION',returncode=r.returncode,log_sha256=sha(exe.with_suffix('.log'))))
    save(out/'result.json',dict(status='PASS_HOST_2_POSITIVE_7_NEGATIVE',full_fixture_entries=1536,results=results))
    print('PASS_HOST_2_POSITIVE_7_NEGATIVE')
if __name__=='__main__':main()
