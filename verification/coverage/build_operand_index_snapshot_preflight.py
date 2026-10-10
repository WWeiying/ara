"""One ordinary RVV restart case: software proof only, never launches DUT."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import build_gap101_preflight as old
from closure_point_inventory import points, read_xml

s = old.shared
ROOT, OUT = old.ROOT, old.OUT
BASE = OUT / 'akv-lifecycle-offline-admitted-724-parent-20261006-01'
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/voperand_index_snapshot_restart.c'
CHECKS = 457
WORD = (3 << 26) | (1 << 25) | (8 << 20) | (6 << 12) | (8 << 7) | 7
SYMBOLS = ('tohost', 'g75_result', 'num_failed', 'g75_trap', 'trap_fail',
           'replay_dump', 'replay_csr', 'indices', 'source',
           'replay_load_indices', 'replay_indexed_load')


def require(value, message):
    if not value:
        raise ValueError(message)


def images():
    offsets = [((17*i+3)%256)*4 for i in range(64)]
    data = [0xa5170300 ^ (131*i) for i in range(256)]
    after = [data[offsets[i]//4] if 13 <= i < 37 else offsets[i] for i in range(64)]
    return offsets, data, after


def validate(commits, symbols, trace):
    require('exception ' not in trace and not any(c.pc == symbols['trap_fail'] for c in commits),
            'Unexpected software trap')
    writes = {a:v for c in commits for a,v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a,v in c.memory_accesses
                if a == symbols['tohost'] and v is not None]
    require(terminal == [1] and writes.get(symbols['g75_result']) == CHECKS and
            writes.get(symbols['g75_result']+4) == writes.get(symbols['num_failed']) == 0,
            'Software check count/terminal differs')
    offsets, data, after = images()
    expected = {'indices': offsets, 'source': data,
                'replay_dump': [0x07070707]*32 + after + [0x0a0a0a0a]*32,
                'replay_csr': [37,17,13,0,37,0], 'g75_trap': [0,0,0]}
    for name, values in expected.items():
        size = 8 if name in ('replay_csr','g75_trap') else 4
        for i, value in enumerate(values):
            require(writes.get(symbols[name]+size*i) == value,
                    'Independent software output differs: %s[%d]' % (name,i))
    operations = [c for c in commits if c.pc == symbols['replay_indexed_load']]
    require(len(operations) == 1, 'Indexed load population differs')
    c = operations[0]
    require(c.instruction & ~(31 << 15) == WORD and
            (c.vector_sew,c.vector_lmul,c.vector_vl,c.vector_vstart) == (32,'m2',37,13) and
            c.vector_tail_agnostic is False and c.vector_mask_agnostic is False,
            'Indexed opcode/configuration differs')
    require(set(c.vector_writes) == {8,9}, 'Indexed destination group differs')
    blob = b''.join(v.to_bytes(4,'little') for v in after)
    require(all(c.vector_writes[r] == int.from_bytes(blob[(r-8)*128:(r-7)*128],'little')
                for r in (8,9)), 'Independent complete destination image differs')
    return dict(status='SPIKE_SOFTWARE_ORACLE_PASS_NOT_DUT', checks=CHECKS,
                active_destination_bytes=96, destination_image_bytes=256,
                protected_neighbor_bytes=256, unchanged_input_bytes=1280,
                csr_words=6, traps=0, scalar_comparison_qualified=False,
                measured_coverage_gain=None, coverage_admitted=False)


def target_evidence():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), 'Aliased input')
        sha = s.sha(path)
        require(expected is None or sha == expected, 'Input identity differs: '+str(path))
        pins[str(path)] = sha
        return path
    manifest = json.loads(pin(BASE/'admission-manifest.json').read_bytes())
    def baseline(name):
        path = BASE/name
        return pin(path,manifest['output_pins'][str(path)])
    state = json.loads(baseline('status.json').read_bytes())
    bits = json.loads(baseline('combined-bits.json').read_bytes())
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            state['aggregate_passed'] == len(bits['tests']) == len(set(bits['tests'])) == 724,
            'Not formal724 PASS-only population')
    require(baseline('combined-inputs.txt').read_text().splitlines() ==
            [str(old.BUILD/'sim/simv.vdb'), *bits['tests']], 'Formal724 membership differs')
    build = json.loads(pin(old.BUILD/'build-source-pins.json').read_bytes())
    sources = {}
    for relative in ('hardware/src/lane/operand_requester.sv','hardware/src/lane/operand_queue.sv',
                     'hardware/src/lane/operand_queues_stage.sv','hardware/src/lane/lane.sv',
                     'hardware/include/ara_pkg.sv','hardware/include/rvv_pkg.sv',
                     'hardware/src/lane/lane_sequencer.sv','hardware/src/ara_dispatcher.sv'):
        original = ROOT/relative
        chosen = (OUT/'old-image-source-evidence-20261006-01'/original.name
                  if original.name in ('lane_sequencer.sv','ara_dispatcher.sv') else original)
        sources[relative] = str(pin(chosen,build[str(original)]))
    lane = Path(sources['hardware/src/lane/lane_sequencer.sv']).read_text()
    dispatcher = Path(sources['hardware/src/ara_dispatcher.sv']).read_text()
    require('idx_first_aggregate_word * idx_elems_per_lane_word' in lane and
            'source_snapshot_replay: pe_req.source_snapshot_replay_vs2' in lane and
            'indexed_load_groups_overlap = ara_req.op == VLXE' in dispatcher and
            'ara_req.source_snapshot_replay_vs2 = 1\'b1' in dispatcher,
            'Frozen producer predicate chain differs')
    design = s.Design(old.BUILD/'sim/simv.vdb')
    for relative, sha in bits['design'].items():
        pin(design.db/relative,sha)
    shape_path = pin(design.db/'shape/cond.verilog.shape.xml')
    pin(design.db/'auxiliary/verilog.sourceinfo.xml')
    root = read_xml(shape_path)
    targets = []
    for lane_id in range(4):
        scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_requester' % lane_id
        require(design.source(scope)['resolved_path'] == str(ROOT/'hardware/src/lane/operand_requester.sv'),
                'Wrong compiled source owner')
        row = bits['metrics']['cond'][scope]
        nodes = [n for n in root if n.get('id') == design.hierarchy[scope].get('id')]
        require(len(nodes) == 1 and nodes[0].get('chksum') == row['checksum'] == '1592560956'
                and row['width'] == 1256, 'Exact compiled condition shape differs')
        mapped = {p['raw_index']:p for p in points('cond',nodes[0],row['width'])}
        for index, line, vector in ((786,'427','1'),(799,'535','01'),(1200,'359','01')):
            p = mapped[index]
            require((p['line'],p['vector']) == (line,vector) and '[6]' in p['expression'],
                    'Wrong requester6 compiled coordinate')
            require(not int(row['bits'],16)&(1 << (row['width']-1-index)), 'Target already hit724')
            targets.append(dict(scope=scope,metric='cond',point=p,width=row['width'],
                                checksum=row['checksum'],hit_before=False))
    duplicate = pin(ROOT/'apps/riscv-tests/isa/rv64uv/vindexed_vstart_edges.c')
    text = duplicate.read_text()
    overlap = text.split('static void test_overlapping_indexed_load(void)',1)[1].split('\nint main',1)[0]
    require('csrw vstart' not in overlap and 'vloxei32.v v28' in overlap,
            'Dedup fixture changed; reassess overlap restart boundary')
    s.check(pins)
    return dict(status='RAW724_REACHABLE_TARGET_HYPOTHESIS_NOT_MEASURED',pins=pins,
                baseline=str(BASE),sources=sources,targets=targets,
                predicate_chain='VLXE overlapping vd/index -> retain index snapshot -> SlideAddrGenA requester6 replay; '
                'vstart13/e32 -> first aggregate word1 -> per-lane vstart2 -> replay word offset1',
                dedup='Existing fixture separates nonoverlap vstart and overlap vstart0; new equal-EEW overlap restart.',
                expected_cond_coordinates=12,expected_branch_increment=None,
                native_ids_reinterpreted=False,exclusions_generated=False,vcs_started=False,
                runtime_hit_required=True,budget_seconds=300)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output = parser.parse_args().output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh output required')
    evidence = target_evidence()
    include = ROOT/'verification/tests'
    paths = [APP,Path(__file__).resolve(),Path(__file__).with_name('test_build_operand_index_snapshot_preflight.py'),
             include/'gap75_start.S',include/'gap75.ld',s.LLVM/'clang',s.LLVM/'llvm-readelf',s.SPIKE]
    paths += [Path(m.__file__).resolve() for m in tuple(sys.modules.values())
              if getattr(m,'__file__',None) and str(ROOT/'verification') in str(m.__file__)]
    pins = s.merge_pins(evidence['pins'],{str(p):s.sha(p) for p in paths})
    s.check(pins)
    output.mkdir()
    s.save(output/'input-pins.json',pins)
    s.save(output/'target-before.json',evidence)
    try:
        elf = output/'input.elf'
        command = [str(s.LLVM/'clang'),'--target=riscv64-unknown-elf','-march=rv64gcv_zfh_zvfh',
                   '-mabi=lp64d','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-O2',
                   '-fno-vectorize','-fno-slp-vectorize','-ffreestanding','-DVLEN=1024','-DNR_LANES=4',
                   '-I'+str(include),'-fuse-ld=lld','-nostdlib','-T'+str(include/'gap75.ld'),
                   str(include/'gap75_start.S'),str(APP),'-o',str(elf)]
        s.save(output/'compile-command.json',command)
        with (output/'compile.log').open('x') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        symbols = {n:s._elf_symbol(elf,s.LLVM/'llvm-readelf',n) for n in SYMBOLS}
        command = [str(s.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                   '-l','--log-commits',str(elf)]
        s.save(output/'spike-command.json',command)
        with (output/'spike.stdout').open('x') as stdout,(output/'spike.trace').open('x') as trace:
            subprocess.run(command,stdout=stdout,stderr=trace,check=True,timeout=120)
        result = validate(s.parse_spike_commits(output/'spike.trace'),symbols,(output/'spike.trace').read_text())
        s.save(output/'spike-validation.json',result)
        s.check(pins)
        outputs = {str(p):s.sha(p) for p in output.iterdir() if p.is_file()}
        s.save(output/'preflight-manifest.json',dict(status='OPERAND_INDEX_SNAPSHOT_SPIKE_PREFLIGHT_PASS_NOT_DUT',
            pins=pins,output_pins=outputs,input_elf=str(elf),symbols=symbols,validation=result,
            baseline_tests=724,vcs_started=False,coverage_admitted=False))
        print(json.dumps(dict(output=str(output),seal=s.sha(output/'preflight-manifest.json'),validation=result)))
    except Exception as error:
        s.save(output/'failure.json',dict(status='PREFLIGHT_FAILED_NOT_DUT_FAILURE',reason=str(error)))
        raise


if __name__ == '__main__':
    main()
