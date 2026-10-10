"""Exact slot15/bit15 reset with sixteen pre-reset states and native recovery gold."""
import argparse
import ast
import inspect
import textwrap
from pathlib import Path
from types import FunctionType, SimpleNamespace

import qualify_qbs_affine_external_reset as old
import run_qbs_affine_aux_slot15 as run
import recheck_qbs_affine_native_dependencies as closure

life, require = old.life, old.require
REL = run.SCOPE[len('ara_tb.'):]
WIDTHS = dict(clk=1,rst_n=1,**{REL+'.entry_valid_q':16},
              **{REL+'.entry_state_q[%d]'%i:3 for i in range(16)})


def parse(source):
    reader = old.vcd_parser.vcd
    return FunctionType(reader.__code__,dict(reader.__globals__,ROOT='ara_tb',WIDTHS=WIDTHS))(source)


def all_slots(iterator):
    marker, decl = next(iterator)
    require(marker == 'declarations','Missing exact waveform declarations')
    valid_id = decl[run.SCOPE+'.entry_valid_q']['code']
    reset_id = decl['ara_tb.rst_n']['code']
    ids = [decl[run.SCOPE+'.entry_state_q[%d]'%i]['code'] for i in range(16)]
    snapshot, release, reused = None, None, {}
    for time, before, after in iterator:
        if before.get(reset_id) == '1' and after.get(reset_id) == '0':
            require(snapshot is None,'Repeated reset')
            require(before.get(valid_id) == '1'*16 and all(before.get(code) == '001' for code in ids),
                    'Not all sixteen slots valid in AUX immediately before reset')
            snapshot = dict(time=time,valid=before[valid_id],states=[1]*16)
        if snapshot is None: continue
        if after.get(reset_id) == '0':
            require(after.get(valid_id) == '0'*16 and all(after.get(code) == '001' for code in ids),
                    'Reset did not clear all valid bits and retain AUX states')
        if before.get(reset_id) == '0' and after.get(reset_id) == '1':
            require(release is None,'Repeated release')
            release = time
        if release is None or time <= release: continue
        prior, new = before.get(valid_id,''),after.get(valid_id,'')
        require(len(prior) == len(new) == 16 and set(prior+new) <= {'0','1'},'Unknown valid after release')
        for slot, code in enumerate(ids):
            if slot in reused: continue
            if prior[-1-slot] == '0' and new[-1-slot] == '1':
                require(before.get(code) == '001' and after.get(code) == '000',
                        'First slot reuse is not retained AUX -> DOT')
                reused[slot] = dict(slot=slot,time=time,retained_state=1,allocated_state=0)
    require(snapshot is not None and release is not None and set(reused) == set(range(16)),
            'Incomplete reset / sixteen-slot reallocation')
    return dict(pre_reset=snapshot,release_timestamp=release,reused_slots=[reused[i] for i in range(16)])


def selected_wave(source, output, selection):
    require(selection == run.configuration('aux'),'Exact slot15 selection only')
    full = all_slots(iter(parse(source)))
    life.save(output.parent/'full-slot-reset-reuse.json',full)
    iterator = iter(parse(source)); _,decl = next(iterator)
    names = ['ara_tb.clk','ara_tb.rst_n',selection['ext_target'],run.SCOPE+'.entry_valid_q']
    codes = [decl[name]['code'] for name in names]
    with output.open('x') as stream:
        stream.write('$timescale 100fs $end\n$scope module ara_tb $end\n')
        for index,(name,width) in enumerate(zip(names,(1,1,3,1))):
            label = selection['ext_guard'] if index == 3 else name
            stream.write('$var reg %d %s \\%s $end\n'%(width,'abcd'[index],label[7:]))
        stream.write('$upscope $end\n$enddefinitions $end\n')
        for time,_,after in iterator:
            stream.write('#%d\n'%time)
            for index,code in enumerate(codes):
                bits = after.get(code,'x')
                if index == 3:
                    require(len(bits) == 16,'Missing full packed guard')
                    bits = bits[-1-15]
                stream.write(('b%s %s\n' if index == 2 else '%s%s\n')%(bits,'abcd'[index]))
    return dict(source_target=names[2],target_width=3,mda_index=15,source_guard=names[3],
                guard_width=16,selected_guard_bit=15,converter_memory_objects_required=True,
                source_sha256=life.digest(source),selected_sha256=life.digest(output))


def slot_reuse(selected, selection, release):
    full = life.read_bound(selected.parent/'full-slot-reset-reuse.json',
                           life.digest(selected.parent/'full-slot-reset-reuse.json'))
    require(full['release_timestamp'] == release and selection == run.configuration('aux'),
            'Selected reset and full-slot reset differ')
    return full['reused_slots'][15]


def collector(namespace):
    # Only the three frozen population literals are changed, never native oracle code.
    tree = ast.parse(textwrap.dedent(inspect.getsource(old.collect)))
    sites = [node for node in ast.walk(tree) if isinstance(node,ast.Constant) and type(node.value) is int and node.value == 746]
    require(len(sites) == 2,'Frozen collector population literal structure drift')
    for node in sites: node.value = 760
    exec(compile(ast.fix_missing_locations(tree),__file__,'exec'),namespace)
    return namespace['collect']


def collect(source, seal, output):
    dependencies = closure.source_pins()
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_qualify_qbs_affine_aux_slot15.py')):
        dependencies[str(path)] = life.digest(path)
    def check(pins): return life.check(life.merge_pins(pins,dependencies))
    def save(path,value):
        if path.name == 'evidence-pins.json': value = life.merge_pins(value,dependencies)
        life.save(path,value)
    private = SimpleNamespace(**dict(vars(life),check=check,save=save))
    backend = run.backend()
    backend.__file__ = run.__file__
    namespace = dict(old.collect.__globals__,run=backend,life=private,BASE=run.BASE,BASE_SHA=run.BASE_SHA,
                     selected_wave=selected_wave,slot_reuse=slot_reuse)
    collector(namespace)('aux',source,seal,output)
    check(dependencies)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--seal',required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    collect(a.run.resolve(),a.seal,a.output.resolve())
