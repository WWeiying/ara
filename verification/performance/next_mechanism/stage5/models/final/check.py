"""Whole model content plus scoped native-entry TB evidence, never RTL timing."""
import importlib.util
import json
from pathlib import Path
import re


def require(ok, message):
    if not ok: raise ValueError(message)


def native_entries(lines, symbols):
    mode = step = None; active = False; ended = False
    counts = {(m,s):dict(qbs=0,pv_prepare=0) for m in (0,1) for s in range(3)}
    starts = {symbols['qbs_native_execute_command'][0]:'qbs',
              symbols['akv_experimental_resident_pv_prepare'][0]:'pv_prepare'}
    for line in lines:
        if line.startswith('STAGE5_STEP_BEGIN '):
            f=dict(word.split('=',1) for word in line.split()[1:]); mode=int(f['requested']); step=int(f['step'])
            require((mode,step) in counts,'Unknown model phase'); active=False
        elif line.startswith('BIND_COUNTER '):
            f=dict(word.split('=',1) for word in line.split()[1:]); active=f['when']=='before'
        elif line.startswith('STAGE5_STEP_END '): mode=step=None
        elif line.startswith('STAGE5_NUMERICAL_PAIR_ONLY '): ended=True
        elif line.startswith('Trace '):
            match=re.fullmatch(r'Trace 0: (?:0x)?[0-9a-f]+ \[[0-9a-f]+/([0-9a-f]+)/[0-9a-f]+/[0-9a-f]+\].*',line.rstrip())
            require(match is not None,'Malformed/wrong-hart TB trace')
            pc=int(match[1],16)
            require(any(a<=pc<b for n,(a,b) in symbols.items() if n in
                ('qbs_native_execute_command','akv_experimental_resident_pv_prepare')), 'Unfiltered native TB')
            require(active and not ended and (mode,step) in counts,'Native entry outside decode snapshot')
            if pc in starts: counts[(mode,step)][starts[pc]]+=1
    return counts


def check(directory):
    out=Path(directory)
    spec=json.loads((out/'spec.json').read_text()); pcs=json.loads((out/'pcs.json').read_text())
    symbols=json.loads((out/'symbols.json').read_text())
    module_spec=importlib.util.spec_from_file_location('frozen_model_content_check',out/'inputs/binding_check.py')
    m=importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(m)
    with (out/'guest.log').open() as stream: result=m.check_lines(stream,spec,pcs)
    with (out/'guest.log').open() as stream: entries=native_entries(stream,symbols)
    with (out/'guest.log').open() as stream: exits=[line.strip() for line in stream if line.startswith('GUEST_TEST_EXIT=')]
    require(exits==['GUEST_TEST_EXIT=0'],'Missing/failed/duplicate Linux child exit')
    for phase in result['phases']:
        key=(phase['requested'],phase['step'])
        require(entries[key]['qbs']>0,'No actual QBS native entry for model phase')
        require(entries[key]['pv_prepare']==phase['architectural'].get('pv',0),'PV preparation entry count differs')
    expected=sum(row['native_qbexec'] for row in result['qbs'].values())
    require(all(sum(entries[(mode,s)]['qbs'] for s in range(3))==expected for mode in (0,1)),
            'QBS native-entry hits differ from complete command summaries')
    result.update(native_entry_tb_hits=[dict(requested=k[0],step=k[1],**v) for k,v in entries.items()],
                  linux_child_exit_checked=True,scoped_native_entry_hits_checked=True,
                  instruction_retirement_claim=False,rtl_or_model_speed_claim=False)
    return result
