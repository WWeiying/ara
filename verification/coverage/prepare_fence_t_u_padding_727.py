"""Only rebind the frozen source review to formal727; no build or EDA."""
import inspect
from pathlib import Path
import sys
import prepare_fence_t_u_padding_static as old

SOURCE_SHA='37a5358d0aefb2026dd7f5ce30013d6cfcdeee64db6fd55c30f8251496663563'
BASE=old.OUT/'gap106-offline-admitted-727-parent-20261006-01'
BASE_SHA='918a5cb4b471e1106a10b4e1c76eb996e9803a44c8d4566c0a038d3b697e29d2'
ROOT=old.ROOT
BUILD=ROOT/'verification/coverage/fence_t_u_padding_build.sh'


def adapted():
    old.require(old.sha(Path(old.__file__))==SOURCE_SHA,'Frozen static source drift')
    source=inspect.getsource(old.prepare)
    additions="""pin(Path(old.__file__),SOURCE_SHA)
    pin(BUILD)
    sourcepin_path=ROOT/'hardware/deps/cva6/core/pmp/src/pmp.sv'
    pin(sourcepin_path,sourcepins[str(sourcepin_path)])
    for name in ('printf.c','string.c','serial.c','util.c','print_trap_cause.c','link.ld'):
        pin(ROOT/'apps/common'/name)
    for name in ('clang','ld.lld','llvm-objdump','llvm-readobj','llvm-readelf'):
        pin(ROOT/'install/riscv-llvm/bin'/name)
    pin(Path(__file__))"""
    changes=[('==726','==727'),("'Wrong admitted sample population'","'Wrong admitted727 population'"),
             ("require(not int(record['bits'],16)&(1<<(record['width']-1-index)),'Target already hit; reassess')",
              "hit=bool(int(record['bits'],16)&(1<<(record['width']-1-index)))\n                witness=instance=='controller_i' and metric=='branch' and index in (33,36)\n                require(witness or not hit,'Primary target already hit; reassess')"),
             ('hit726=False',"hit727=hit,role='corroborating_witness' if witness else 'unhit_candidate'"),
             ('pin(Path(__file__))',additions),
             ('counts=dict(cond=11,branch=2,line=1),',
              'counts=dict(cond=11,branch=2,line=1),relative_admission_population=727,source_static_preflight=True,ELF_preflight=False,')]
    for before,after in changes:
        old.require(source.count(before)==1,'Exact rebind boundary differs: '+before)
        source=source.replace(before,after)
    # Keep the design BUILD global from the predecessor, not the build-command path.
    namespace=dict(old.prepare.__globals__,old=old,SOURCE_SHA=SOURCE_SHA,BASE=BASE,
                   BASE_SHA=BASE_SHA,__file__=__file__)
    source=source.replace('pin(BUILD)\n',"pin(ROOT/'verification/coverage/fence_t_u_padding_build.sh')\n")
    exec(compile(source,__file__+':727-only','exec'),namespace)
    return namespace['prepare']


if __name__=='__main__':
    old.require(len(sys.argv)==2,'Only fresh review output argument allowed')
    adapted()(Path(sys.argv[1]).absolute())
