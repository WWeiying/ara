#!/usr/bin/env python3
"""Run the reviewed same-ELF old/new pair, finite waves and actual UVM checks."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import executor_common as c


def simulation_command(simv,elf,target,script,log,trace):
    c.require(type(target) is int and 0x80000000<=target<0x81000000 and target%64==0 and
              target%4096<=4096-288,'Invalid injected target')
    return [simv,'-no_save','-ucli','-do',script,'-l',log,
            '+PRELOAD='+str(elf),f'+READER_FAULT_TARGET={target:x}',
            '+TESTCASE=reader_held_ar_fault','+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF','+AKV_PERF',
            '+VECTOR_TRACE='+str(trace),'+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000']


def check_metadata(metadata,profile):
    wanted=[s['alias'] for s in profile['signals']]
    present=metadata.get('present_signals',[])
    c.require(metadata.get('edge')=='negedge' and type(metadata.get('cycle_count')) is int and
              metadata['cycle_count']>10 and not metadata.get('missing_signals') and
              len(present)==len(set(present))==len(wanted) and set(present)==set(wanted),
              'Incomplete/duplicated FSDB signal export')


def compare_pair(results):
    a,b=(results[mode]['log'] for mode in c.MODES)
    c.require(a['commands']==b['commands']==71 and a['trap_tval']==b['trap_tval'],
              'Paired program/target mismatch')
    c.require(len(a['records'])==len(b['records'])==71,'Missing paired command ledger')
    differences=[]
    for index,(old,new) in enumerate(zip(a['records'],b['records']),1):
        c.require(set(old)==set(new),'Paired PERF schema mismatch')
        changed={k:dict(baseline=old[k],candidate=new[k]) for k in old if old[k]!=new[k]}
        if changed: differences.append(dict(command=index,fields=changed))
    return dict(state='PASS' if not differences else 'REGRESSION',commands=71,
                exact_per_command=not differences,differences=differences,
                scope='Resource baseline versus shared-reader/unified-storage; identical TB fault interposer',
                performance_claim=False,mmu_covered=False,production_promoted=False)


def run(args):
    c.require(type(args.timeout) is int and 1<=args.timeout<=900,'Simulation wall bound is 1..900 seconds')
    build=args.build.resolve(strict=True); out=args.output.resolve()
    c.require(not out.exists() and not out.is_relative_to(build) and not build.is_relative_to(out),
              'Fresh independent run output required')
    report,prepared,pins=c.checked_build(build,args.expected_build_sha256)
    c.s.merge_pins(pins,c.own_pins())
    exporter=args.fsdbreport.absolute()
    toolpins=c.s.hashes(c.hand.exporter_files(exporter))
    c.s.merge_pins(pins,toolpins)
    c.s.verify_pins(pins)
    out.mkdir(parents=True)
    owner=c.Execution(out); owner.state.update(build=str(build),performance=False); owner.save()
    try:
        c.save(out/'source-pins.json',pins)
        pinsha=c.digest(out/'source-pins.json')
        if args.preflight_only:
            c.save(out/'preflight.json',dict(state='RUN_PREFLIGHT_ONLY',execution='NOT_RUN',
                build=str(build),build_sha256=args.expected_build_sha256,source_pins_sha256=pinsha))
            owner.state['state']='RUN_PREFLIGHT_ONLY'
            return
        elf=Path(report['elf']); target=report['weights']['address']
        results={}; evidence=[out/'source-pins.json']

        def identity():
            c.require(c.digest(out/'source-pins.json')==pinsha,'Run input receipt drift')
            c.s.verify_pins(pins)
            c.require(c.s.hashes(c.hand.exporter_files(exporter))==toolpins,'FSDB tool inventory drift')
            for image in report['images'].values():
                simv=Path(image['simv'])
                c.require(c.s.hashes(c.s.image_files(simv))==image['pins'],'Image inventory drift')
                c.verify_manifest(simv.parent/'vcs_source_manifest.json')

        for mode in c.MODES:
            work=out/mode; work.mkdir(); owner.state['variant']=mode
            image=report['images'][mode]; simv=Path(image['simv'])
            recipe=prepared['recipes'][mode]
            profile=Path(recipe['capture']); script=Path(recipe['script'])
            identity()
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                           simv.parent/'vcs_source_manifest.json','--check'],
                          work/'manifest-before.log',300,'MANIFEST_BEFORE')
            owner.execute(['bash',c.ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                           simv.parent,elf],work/'image-contract.log',180,'IMAGE_CONTRACT')
            log=work/'run.vcs.log'; trace=work/'vector_trace.csv'
            owner.execute(simulation_command(simv,elf,target,script,log,trace),
                          work/'console.log',args.timeout,'RUNNING')
            identity()
            c.check.check_log(log.read_text(),Path(recipe['vlsu']).read_text(),target)
            # No log/trace filtering and no locally manufactured protocol summary.
            owner.execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
                           '--require-axi','--require-axi-write','--vector-trace',trace,'--log',log,
                           '--simv',simv,'--elf',elf,'--output',work/'uvm_result.json'],
                          work/'uvm-check.log',600,'UVM_CHECK')
            c.s.check_result(work/'uvm_result.json',report['elf_sha256'],image['pins'])
            uvm=c.s.read_json(work/'uvm_result.json')
            c.require(uvm['log_sha256']==c.digest(log) and uvm['vector_trace_sha256']==c.digest(trace),
                      'Actual UVM input identity mismatch')
            owner.execute([sys.executable,'-B',c.ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py',
                           '--fsdb',work/'reader.fsdb','--profile',profile,'--begin','0ns','--end','250000ns',
                           '--output',work/'cycles','--fsdbreport',exporter],
                          work/'extract.log',300,'EXTRACTING')
            metadata=c.s.read_json(work/'cycles/metadata.json')
            check_metadata(metadata,c.s.read_json(profile))
            parsed=c.check.check_log_and_cycles(log.read_text(),Path(recipe['vlsu']).read_text(),
                                                work/'cycles/cycles.csv',target)
            c.save(work/'checked.json',parsed)
            owner.execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                           simv.parent/'vcs_source_manifest.json','--check'],
                          work/'manifest-after.log',300,'MANIFEST_AFTER')
            identity()
            results[mode]=parsed
            # Closed explicit files only. In particular not systemd worker.log.
            evidence += [work/n for n in ('run.vcs.log','vector_trace.csv','reader.fsdb','uvm_result.json',
                'checked.json','console.log','cycles/cycles.csv','cycles/metadata.json',
                'cycles/fsdbreport.raw.csv','manifest-before.log','manifest-after.log',
                'image-contract.log','uvm-check.log','extract.log')]
            evidence += sorted(work.glob('*.command.json'))+sorted(work.glob('*.exit.json'))
        result=compare_pair(results)
        identity()
        result.update(build=str(build),build_sha256=args.expected_build_sha256,
            prepared=report['prepared'],prepare_sha256=report['prepare_sha256'],
            elf=str(elf),elf_sha256=report['elf_sha256'],weights=report['weights'],images=report['images'],
            source_pins_sha256=pinsha,post_pins_match=True,independent_protocol_checked=True,
            simulator_exit_codes=dict(baseline=0,candidate=0),profiles=results,
            evidence_sha256=c.closed_evidence(evidence))
        c.save(out/'result.json',result)
        owner.state['state']=result['state']
        c.require(result['state']=='PASS','Paired command regression; retain both raw results')
    except BaseException as exc:
        # Preserve an already-completed comparison, rather than overwrite its deltas.
        if not (out/'result.json').exists(): c.finish_failure(owner,out,exc)
        raise
    finally:
        owner.state['child_pid']=None; owner.save()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--expected-build-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=900)
    p.add_argument('--preflight-only',action='store_true')
    p.add_argument('--fsdbreport',type=Path,default=Path(
        '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1/bin/fsdbreport'))
    c.install_signals(); run(p.parse_args())
