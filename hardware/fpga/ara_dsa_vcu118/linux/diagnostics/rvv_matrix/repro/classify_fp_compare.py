"""Classify mandatory prestart preservation for disjoint-destination probes."""
import re


def parse(output):
    raw=[]
    data={}
    for line in output.splitlines():
        if not line.startswith(('RVV_FP_COMPARE_RAW ', 'RVV_FP_COMPARE_BYTE ')):
            continue
        values={}
        for token in line.split()[1:]:
            match=re.fullmatch(r'(\w+)=(\d+)',token)
            if not match or match[1] in values:
                raise ValueError('Malformed diagnostic fields')
            values[match[1]]=int(match[2])
        if line.startswith('RVV_FP_COMPARE_RAW '):
            raw.append(values)
        else:
            if set(values)!={'index','actual'} or values['index'] in data or values['actual']>255:
                raise ValueError('Invalid or duplicate byte')
            data[values['index']]=values['actual']
    if len(raw)!=1 or set(raw[0])!={'cap','returned_vstart','actual_flags','guard_before','guard_after'}:
        raise ValueError('Missing or ambiguous raw result')
    info=raw[0]
    if not 0<info['cap']<=1024 or info['actual_flags']>31:
        raise ValueError('Invalid capacity or flags')
    if set(data)!=set(range((info['cap']+7)//8)):
        raise ValueError('Incomplete result bytes')
    return info,[data[i] for i in range(len(data))]


def classify(case, board, reference):
    """ELF identity must be checked by caller; this does not prove original equivalence."""
    if not re.fullmatch(r'rvv_detail_fp_compare_restart(?:_unmasked)?_e(?:16|32|64)_m(?:f[24]|[1248])',case['name']):
        raise ValueError('Only disjoint v24 restart probes have this sentinel oracle')
    if board.get('status')!='failed' or board.get('exit_code')!=1:
        raise ValueError('Board did not finish with a numerical failure')
    if not reference.get('passed') or reference.get('exit_code')!=0:
        raise ValueError('No passing reference')
    actual,data=parse(board['output'])
    golden,expected=parse(reference['output'])
    if actual['cap']!=golden['cap']:
        raise ValueError('Different vector capacity')
    stimulus=case['measured_stimulus']
    start,vl=stimulus['vstart'],stimulus['vl']
    if not 0<=start<=actual['cap'] or not 0<=vl<=actual['cap']:
        raise ValueError('Stimulus exceeds capacity')
    limit=actual['cap'] if start>=vl else start
    if golden['returned_vstart'] or golden['guard_before']!=91 or golden['guard_after']!=91:
        raise ValueError('Reference state disagrees with sentinel oracle')
    differences=[]
    for i in range(limit):
        old=(91>>(i%8))&1
        if (expected[i//8]>>(i%8))&1 != old:
            raise ValueError('Reference modified a mandatory preserved bit')
        value=(data[i//8]>>(i%8))&1
        if value!=old:
            differences.append(dict(element=i,expected=old,actual=value))
    return dict(prestart_mismatches=differences,checked_preserved_elements=limit,
        returned_vstart=actual['returned_vstart'],actual_flags=actual['actual_flags'],
        guards_intact=actual['guard_before']==91 and actual['guard_after']==91,
        tail_bits_used_as_evidence=False,original_failure_equivalence_proven=False,
        internal_rtl_root_cause_proven=False)
