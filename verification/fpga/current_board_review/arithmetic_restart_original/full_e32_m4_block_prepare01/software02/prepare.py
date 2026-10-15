"""One reviewed comparator, original fixed flags, Host and two ELF builds only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'software01'
A=HERE.parents[1]
spec=importlib.util.spec_from_file_location('sealed_prepare',OLD/'prepare.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.HERE=HERE
read=lambda p:json.loads(p.read_text())
require,sha,save,emit,run=base.require,base.sha,base.save,base.emit,base.run

def main():
    source=A/'full_e32_m4_integrated_source_proposal01'
    proposal=HERE.parent/'static_sticky01'
    review=A/'full_e32_m4_static_review01/STICKY_SOURCE_REVIEW.json'
    require(sha(review)=='fe72d121cc52de6ee339367f5fc94c77d53628f4ed4890eb6d713e52832c0f24','Exact source review')
    pins=read(OLD/'closed_audit03/PINS.json')
    pins.update(read(proposal/'STATIC_BINDING.json')['pins'])
    for p in (review,proposal/'STATIC_BINDING.json',HERE/'prepare.py',HERE/'short_host.c',HERE/'execute.py'):
        pins[str(p)]=sha(p)
    for p,h in pins.items():require(sha(p)==h,'Preflight drift '+p)
    save(HERE/'preflight.json',dict(status='ONE_REVIEWED_CANDIDATE_HOST_TWO_COMPILES_ONLY',pins=pins))
    for name in ('case.c','fp_period.h','gold_data.S'):
        emit(HERE/name,(source/name).read_text())
    emit(HERE/'packed_cache.h',(proposal/'packed_cache.h').read_text())
    emit(HERE/'mask_constant.h',(OLD/'mask_constant.h').read_text())
    emit(HERE/'host.c',(OLD/'host.c').read_text())
    token={}
    for label,header in [('old',OLD/'packed_cache.h'),('new',HERE/'packed_cache.h')]:
        run(['/usr/bin/cc','-E','-P','-x','c',header],HERE/f'host_tokens_{label}.i')
        token[label]=sha(HERE/f'host_tokens_{label}.i')
    save(HERE/'host_inheritance.json',dict(inherited=False,reason='Reviewed Host macro adds redundant parentheses; raw token identity is not claimed. Execute original full46 suite once.',preprocessed_sha256=token))
    rows=read(base.MODEL/'calls.json');seeds=read(base.MODEL/'seed_inputs.json');host=[]
    for packed in (False,True):
        root=HERE/('host_packed' if packed else 'host_original')
        base.make_host(root,packed,rows,seeds)
        flags=['-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-DSEW=32']
        if packed:flags+=['-DPACKED_CASE=1']
        run(['/usr/bin/cc',*flags,root/'host.c',HERE/'gold_data.S','-o',root/'host'],root/'compile.log')
        for mutation in list(range(15))+(list(range(20,36)) if packed else []):
            expected=90 if mutation>=20 else int(mutation!=0)
            log=root/f'case{mutation}.log';receipt=run([root/'host',mutation,base.MODEL/'gold_u32le.bin'],log,expected)
            require(('HOST_BLOCK' if expected==90 else 'HOST_FULL5985 results=766080 guards=11970') in log.read_text(),'Actual full Host result')
            host.append(dict(packed=packed,mutation=mutation,log=str(log),sha256=sha(log),**receipt))
    for n in range(15):require((HERE/'host_original'/f'case{n}.log').read_bytes()==(HERE/'host_packed'/f'case{n}.log').read_bytes(),'Original/candidate exact transcripts')
    header=(HERE/'packed_cache.h').read_text()
    needle='    return value;\n}\n\nstatic __attribute__((always_inline)) inline uint64_t'
    require(header.count(needle)==1,'Exact actual8 Host instrumentation')
    header=header.replace(needle,'    actual_event(p);\n'+needle)
    emit(HERE/'short_packed.h',header)
    run(['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',HERE/'short_host.c','-o',HERE/'short_host'],HERE/'short_compile.log')
    short=run([HERE/'short_host'],HERE/'short_host.log')
    save(HERE/'host_result.json',dict(status='HOST46_FULL5985_EQUIVALENCE_AND_SHORT_COMPARATOR_PASS_NOT_RV64',runs=host,short=short))
    compiled={}
    for backend in ('soc','spike'):
        root=HERE/backend;root.mkdir()
        emit(root/'main.c',(OLD/'soc/main.c').read_text())
        command=read(OLD/'soc/compile.log.command.json')['command']
        command=[v.replace(str(OLD),str(HERE)) for v in command]
        command=[v.replace(str(HERE/'soc'),str(root)) for v in command]
        if backend=='spike':command.insert(1,'-DSPIKE_REFERENCE=1')
        receipt=run(command,root/'compile.log')
        symbols,code,functions=base.disassemble(root/'program.elf',root)
        compiled[backend]=dict(returncode=receipt['returncode'],elf_sha256=sha(root/'program.elf'),instructions=len(code),symbols=len(symbols))
    for p,h in pins.items():require(sha(p)==h,'Post preparation drift '+p)
    save(HERE/'prepare_result.json',dict(status='HOST_PASS_TWO_ELFS_COMPILED_PENDING_LINKED_CFG_AUDIT',host_runs=len(host),backends=compiled,pins_unchanged=True,reference=False,DUT=False))

if __name__=='__main__':main()
