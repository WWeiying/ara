#!/usr/bin/env python3
"""Generate a small new directed regression, not an archived Linux replay."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("parent_scenarios", HERE.parent / "scenarios.py")
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
base = parent.base


def cases():
    result = []
    for op in ("vmseq", "vmsne", "vmslt", "vmsltu"):
        for dest, triple in ((8, False), (16, False), (8, True)):
            result.append(dict(op=op, dest=dest, triple=triple, masked=True,
                               start=3, vl=37, mixed=False, carry=False))
    for op in ("vmadc", "vmsbc"):
        for carry in (False, True):
            # Mask-producing carry/borrow instructions prohibit data-source overlap.
            result.append(dict(op=op, dest=24, triple=False, masked=False,
                               start=1, vl=63, mixed=False, carry=carry))
    for op in ("vmseq", "vmsltu"):
        result.append(dict(op=op, dest=24, triple=False, masked=False,
                           start=0, vl=64, mixed=False, carry=False))
    for dest in (8, 16):
        result.append(dict(op="vmsltu", dest=dest, triple=False, masked=True,
                           start=33, vl=61, mixed=True, carry=False))
    return [dict(c, context=context, id=len(result) * context + i)
            for context in (0, 1) for i, c in enumerate(result)]


def assembly(c):
    src1 = 8 if c["triple"] else 16
    lines = [".text", ".balign 4", f'.global neighbor_{c["id"]}',
             f'neighbor_{c["id"]}:', "addi sp,sp,-16", "sd ra,0(sp)",
             "vsetvli t0,zero,e32,m2,tu,mu", "vle32.v v8,(a0)",
             "vle32.v v16,(a1)"]
    if c["mixed"]:
        # Reload the same architectural bytes at a different physical EEW.
        lines += ["vsetvli t0,zero,e8,m1,tu,mu", "addi t1,a0,128",
                  "vle8.v v9,(t1)", "addi t1,a1,128", "vle8.v v17,(t1)"]
    if c["dest"] == 24:
        lines += ["vsetvli t0,zero,e8,m1,tu,mu", "vle8.v v24,(a2)"]
    lines += ["vsetvli t0,zero,e32,m2,tu,mu", "vlm.v v0,(a3)",
              f'li t0,{c["vl"]}', "vsetvli t0,t0,e32,m2,tu,mu",
              f'li t0,{c["start"]}', "csrw vstart,t0"]
    if c["context"]:
        lines += ["call context_roundtrip"]
    lines += ["csrwi fflags,1"]
    suffix = ",v0.t" if c["masked"] else ",v0" if c["carry"] else ""
    form = "vvm" if c["carry"] else "vv"
    lines += [f'{c["op"]}.{form} v{c["dest"]},v8,v{src1}{suffix}',
              "csrr t2,vstart", "csrr t1,fflags", "slli t1,t1,32",
              "or a0,t2,t1", "vsetvli t0,zero,e32,m2,tu,mu",
              f'vsm.v v{c["dest"]},(a4)', "csrr zero,vl", "fence rw,rw",
              "ld ra,0(sp)", "addi sp,sp,16", "ret"]
    return "\n".join(lines) + "\n"


C_SOURCE = r'''#include <stdint.h>
#include <stddef.h>
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
extern volatile unsigned long replay_case;
typedef unsigned long (*operation)(const void *,const void *,const void *,const void *,void *);
struct test { operation run; unsigned op,dest,triple,masked,start,vl,mixed,carry,context; };
@DECLS@
static const struct test tests[] = {
@TESTS@
};
static uint32_t a[64] __attribute__((aligned(64)));
static uint32_t b[64] __attribute__((aligned(64)));
static uint8_t old[128] __attribute__((aligned(64)));
static uint8_t mask[128] __attribute__((aligned(64)));
static uint8_t output[10] __attribute__((aligned(64)));
static const uint32_t values[] = {0,1,0xffffffffU,0x80000000U,0x7fffffffU,
    0xfffffffeU,0x12345678U,0x87654321U};
static unsigned bit(const uint8_t *p,unsigned i) { return (p[i/8]>>(i%8))&1; }
static unsigned wanted(const struct test *t,unsigned i) {
    uint32_t x=a[i], y=t->triple ? a[i] : b[i];
    unsigned carry=t->carry ? bit(mask,i):0;
    switch(t->op) {
    case 0: return x==y;
    case 1: return x!=y;
    case 2: return (int32_t)x<(int32_t)y;
    case 3: return x<y;
    case 4: return (((uint64_t)x+y+carry)>>32)&1;
    default: return (uint64_t)x<((uint64_t)y+carry);
    }
}
static unsigned validate(const struct test *t,unsigned long status) {
    const uint8_t *prior=t->dest==8 ? (const uint8_t *)a:
                         t->dest==16 ? (const uint8_t *)b:old;
    unsigned errors=status!=((unsigned long)1<<32);
    errors+=output[0]!=0x5b || output[9]!=0x5b;
    for(unsigned i=0;i<64;++i) {
        unsigned actual=bit(output+1,i), before=bit(prior,i), expected=wanted(t,i);
        unsigned active=i>=t->start && i<t->vl && (!t->masked || bit(mask,i));
        if(active) errors+=actual!=expected;
        else if(i<t->start) errors+=actual!=before;
        else if(i<t->vl) {
            /* Different-EEW compare aliases permit mask-agnostic ones. */
            errors+=actual!=before && !(t->dest!=24 && actual==1);
        } else {
            /* Mask tails may retain old bits, become ones, or compute to VLMAX. */
            errors+=actual!=before && actual!=1 && actual!=expected;
        }
    }
    return errors;
}
int main(void) {
    unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    if(vlenb!=128) return 90;
    unsigned negatives=0;
    for(unsigned n=0;n<sizeof(tests)/sizeof(tests[0]);++n) {
        const struct test *t=tests+n;
        replay_case=n;
        for(unsigned i=0;i<64;++i) {
            a[i]=values[(i*5+i/8)%8]; b[i]=values[(i*3+2+i/7)%8];
        }
        for(unsigned i=0;i<128;++i) {old[i]=(uint8_t)(0x5b^(i*13));mask[i]=0xaa;}
        for(unsigned i=0;i<10;++i) output[i]=0x5b;
        unsigned long status=t->run(a,b,old,mask,output+1);
        unsigned errors=validate(t,status);
        if(errors) return replay_mismatch(n,0,0,errors);
        unsigned active=t->start;
        while(t->masked && !bit(mask,active)) ++active;
        output[1+active/8]^=1U<<(active%8);
        if(!validate(t,status)) return 91;
        ++negatives;
        output[1+active/8]^=1U<<(active%8);
        if(!validate(t,status^((unsigned long)16<<32))) return 92;
        ++negatives;
        output[0]^=1;
        if(!validate(t,status)) return 93;
        ++negatives;
        output[0]^=1;
        if(validate(t,status)) return 94;
    }
    if(negatives!=120) return 95;
    replay_text("NEIGHBORS_INTEGER_PASS cases=40 errors=0\n");
    replay_text("NEIGHBORS_ORACLE_NEGATIVE_PASS checks=120\n");
    replay_text("BOARD_REPLAY_PASS\n");
    return 0;
}
'''


def main():
    out = HERE / "build01"
    out.mkdir(exist_ok=False)
    configs = cases()
    assert len(configs) == 40
    ops = ["vmseq", "vmsne", "vmslt", "vmsltu", "vmadc", "vmsbc"]
    decls, rows = [], []
    for c in configs:
        decls.append(f'extern unsigned long neighbor_{c["id"]}(const void *,const void *,const void *,const void *,void *);')
        fields = [ops.index(c["op"])] + [int(c[k]) for k in
                  ("dest", "triple", "masked", "start", "vl", "mixed", "carry", "context")]
        rows.append('    {neighbor_'+str(c['id'])+','+','.join(map(str,fields))+'},')
    (out / "main.c").write_text(C_SOURCE.replace("@DECLS@", "\n".join(decls)).replace("@TESTS@", "\n".join(rows)))
    (out / "scenario.S").write_text(''.join(assembly(c) for c in configs)+parent.context_assembly())
    pins = {str(HERE / "prepare.py"): base.sha(HERE / "prepare.py"),
            str(HERE.parent / "scenarios.py"): base.sha(HERE.parent / "scenarios.py")}
    for name in ("startup.S", "runtime.c", "replay.ld"):
        src = base.RUNTIME / name
        shutil.copyfile(src, out / name)
        pins[str(src)] = base.sha(src)
    flags = ['-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static','-ffreestanding',
             '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
             '-msmall-data-limit=0','-Wl,--build-id=none','-Wall','-Wextra','-Werror',
             '-mcmodel=medany','-ffunction-sections','-fdata-sections','-Wl,--gc-sections']
    for backend in ("soc", "spike"):
        cmd = [base.helper.CC,*flags,'-T',out/'replay.ld',
               *(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
               *[out/n for n in ('main.c','scenario.S','startup.S','runtime.c')],
               '-lgcc','-o',out/(backend+'.elf')]
        r = base.command(cmd,out,backend+'_compile')
        assert r['returncode']==0, (out/(backend+'_compile.log')).read_text()
    nm = subprocess.check_output([str(base.helper.CC.with_name('riscv64-unknown-elf-nm')),
                                  '-n',out/'spike.elf'],text=True)
    symbols = {r.split()[2]:r.split()[0] for r in nm.splitlines() if len(r.split())==3}
    (out/'spike.cmd').write_text('until pc 0 '+symbols['replay_exit']+'\nreg 0 a0\nstr '+symbols['replay_log']+'\nrs\n')
    r = base.command([base.helper.SPIKE,'-d','--debug-cmd='+str(out/'spike.cmd'),
                      '--isa=rv64gcv_zfh_zvfh_zvl1024b','-m2',out/'spike.elf'],out,'spike')
    markers = ['NEIGHBORS_INTEGER_PASS cases=40 errors=0',
               'NEIGHBORS_ORACLE_NEGATIVE_PASS checks=120','BOARD_REPLAY_PASS']
    log = (out/'spike.log').read_text()
    assert r['returncode']==0 and all(m in log for m in markers), log
    entry = dict(directory=str(out),elf=str(out/'soc.elf'),elf_sha256=base.sha(out/'soc.elf'),
                 pass_markers=markers,reference_elf_sha256=base.sha(out/'spike.elf'),
                 reference='Spike PASS; not DUT validation',cases=configs)
    base.save(HERE/'programs.json',dict(programs={'fp_compare_integer_neighbors':entry},pins=pins,
        scope='New directed e32/m2 bare-metal regression, no original Linux ELF attribution. '
              'No VCS run. VMADC/VMSBC data-source aliases excluded as illegal. '
              'Context assembly imported unchanged from parent scenarios.py.',
        files={str(p):base.sha(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(manifest=str(HERE/'programs.json'),**{k:entry[k] for k in
                          ('elf','elf_sha256','pass_markers')}),indent=2))


if __name__ == '__main__':
    main()
