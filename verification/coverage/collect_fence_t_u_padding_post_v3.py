"""Pinned simulator completion evidence, explicitly not an OS terminal receipt."""
import argparse
import gzip
import json
from pathlib import Path
import re
import shlex
import xml.etree.ElementTree as ET

import collect_fence_t_u_padding_post_v2 as policy

old=policy.old
ROOT,OUT,require=old.ROOT,old.OUT,old.require
POLICY_HELPER_SHA='dcca838d56777a01a8b449a9f380729ce3480307ccaaa710b2225facfcc6b847'
MODE='complete_pinned_simulator_log_NOT_OS_RETURN_RECEIPT'


def terminal_log(text, coverage_end):
    policy.policy_log(text)
    require(len(re.findall(r'^\$finish called from file .*uvm_root\.svh", line 527\.$',text,re.M))==1,
            'Missing/duplicate UVM finish call')
    require(len(re.findall(r'^\$finish at simulation time\s+\d+\s*$',text,re.M))==1,
            'Missing/duplicate finish time')
    marker=' Coverage status: End of All Coverages ...'
    require(text.splitlines().count(marker)==int(coverage_end), 'Coverage-end witness differs')
    require(text.count('VCS Coverage Metrics: during simulation line, cond, FSM, branch, tgl was monitored')==1,
            'Coverage metrics completion differs')
    require(text.count('V C S   S i m u l a t i o n   R e p o r t')==1, 'Duplicate/missing VCS end report')
    tail=re.search(r'^Time: (\d+ fs)\nCPU Time:\s+(\d+\.\d+) seconds;\s+Data structure size:\s+\d+\.\d+Mb\n'
                   r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2} \d{4}\s*\Z',text,re.M)
    require(tail is not None, 'Incomplete/nonterminal VCS report tail')
    require(len(re.findall(r'^Time: ',text,re.M))==1 and len(re.findall(r'^CPU Time:',text,re.M))==1,
            'Repeated VCS completion times')
    return dict(simulation_time=tail[1],reported_CPU_seconds=float(tail[2]),
                CPU_is_not_wall_time=True, complete_report_tail=True,
                finish_call_count=1, finish_time_record_count=1,
                end_coverage_count=int(coverage_end))


def xml(path):
    data=path.read_bytes()
    return ET.fromstring(gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data)


def vdb_witness(run,plan):
    data=run/'code.vdb/snps/coverage/db/testdata'
    require(sorted(p.name for p in data.iterdir() if p.is_dir())==['fence_t_u_padding_successor'],
            'Unexpected VDB test population')
    test=data/'fence_t_u_padding_successor'
    info=xml(test/'siminfo.xml').findall('srctest')
    require(len(info)==1,'Missing/duplicate VDB simulation identity')
    info=info[0].attrib
    require(shlex.split(info['cmdline'])==plan['run']['argv'][4:] and info['workdir']==str(run),
            'Native VDB command/cwd differs from sealed run plan')
    args=xml(test/'vcmArguments.xml')
    expected=OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
    require(args.attrib.get('compvdbpath')==str(expected), 'VDB compiled-image path differs')
    require(sorted(e.attrib['vcm_opt'] for e in args.findall('vcm_arg_data') if 'vcm_opt' in e.attrib)==
            sorted('-cm '+m for m in ('line','cond','fsm','tgl','branch')), 'VDB metric set differs')
    linked=json.loads(old.PLAN.read_bytes())
    baseline=Path(linked['baseline'])/'combined-bits.json'
    require(str(baseline) in plan['pins'], 'Unpinned baseline bitmap')
    bits=json.loads(baseline.read_bytes())
    counts={};inherited={}
    for metric in ('line','cond','fsm','branch','tgl'):
        root=xml(test/(metric+'.verilog.data.xml'))
        require(root.tag=='covdata' and root.attrib.get('type')==(None if metric=='line' else 'verilog'),
                'Unexpected VDB data root')
        rows=root.findall('instance_data');seen=set();inherited[metric]=0
        require(rows,'Empty VDB metric')
        for entry in rows:
            scope=entry.attrib['name'];value=entry.attrib['value']
            require(scope not in seen and set(value)<={'0','1'},'Duplicate/nonbinary VDB instance')
            seen.add(scope)
            raw_checksum=entry.attrib.get('chksum')
            inherited[metric]+=raw_checksum is None
            if metric in bits['metrics']:
                bound=bits['metrics'][metric][scope]
                require(raw_checksum in (None,bound['checksum']) and len(value)==bound['width'],
                        'VDB definition checksum/width differs: '+scope)
            else:
                require(metric=='tgl' and raw_checksum is not None and value,
                        'Unbound/malformed extra VDB metric')
        if metric in bits['metrics']:
            require(seen==set(bits['metrics'][metric]), 'Incomplete VDB metric scope population')
        counts[metric]=len(rows)
    paths=sorted(p for p in test.rglob('*') if p.is_file())
    return dict(siminfo=info,metric_instance_counts=counts,
                raw_checksum_inherited_counts=inherited,
                missing_checksum_policy='Existing frozen raw-audit convention: absent per-row checksum inherits sealed baseline compiled-image binding; not claimed present in raw XML',
                exact_baseline_shape=True,baseline_shape_metrics=sorted(bits['metrics']),
                toggle_baseline_shape_verified=False,
                toggle_scope='Complete parsed/pinned raw witness only; formal727 bitmap has no toggle metric, no toggle gain/shape qualification claimed',
                gain_not_computed=True),{str(p):old.sha(p) for p in paths}


def collect(output):
    require(output.parent==OUT and not output.exists() and output.resolve()==output,'Fresh collector output required')
    require(old.sha(old.PLAN)==old.PLAN_SHA,'Linked plan seal differs')
    policy.collector()  # Validate frozen predecessors and UVM compiled-source identity; no collection.
    require(old.sha(Path(policy.__file__))==POLICY_HELPER_SHA,'Frozen policy helper differs')
    plan=json.loads(old.PLAN.read_bytes());old.check_pins(plan['pins'])
    run=Path(plan['run']['cwd'])
    paths=[run/'console.log',run/'run.vcs.log',run/'commit_trace.csv']
    outputs={str(p):old.sha(p) for p in paths}
    console=paths[0].read_text();vcs=paths[1].read_text()
    first,second=terminal_log(console,True),terminal_log(vcs,False)
    require(first['simulation_time']==second['simulation_time'] and
            first['reported_CPU_seconds']==second['reported_CPU_seconds'], 'Two log end reports disagree')
    witness,vdb_pins=vdb_witness(run,plan);outputs.update(vdb_pins)
    require(witness['siminfo']['simtime']==first['simulation_time'] and
            float(witness['siminfo']['cputime'])==first['reported_CPU_seconds'],'VDB/log time evidence differs')
    build=OUT/'fence-t-u-padding-build-parent-727-20261006-01'
    result=policy.evaluate(console,paths[2].read_text(),json.loads((build/'elf_metadata.json').read_bytes())[0],
                           (build/'input.elf').read_bytes(),plan['proof']['sites'],vcs)
    old.check_pins(plan['pins'])
    for path,digest in outputs.items():require(old.sha(path)==digest,'Output still changing: '+path)
    require(old.sha(old.PLAN)==old.PLAN_SHA,'Linked plan changed')
    deps=[Path(__file__).resolve(),Path(policy.__file__).resolve(),Path(old.__file__).resolve(),
          policy.UVM,policy.POLICY,
          ROOT/'verification/coverage/test_collect_fence_t_u_padding_post.py',
          ROOT/'verification/coverage/test_collect_fence_t_u_padding_post_v2.py',
          ROOT/'verification/coverage/test_collect_fence_t_u_padding_post_v3.py']
    dep_pins={str(p):old.sha(p) for p in deps}
    require(dep_pins[str(Path(old.__file__).resolve())]==policy.PREDECESSOR_SHA and
            dep_pins[str(Path(policy.__file__).resolve())]==POLICY_HELPER_SHA and
            dep_pins[str(policy.UVM)]==policy.UVM_SHA and dep_pins[str(policy.POLICY)]==policy.POLICY_SHA,
            'Frozen successor dependency changed')
    result.update(terminal_source=MODE,returncode_unknown=True,OS_returncode=None,
                  OS_terminal_receipt_verified=False,wall_elapsed_seconds=None,
                  exact_wall_time_verified=False,terminal_log_evidence=dict(console=first,vcs_log=second),
                  VDB_witness=witness,output_pins=outputs,frozen_input_pins=plan['pins'],
                  frozen_pin_count=151,frozen_pins_pre_and_post_verified=True,
                  linked_plan_sha256=old.PLAN_SHA,collector_pins=dep_pins)
    output.mkdir();(output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    seal=old.sha(output/'result.json')
    (output/'seal.json').write_text(json.dumps(dict(result_sha256=seal))+'\n')
    print(json.dumps(dict(output=str(output),seal=seal,status=result['status'],terminal_source=MODE)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--terminal-source',choices=[MODE],required=True)
    args=parser.parse_args();collect(args.output.absolute())
