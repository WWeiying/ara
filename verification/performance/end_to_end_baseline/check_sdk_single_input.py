"""Check same-ELF ABBA SDK dispatch timings without requiring an improvement."""
import re
from pathlib import Path

from audit import digest,require
from check_decode_native import check as decode_check
from check_projection_native import fields

ORDER=(0,1,1,0)
SUITE='SDK_SINGLE_INPUT_SUITE_PASS trials=4 order=ABBA commands=112 outputs=3584'


def oracle_paths(build):
    build=Path(build)
    return ([build/f'part_{p}_expected.bin' for p in range(7)]+
            [build/f'activation_{i}.bin' for i in range(4)]+[build/'profiles.bin',build/'flags.bin'])


def verify_oracle_inputs(program,pins):
    expected=program['oracle_inputs']
    require(set(expected)=={str(p) for p in oracle_paths(program['oracle_build'])},'Incomplete oracle inventory')
    for path,sha in expected.items():
        require(pins.get(path)==sha==digest(path),'Oracle identity drift: '+path)


def check(text,*oracle):
    mode=None;seen=[];trials=[];lines=[];sequence=0
    for line in text.splitlines():
        if line.startswith('SDK_SINGLE_INPUT_TRIAL_BEGIN '):
            row=fields(line,'SDK_SINGLE_INPUT_TRIAL_BEGIN');trial=len(seen)
            require(mode is None and trial<4 and row==dict(trial=trial,candidate=ORDER[trial]),'ABBA begin order')
            mode=trial;seen.append(trial);lines=[]
        elif line.startswith('SDK_SINGLE_INPUT_TRIAL_END '):
            row=fields(line,'SDK_SINGLE_INPUT_TRIAL_END')
            require(mode is not None and row==dict(trial=mode,candidate=ORDER[mode],status=0),'ABBA terminal')
            measured=decode_check('\n'.join(lines),*oracle)
            trials.append(dict(trial=mode,candidate=ORDER[mode],measured=measured));mode=None
        elif mode is not None:
            if line.startswith('[QBS_PERF] '):
                sequence+=1;row=fields(line,'[QBS_PERF]')
                require(row['seq']==sequence and sequence<=112,'Global command order')
                normalized=sequence-28*mode
                line=re.sub(r'(?<!\S)seq=\d+(?=\s|$)',f'seq={normalized}',line,count=1)
            lines.append(line)
        elif line.startswith(('[QBS_PERF] ','DECODE_NATIVE_')):
            require(False,'Measured work outside trial')
    require(mode is None and seen==list(range(4)) and len(trials)==4 and sequence==112 and
            text.splitlines().count(SUITE)==1 and not re.search(r'Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@',text,re.M),
            'Incomplete/failed ABBA run')
    fixed=('ar','r_beats','payload_bytes','weight_bytes','activation_bytes','useful_pairs','dot_active_cycles','fp_uop_issue',
           'accumulator_updates','context_fill_count','context_reuse_count','context_read_bytes','activation_axi_bytes_saved')
    before=trials[0]['measured']
    for trial in trials[1:]:
        m=trial['measured']
        require([(p['checksum'],p['fcsr'],p['vcsr']) for p in m['parts']]==
                [(p['checksum'],p['fcsr'],p['vcsr']) for p in before['parts']],'Output/CSR differs')
        require([(p['checksum'],p['fcsr'],p['vcsr']) for p in m['preparation']]==
                [(p['checksum'],p['fcsr'],p['vcsr']) for p in before['preparation']],'Quantization differs')
        require([[a['counters'][key] for key in fixed] for a in m['activity']]==
                [[a['counters'][key] for key in fixed] for a in before['activity']],'Hardware service work changed')
    baseline=[t['measured'] for t in trials if not t['candidate']]
    candidate=[t['measured'] for t in trials if t['candidate']]
    comparisons=[]
    for part in range(7):
        a=sum(m['parts'][part]['execution'] for m in baseline)
        b=sum(m['parts'][part]['execution'] for m in candidate)
        comparisons.append(dict(part=part,baseline_execution_sum=a,candidate_execution_sum=b,execution_ratio=a/b,
            warmed_baseline_execution=baseline[1]['parts'][part]['execution'],
            candidate_execution_mean=b/2,warmed_execution_ratio=2*baseline[1]['parts'][part]['execution']/b))
    return dict(trials=trials,parts=comparisons,commands=112,outputs=3584,
        execution_ratio=sum(m['total']['execution'] for m in baseline)/sum(m['total']['execution'] for m in candidate),
        region_ratio=sum(m['total']['region'] for m in baseline)/sum(m['total']['region'] for m in candidate),
        baseline_region_cycles=[m['total']['region'] for m in baseline],candidate_region_cycles=[m['total']['region'] for m in candidate],
        full_k=True,full_n=False,whole_model=False,preparation_included=True,cold_weight_repack_included=False,
        candidate_accepted_for_production=False)
