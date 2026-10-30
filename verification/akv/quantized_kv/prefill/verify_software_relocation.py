#!/usr/bin/env python3
"""Rebuild consumers and reuse functional evidence only for identical final ELFs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from archive_identity import members
from run_replay import digest
from run_model_qemu import check as check_model
from run_qwen3_model_qemu import check as check_qwen3
from run_graph_qemu import check_log as check_graph

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library-build',type=Path,required=True)
    parser.add_argument('--previous-run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();new=args.library_build.resolve(strict=True)
    old=args.previous_run.resolve(strict=True);out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False);pins={}
    def save(name,value):
        p=out/name;tmp=p.with_suffix(p.suffix+'.tmp')
        tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
    def pin(p,expected=None):
        p=Path(p).resolve(strict=True);h=digest(p)
        assert expected is None or h==expected,str(p)
        assert str(p) not in pins or pins[str(p)]==h,str(p)
        pins[str(p)]=h
    def verify():
        for p,h in pins.items():assert digest(p)==h,p
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify()
        save('status.json',dict(state=label));save(label+'.command.json',argv)
        with (out/(label+'.log')).open('w') as stream:
            subprocess.run(argv,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=600)
        verify()
    for p in (Path(__file__),HERE/'archive_identity.py',HERE/'run_replay.py',
              HERE/'build_graph_test.py',HERE/'run_model_qemu.py',HERE/'run_qwen3_model_qemu.py',HERE/'run_graph_qemu.py'):pin(p)
    result=dict(state='FAIL',fresh_model_execution=False,performance_measured=False)
    try:
        current=json.loads((new/'result.json').read_text());assert current['state']=='PASS'
        pin(new/'result.json');pin(new/'source-pins.json',current['source_pins_sha256'])
        for p,h in json.loads((new/'source-pins.json').read_text()).items():pin(p,h)
        parent=json.loads((old/'result.json').read_text());assert parent['state']=='PASS';pin(old/'result.json')
        previous={}
        for name,stage in parent['stages'].items():
            p=Path(stage['directory'])/'result.json';pin(p,stage['result_sha256']);previous[name]=json.loads(p.read_text())
        assert all(previous[n]['state']=='PASS' for n in ('libraries','graph','qwen25','qwen3'))
        archives={}
        for mode in ('OFF','ON'):
            a=previous['libraries']['configurations'][mode]['libraries']
            b=current['configurations'][mode]['libraries']
            old_lib=old/'libraries'/mode.lower();new_lib=new/mode.lower()
            old_map={str(Path(p).relative_to(old_lib)):(p,h) for p,h in a.items()}
            new_map={str(Path(p).relative_to(new_lib)):(p,h) for p,h in b.items()}
            assert old_map.keys()==new_map.keys();archives[mode]={}
            for name,(p,h) in old_map.items():
                q,j=new_map[name];pin(p,h);pin(q,j)
                x=members(Path(p).read_bytes());y=members(Path(q).read_bytes())
                assert x==y,'Archive payload differs: '+name
                archives[mode][name]=dict(entries=len(x),payloads_identical=True,
                    timestamp_metadata_ignored=True,old_sha256=h,new_sha256=j)
        audits=current['configurations']['ON']['dependency_audits']
        assert set(audits)=={'prefill','frontend'}
        assert all(a['verification_sources'] is False for a in audits.values())
        run([sys.executable,'-B',HERE/'build_graph_test.py',out/'graph-build','--library-build',new],'build-graph')
        graph=json.loads((out/'graph-build/result.json').read_text());assert graph['state']=='BUILT_NOT_EXECUTED'
        cases={}
        for mode in ('off','on'):
            a=previous['graph-build']['executables'][mode];b=graph['executables'][mode]
            pin(a['path'],a['sha256']);pin(b['path'],b['sha256']);assert a['sha256']==b['sha256'],'Graph ELF differs'
            cases['graph-'+mode]=dict(sha256=b['sha256'],byte_identical=True)
            log=old/'graph'/('qemu-'+mode+'.log');pin(log)
            assert check_graph(log.read_text(),mode=='on')==previous['graph']['results'][mode]
        for name,checker in (('qwen25',check_model),('qwen3',check_qwen3)):
            case=old/name;target=out/name;target.mkdir()
            receipt=previous[name];source_pins=case/'source-pins.json'
            pin(source_pins,receipt['source_pins_sha256']);historical=json.loads(source_pins.read_text())
            compile_cmd=json.loads((case/'compile.command.json').read_text())
            pin(case/'compile.command.json');pin(case/'link.command.json')
            pin(compile_cmd[0],historical[str(Path(compile_cmd[0]))])
            source=Path(compile_cmd[compile_cmd.index('-c')+1]);pin(source,historical[str(source)])
            compile_cmd[compile_cmd.index('-o')+1]=str(target/'test.o');run(compile_cmd,'compile-'+name)
            link=json.loads((case/'link.command.json').read_text());old_base=str(old/'libraries/on')
            link=[str(target/'test.o') if x==str(case/'test.o') else
                str(new/'on')+x[len(old_base):] if x.startswith(old_base+'/') else x for x in link]
            link=['-Wl,-Map='+str(target/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
            link[link.index('-o')+1]=str(target/'test');run(link,'link-'+name)
            pin(case/'test',historical[str(case/'test')]);pin(target/'test')
            assert digest(target/'test')==historical[str(case/'test')],'Model ELF differs: '+name
            log=case/'qemu.log';pin(log);assert checker(log.read_text())==receipt['measured']
            cases[name]=dict(sha256=digest(target/'test'),byte_identical=True,
                reused_result_sha256=digest(case/'result.json'),measured=receipt['measured'])
        # These are unchanged runtime images, not old source files whose paths moved.
        for name in ('graph','qwen25','qwen3'):
            case=old/name;p=case/'source-pins.json';receipt=previous[name]
            pin(p,receipt['source_pins_sha256']);historical=json.loads(p.read_text());selected=[]
            checker_file=HERE/({'graph':'run_graph_qemu.py','qwen25':'run_model_qemu.py','qwen3':'run_qwen3_model_qemu.py'}[name])
            pin(checker_file,historical[str(checker_file)])
            for file,h in historical.items():
                path=Path(file)
                if path.suffix=='.ext4' or path.name in ('qemu-system-riscv64','fw_dynamic.bin','Image','init','off.cpio','on.cpio','initramfs.cpio'):
                    pin(path,h);selected.append(str(path))
            assert any(p.endswith('.cpio') for p in selected)
            assert any(p.endswith('/qemu-system-riscv64') for p in selected)
            if name!='graph':assert any(p.endswith('.ext4') for p in selected)
            cases.setdefault(name,{})['runtime_inputs_verified']=len(selected)
        verify();save('source-pins.json',pins)
        result.update(state='PASS',validation='IDENTICAL_ELF_EVIDENCE_REUSE',archives=archives,cases=cases,
            previous_run=str(old),post_pins_match=True,source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        save('result.json',result);save('status.json',dict(state=result['state']))


if __name__=='__main__':main()
