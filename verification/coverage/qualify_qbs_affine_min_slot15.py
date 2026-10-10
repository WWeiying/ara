"""MIN_SCALE slot15: full sixteen-slot snapshot/reuse plus original native gold."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace

import qualify_qbs_affine_aux_slot15 as template
import run_qbs_affine_min_slot15 as run

life,require = template.life,template.require


def all_slots(iterator):
    marker,decl = next(iterator)
    require(marker == 'declarations','Missing waveform declarations')
    valid_id,reset_id = decl[run.SCOPE+'.entry_valid_q']['code'],decl['ara_tb.rst_n']['code']
    ids = [decl[run.SCOPE+'.entry_state_q[%d]'%i]['code'] for i in range(16)]
    snapshot,release,reused = None,None,{}
    for time,before,after in iterator:
        if before.get(reset_id) == '1' and after.get(reset_id) == '0':
            require(snapshot is None,'Repeated reset')
            require(before.get(valid_id) == '1'*16 and all(before.get(code) == '011' for code in ids),
                    'All sixteen slots must be valid MIN_SCALE immediately before reset')
            snapshot = dict(time=time,valid=before[valid_id],states=[3]*16)
        if snapshot is None: continue
        if after.get(reset_id) == '0':
            require(after.get(valid_id) == '0'*16 and all(after.get(code) == '011' for code in ids),
                    'Reset did not retain all MIN_SCALE states and clear valid bits')
        if before.get(reset_id) == '0' and after.get(reset_id) == '1':
            require(release is None,'Repeated release')
            release = time
        if release is None or time <= release: continue
        prior,new = before.get(valid_id,''),after.get(valid_id,'')
        require(len(prior) == len(new) == 16 and set(prior+new) <= {'0','1'},'Unknown valid after release')
        for slot,code in enumerate(ids):
            if slot not in reused and prior[-1-slot] == '0' and new[-1-slot] == '1':
                require(before.get(code) == '011' and after.get(code) == '000',
                        'First slot reuse must be retained MIN_SCALE -> DOT')
                reused[slot] = dict(slot=slot,time=time,retained_state=3,allocated_state=0)
    require(snapshot is not None and release is not None and set(reused) == set(range(16)),
            'Incomplete sixteen-slot reset/reuse')
    return dict(pre_reset=snapshot,release_timestamp=release,reused_slots=[reused[i] for i in range(16)])


def selected_wave(source,output,selection):
    # The immutable bit15/MDA projection is reused; only the authorized phase changes.
    require(selection == run.configuration('min_scale'),'Exact MIN slot15 binding')
    private_run = SimpleNamespace(**dict(vars(run),configuration=lambda phase:run.configuration('min_scale')))
    ns = dict(template.selected_wave.__globals__,run=private_run,all_slots=all_slots)
    return FunctionType(template.selected_wave.__code__,ns)(source,output,selection)


def slot_reuse(selected,selection,release):
    require(selection == run.configuration('min_scale'),'Exact MIN slot15 binding')
    private_run = SimpleNamespace(**dict(vars(run),configuration=lambda phase:run.configuration('min_scale')))
    return FunctionType(template.slot_reuse.__code__,dict(template.slot_reuse.__globals__,run=private_run))(
        selected,selection,release)


def collect(source,seal,output):
    # Preserve every native oracle and epoch check in the source-complete predecessor.
    def collector(namespace):
        fn = template.collector(namespace)
        def invoke(stage,*args):
            require(stage == 'aux','Frozen template stage interface drift')
            return fn('min_scale',*args)
        return invoke
    def source_pins():
        pins = template.closure.source_pins()
        test = Path(__file__).with_name('test_qualify_qbs_affine_min_slot15.py')
        pins[str(test)] = life.digest(test)
        return pins
    ns = dict(template.collect.__globals__,run=run,selected_wave=selected_wave,slot_reuse=slot_reuse,
              closure=SimpleNamespace(source_pins=source_pins),collector=collector,__file__=__file__)
    FunctionType(template.collect.__code__,ns)(source,seal,output)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--seal',required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    collect(a.run.resolve(),a.seal,a.output.resolve())
