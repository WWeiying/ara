#!/usr/bin/env python3
"""Audit existing evidence and finish the frozen ALU SoC pair without rebuilding."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import re
import shutil
import time

ZERO_ALU_CASE = 'rv64uv-ara-vwiden_lmul4_edges'
COLLATERAL = {ZERO_ALU_CASE: 'vwiden_lmul4_edges',
              'rv64uv-ara-vunit_vstart_edges': 'vunit_vstart_edges'}


def classify(api, text, case):
    if case not in COLLATERAL:
        result=api.parse(text, case)
        if case=='vvaddint32' and (len(result['hw_cycles'])!=1 or int(result['hw_cycles'][0])<=0):
            raise ValueError('Missing nonzero vector-add timer')
        return result
    # This ELF only exercises vector loads/stores and widening MAC in VMFPU.
    # It is a collateral regression, not evidence that the shared ALU ran.
    if ('Core Test *** SUCCESS ***' not in text or
            not re.search(r'^PASSED: .*'+COLLATERAL[case]+r'\.c!$',text,re.M) or
            re.search(r'Fatal:|Error:|\bFAILED\b|ALU_SOC_MISMATCH',text)):
        raise ValueError('Collateral firmware/checker failure')
    activity = sorted(api.ACTIVITY.findall(text))
    monitors = re.findall(r'^ALU_SOC_MONITOR (\S+)',text,re.M)
    finish = re.findall(r'\$finish at simulation time\s+(\d+)',text)
    if (len(monitors) != 4 or len(set(monitors)) != 4 or len(activity) != 4 or
            {r[0] for r in activity} != set(monitors) or len(finish) != 1):
        raise ValueError('Incomplete collateral monitor/completion evidence')
    return dict(activity=activity,finish_time=finish[0],
                kernel_cycles=re.findall(r'The execution took (\d+) cycles',text),
                hw_cycles=re.findall(r'\[hw-cycles\]:\s*(\d+)',text),micro=[])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('previous',type=Path); p.add_argument('output',type=Path)
    p.add_argument('--supplement',type=Path)
    p.add_argument('--replacement-vadd',type=Path)
    args = p.parse_args(); old=args.previous.resolve(); out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('sealed_alu_runner',old/'run_shared_alu_soc.py')
    api=importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
    def read(p): return json.loads(p.read_text())
    state=dict(state='AUDITING',previous=str(old))
    def update(**kw):
        state.update(kw); api.save(out/'status.json',state); print(json.dumps(state),flush=True)
    try:
        update()
        pins=read(old/'source-pins.json')
        pins[str(Path(__file__).resolve())]=api.sha(Path(__file__).resolve())
        for name in ('results.json','pairs.json','plan.json'):
            pins[str(old/name)]=api.sha(old/name)
        for v in ('baseline','shared'):
            image=old/v/'sim/simv'
            if api.sha(image) != read(old/v/'image.json')['sha256']:
                raise ValueError('Image identity drift: '+v)
            pins[str(image)]=api.sha(image)
        original=read(old/'results.json'); plan=read(old/'plan.json')
        if args.supplement:
            original += [r for r in read(args.supplement/'results.json')
                         if r.get('returncode') is not None and r['case']!='vvaddint32']
        replacement = None
        if args.replacement_vadd:
            replacement=out/'vadd1024.elf'
            shutil.copy2(args.replacement_vadd,replacement)
            pins[str(replacement)]=api.sha(replacement)
            source=args.replacement_vadd.with_suffix('.S')
            shutil.copy2(source,out/'vadd1024.S')
            pins[str(out/'vadd1024.S')]=api.sha(out/'vadd1024.S')
            api.save(out/'substitution.json',dict(case='vvaddint32',replacement_sha256=api.sha(replacement),
                reason='Original ELF produced no VALU work; replacement is a self-checking 1024-element vector-add program. Original is not accepted as ALU evidence.'))
        for row in original:
            d=Path(row['evidence']) if 'evidence' in row else old/row['variant']/'cases'/row['case']
            for name in ('console.log','command.json','result.json'):
                pins[str(d/name)]=api.sha(d/name)
        api.save(out/'source-pins.json',pins)
        def check():
            for f,h in pins.items():
                if api.sha(Path(f)) != h: raise ValueError('Pinned input drift: '+f)
        check()
        rows=[]; pairs=[]
        def pair(name,results):
            if len(results)!=2 or {r['variant'] for r in results}!={'baseline','shared'}:
                raise ValueError('Incomplete pair: '+name)
            a,b=results
            equal=all(a[k]==b[k] for k in ('activity','finish_time','kernel_cycles','hw_cycles','micro'))
            item=dict(case=name,functional='PASS',exact_cycle_activity_equivalence=equal,
                      role='collateral_non_ALU' if name in COLLATERAL else 'ALU_active')
            pairs.append(item); api.save(out/'pairs.json',pairs)
            if not equal: raise ValueError('Paired timing/activity/results difference: '+name)
        done={r['case'] for r in original}
        for name in plan['cases']:
            if name not in done: continue
            audited=[]
            for r in [r for r in original if r['case']==name]:
                d=Path(r['evidence']) if 'evidence' in r else old/r['variant']/'cases'/name
                if r['returncode']!=0: raise ValueError('Nonzero original returncode')
                if read(d/'command.json')['elf_sha256']!=api.sha(old/'inputs'/name):
                    raise ValueError('Original ELF identity drift')
                result=dict(variant=r['variant'],case=name,status='PASS',evidence=str(d),
                            **classify(api,(d/'console.log').read_text(errors='replace'),name))
                rows.append(result); audited.append(result)
            pair(name,audited)
        api.save(out/'results.json',rows)
        remaining=[n for n in plan['cases'] if n not in done]
        api.save(out/'audit.json',dict(original_worker_state=read(old/'status.json'),
            audited_pairs=len(pairs),reclassified_case=ZERO_ALU_CASE,
            reason='Widening MAC uses VMFPU; zero VALU activity is expected. Firmware and paired timing still required.',
            remaining=remaining,original_evidence_unchanged=True))
        def run(v,name):
            d=out/v/name; d.mkdir(parents=True)
            elf=replacement if name=='vvaddint32' and replacement else old/'inputs'/name
            cmd=[str(old/v/'sim/simv'),'-no_save','-l','run.vcs.log',f'+PRELOAD={elf}',
                 f'+TESTCASE={name}','+NO_FSDB','+ntb_random_seed=1']
            limit=10800 if name in ('dotproduct','llama_q4km_micro') else 3600
            api.save(d/'command.json',dict(command=cmd,elf_sha256=api.sha(elf),timeout_seconds=limit))
            start=time.monotonic(); rc=api.execute(cmd,d,d/'console.log',limit)
            result=dict(variant=v,case=name,returncode=rc,wall_seconds=time.monotonic()-start,evidence=str(d))
            try:
                if rc: raise ValueError('Nonzero simulator return: '+str(rc))
                result.update(classify(api,(d/'console.log').read_text(errors='replace'),name),status='PASS')
            except ValueError as exc:
                result.update(status='FAIL',reason=str(exc))
            api.save(d/'result.json',result)
            return result
        for i in range(0,len(remaining),3):
            check(); batch=remaining[i:i+3]
            update(state='RUNNING',completed_pairs=len(pairs),total_pairs=len(plan['cases']),active_cases=batch)
            with ThreadPoolExecutor(max_workers=6) as pool:
                results=list(pool.map(lambda vn:run(*vn),[(v,n) for n in batch for v in ('baseline','shared')]))
            rows.extend(results); api.save(out/'results.json',rows)
            for j,name in enumerate(batch):
                group=results[2*j:2*j+2]
                if any(r['status']!='PASS' for r in group):
                    raise ValueError('Firmware or checker failure: '+name)
                pair(name,group)
        check()
        if len(pairs)!=len(plan['cases']): raise ValueError('Incomplete final suite')
        api.save(out/'report.json',dict(functional_status='PASS',performance_status='PASS',
            total_pairs=len(pairs),alu_active_pairs=sum(r['role']=='ALU_active' for r in pairs),
            collateral_pairs=sum(r['role']=='collateral_non_ALU' for r in pairs),
            exact_cycle_activity_equivalence=True,original_evidence=str(old),
            scope='Full SoC ALU integration; not physical, FPGA or code coverage signoff'))
        update(state='PASS',completed_pairs=len(pairs),total_pairs=len(pairs),active_cases=[])
        return 0
    except Exception as exc:
        update(state='STOPPED',reason=str(exc)); raise


if __name__=='__main__':
    raise SystemExit(main())
