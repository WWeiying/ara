#!/usr/bin/env python3
"""Export actual expf input/result bits from a previously proven RVFI trace."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
spec=importlib.util.spec_from_file_location('exp_retirement_primitives',HERE/'analyze.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
require=analysis.require


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def operands(text):
    result={}
    for line in text.splitlines():
        match=re.match(r'\s*([0-9a-f]+):\s+(?:[0-9a-f]{8}|[0-9a-f]{4})\s+\S+\s*(.*)$',line)
        if match:result[int(match[1],16)]=match[2].strip()
    return result


def extract(code,args,stream,entry,windows,expected=768):
    groups=[[] for _ in windows];fa0=None;producer=None;active=None;pending=None
    start={w['start']['order']:i for i,w in enumerate(windows)}
    end={w['end']['order']:i for i,w in enumerate(windows)}
    for row in analysis.base.csv_module.csv_records(stream,analysis.base.COMMIT_HEADER,analysis.base.EVENTS):
        if row['event']!='retire':continue
        if row['order'] in start:
            require(active is None and pending is None,'Nested call window');active=start[row['order']]
        if row['order'] in end:
            require(active==end[row['order']] and pending is None,'Unfinished expf at window end');active=None
        pc=row['pc'];item=code.get(pc)
        if active is not None:
            require(item is not None and item['bits']==row['insn'] and not row['trap'],'Changed executed instruction')
        if not item:continue
        names=item['function'].split('|')
        if pc==entry and active is not None:
            require(pending is None and fa0 is not None and producer is not None,'Missing/nested expf argument')
            require(fa0>>32==0xffffffff,'Argument is not NaN-boxed binary32')
            pending=dict(input_bits=f'{fa0&0xffffffff:08x}',producer_pc=hex(producer),entry_order=row['order'])
        # GNU disassembly names the destination ABI register. Stores read fa0;
        # do not treat their first operand as an architectural register write.
        destination=args[pc].split(',',1)[0].strip()
        store=bool(re.fullmatch(r'(?:c\.)?fs[whdq](?:sp)?',item['mnemonic']))
        if destination=='fa0' and not store:
            require(row['rd']==10,'Floating destination identity');fa0=row['rd_wdata'];producer=pc
        if item['mnemonic']=='ret' and 'expf' in names and active is not None:
            require(pending is not None and fa0 is not None and fa0>>32==0xffffffff,'Missing expf result')
            pending.update(output_bits=f'{fa0&0xffffffff:08x}',return_order=row['order'])
            groups[active].append(pending);pending=None
    require(active is None and pending is None and all(len(g)==expected for g in groups),'Incomplete expf calls')
    pairs=lambda group:[(r['input_bits'],r['output_bits']) for r in group]
    require(all(pairs(group)==pairs(groups[0]) for group in groups),'Cross-trial exponential arguments/results differ')
    return groups


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();run=a.run.resolve(strict=True);out=a.output.resolve()
    require(out.is_relative_to(ROOT/'verification/out') and not out.exists(),'Fresh independent output required')
    review=ROOT/'verification/akv/results/current-attention-retirement-review-20261027.json'
    accepted=json.loads(review.read_text());report=json.loads((run/'result.json').read_text())
    require(accepted['state']=='FOUR_CALL_RETIREMENT_AND_PROTOCOL_PASS' and
            ROOT/accepted['source_result']==run/'result.json' and
            accepted['source_result_sha256']==digest(run/'result.json') and report['retirement_proven'],
            'Need exact accepted retirement result')
    build=Path(report['build']);receipt=json.loads((build/'build.json').read_text())
    disassembly=build/'disassemble.log';elf_path=Path(receipt['elf']);trace=run/'work/commit_trace.csv'
    pins={str(p):digest(p) for p in (review,run/'result.json',run/'attribution.json',trace,
                                   build/'build.json',disassembly,elf_path,Path(__file__),HERE/'analyze.py')}
    require(pins[str(trace)]==accepted['commit_trace_sha256'] and
            pins[str(run/'attribution.json')]==accepted['attribution_sha256'] and
            pins[str(elf_path)]==report['elf_sha256'],'Evidence identity mismatch')
    elf=analysis.base.LinkedELF(elf_path.read_bytes());text=disassembly.read_text()
    code=analysis.base.disassembly_map(text,elf);destinations=operands(text)
    require(set(code)==set(destinations),'Missing operand disassembly')
    entries=[start for start,_,name in elf.functions if name=='expf'];require(len(entries)==1,'expf symbol identity')
    windows=json.loads((run/'attribution.json').read_text())['windows']
    with trace.open() as stream:groups=extract(code,destinations,stream,entries[0],windows)
    values=[struct.unpack('<f',bytes.fromhex(row['input_bits'])[::-1])[0] for row in groups[0]]
    require(all(v<=0 for v in values),'Not a nonpositive online-Attention domain')
    finite=[v for v in values if v!=float('-inf')]
    require(finite and all(digest(p)==h for p,h in pins.items()),'Input drift or empty finite domain')
    out.mkdir(parents=True)
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
    (out/'exp-pairs.json').write_text(json.dumps(dict(schema='actual_attention_expf_pairs_v1',
        provenance='Bare-metal Newlib expf results, not a universal libm golden',calls=groups[0]),indent=2)+'\n')
    summary=dict(state='REAL_EXP_ARGUMENTS_EXTRACTED',trials=4,calls_per_trial=len(values),
        unique_input_bits=len({r['input_bits'] for r in groups[0]}),negative_infinities=len(values)-len(finite),
        finite_min=min(finite),finite_max=max(finite),
        finite_below_minus_80=sum(v< -80 for v in finite),
        cross_trial_inputs_outputs_bitwise_equal=True,performance_measured=False,
        pairs_sha256=digest(out/'exp-pairs.json'))
    (out/'result.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
