#!/usr/bin/env python3
"""Rebuild every Attention ABBA object from current sources; never simulate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
PAIR=HERE.parent/'pair'
sys.dont_write_bytecode=True


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def require(ok,message):
    if not ok:raise ValueError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    require(out.is_relative_to(ROOT/'verification/out') and not out.exists(),'Need fresh independent output')
    spec=importlib.util.spec_from_file_location('fresh_attention_pair_helpers',PAIR/'prepare.py')
    helper=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
    producer=helper.reviewed_producer()
    prior_path=PAIR/'out/build-gnu-01/build.json'
    prior=json.loads(prior_path.read_text())
    require(prior['elf_sha256']==sha(prior['elf']),'Historical ELF changed')
    acceptance=ROOT/'verification/akv/results/grouped-pv-pair-review-20261026.json'
    require(json.loads(acceptance.read_text())['state']=='FUNCTIONAL_PASS_PERFORMANCE_REGRESSION',
            'Missing checked original comparison')
    original_records=producer.BASE/'commands.json'
    link=next(r['argv'] for r in json.loads(original_records.read_text()) if r['label']=='link')
    old_objects=[Path(p) for p in link if p.endswith('.o')]
    require(len(old_objects)==17,'Unexpected source inventory')
    pins={};commands=[];new_objects=[];dependencies=[]
    def pin(path):
        path=Path(path).resolve(strict=True);digest=sha(path)
        require(str(path) not in pins or pins[str(path)]==digest,'Input changed during build: '+str(path))
        pins[str(path)]=digest
    for path in (Path(__file__),PAIR/'prepare.py',helper.PRODUCER,prior_path,
                 prior['elf'],acceptance,original_records):pin(path)
    # Deliberately bind only the data from historical sources. No old code
    # source/object hash is relabeled as a current-source acceptance.
    old_data=dict(prior['input_pins'],**prior['artifacts'])
    out.mkdir(parents=True)
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);commands.append(dict(label=label,argv=argv))
        save(out/'commands.json',commands)
        with (out/(label+'.log')).open('x') as f:
            subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
        return out/(label+'.log')
    try:
        for i,obj in enumerate(old_objects):
            argv,recipe=producer.compile_record(obj);argv=list(argv);pin(recipe)
            source=Path(argv[argv.index('-c')+1])
            if obj==producer.BASE/'main.o':source=PAIR/'main.c'
            pin(source)
            if source.name in producer.GENERATED:
                require(sha(source)==producer.GENERATED[source.name],'Capture assembly changed')
                for name in re.findall(r'^\.incbin "([^"]+)"$',source.read_text(),re.M):
                    require(old_data.get(name)==sha(name),'Unproven captured payload: '+name);pin(name)
            target=out/f'{i}.o';argv[argv.index('-c')+1]=str(source);argv[argv.index('-o')+1]=str(target)
            dep_log=run(producer.deps_command(argv),'deps-'+str(i))
            deps=producer.parse_deps(dep_log.read_text());require(bool(deps),'Empty compiler dependencies')
            for path in deps:pin(path)
            dependencies.append(dict(source=str(source),files={str(p):sha(p) for p in deps}))
            run(argv,'compile-'+str(i));new_objects.append(target)
        ld=out/'link.ld';ld.write_text((PAIR/'out/build-gnu-01/link.ld').read_text());pin(ld)
        replacements={str(old):str(new) for old,new in zip(old_objects,new_objects)}
        linked=[replacements.get(a,a) for a in link]
        elf=out/'grouped_attention.elf';linked[linked.index('-o')+1]=str(elf)
        linked[linked.index('-T')+1]=str(ld)
        linked=['-Wl,-Map='+str(out/'link.map') if a.startswith('-Wl,-Map=') else a for a in linked]
        compiler=Path(linked[0])
        for library in ('libm.a','libc.a','libgcc.a','libnosys.a'):
            path=subprocess.check_output([str(compiler),'-print-file-name='+library],text=True).strip();pin(path)
        run(linked,'link')
        disassembly=run([compiler.with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassemble')
        review=helper.linked_review(producer,elf,disassembly.read_text())
        # The caller/ABI/data/ROI review is unchanged; all objects are new.
        save(out/'linked-review.json',review);save(out/'dependencies.json',dependencies)
        require(all(sha(p)==h for p,h in pins.items()),'Source drift')
        save(out/'source-pins.json',pins)
        result=dict(state='FRESH_GNU_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=sha(elf),
                    rebuilt_objects=len(new_objects),reused_objects=0,simulations_launched=0,
                    numerical_execution_checked=False,performance_measured=False,
                    api_evidence=review,golden=prior['golden'],golden_sha256=sha(prior['golden']),
                    source_pins_sha256=sha(out/'source-pins.json'),
                    artifacts={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
        save(out/'build.json',result);print(result['state'])
    except BaseException as exc:
        save(out/'build.json',dict(state='FAIL',error=repr(exc),simulations_launched=0));raise


if __name__=='__main__':main()
