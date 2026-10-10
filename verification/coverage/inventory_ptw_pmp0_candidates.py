"""Configuration-bound PTW access-error candidates, not native exclusions."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from inventory_operand_debug import Design, ROOT
from closure_point_inventory import read_xml

OUT = ROOT / 'verification/out'
BASE = OUT / 'gap97-offline-admitted-706-20261006-01'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw'


def require(value, message):
    if not value:
        raise ValueError(message)


def compact(text):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S))


def source_proof(soc, config, pmp, ptw):
    soc, config, pmp, ptw = map(compact, (soc, config, pmp, ptw))
    require(soc.count('cfg.NrPMPEntries=0;') == 1 and
            soc.count('cfg.NrPMPEntries=') == 1, 'PMP override differs')
    for token in ('CVA6AraConfig_user=gen_usr_cva6_config(cva6_config_pkg::cva6_cfg);',
                  'CVA6AraConfig=build_config_pkg::build_config(CVA6AraConfig_user);',
                  '.CVA6Cfg(CVA6AraConfig)'):
        require(token in soc, 'SoC config propagation differs')
    require('cfg.NrPMPEntries=CVA6Cfg.NrPMPEntries;' in config,
            'Build config does not preserve PMP count')
    require('if(CVA6Cfg.NrPMPEntries>0)begin:gen_pmp' in pmp and
            "endelseassignallow_o=1'b1;" in pmp, 'Zero-PMP output differs')
    require('pmp#(.CVA6Cfg(CVA6Cfg))i_pmp_ptw(' in ptw and
            '.allow_o(allow_access)' in ptw, 'PTW PMP connection differs')
    require(ptw.count('state_d=PROPAGATE_ACCESS_ERROR;') == 1 and
            'if(!allow_access)beginshared_tlb_update_valid=1\'b0;ptw_pptr_n=ptw_pptr_q;'
            'if(CVA6Cfg.RVH)ptw_stage_d=ptw_stage_q;state_d=PROPAGATE_ACCESS_ERROR;end' in ptw,
            'Additional or changed access-error entry path')
    require(re.findall(r'state_q<=([^;]+);', ptw) == ['IDLE', 'state_d'],
            'State reset or capture differs')
    return dict(pmp_entries=0, allow_access=1, reset_state='IDLE',
                unreachable_state='PROPAGATE_ACCESS_ERROR',
                assumptions=['Normal operation after reset; no force or fault injection.',
                             'Frozen SoC configuration; not a generic CVA6 waiver.'],
                retained='PROPAGATE_ERROR and all ordinary page-table faults')


def candidates(node):
    rows, offset = [], 0
    for fsm in node.iter('fsmfsm'):
        states = fsm.findall('state')
        names = {s.get('id'): s.get('name') for s in states}
        for state in states:
            rows.append(dict(raw_index=offset, fsm=dict(fsm.attrib), kind='state',
                             item=dict(state.attrib), name=state.get('name'),
                             candidate=state.get('name') == 'PROPAGATE_ACCESS_ERROR'))
            offset += 1
        for transition in fsm.findall('transition'):
            source, destination = names[transition.get('fromid')], names[transition.get('toid')]
            rows.append(dict(raw_index=offset, fsm=dict(fsm.attrib), kind='transition',
                             item=dict(transition.attrib), source=source, destination=destination,
                             candidate='PROPAGATE_ACCESS_ERROR' in (source, destination)))
            offset += 1
    return rows


def inventory():
    pins = {}

    def read(path, expected=None):
        path = Path(path).absolute()
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        require(expected is None or sha == expected, 'Input drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == sha, 'Conflicting pin')
        pins[str(path)] = sha
        return raw

    manifest = json.loads(read(BUILD / 'build-source-pins.json'))
    paths = ['hardware/src/ara_soc.sv', 'hardware/deps/cva6/core/include/build_config_pkg.sv',
             'hardware/deps/cva6/core/pmp/src/pmp.sv',
             'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv']
    sources = [read(ROOT / path, manifest[str(ROOT / path)]).decode() for path in paths]
    proof = source_proof(*sources)
    state = json.loads(read(BASE / 'status.json'))
    bits = json.loads(read(BASE / 'combined-bits.json'))
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            state['aggregate_passed'] == len(bits['tests']) == len(set(bits['tests'])) == 706,
            'Not admitted706')
    design = Design(BUILD / 'sim/simv.vdb')
    for relative, expected in bits['design'].items():
        read(design.db / relative, expected)
    shape_path = design.db / 'shape/fsm.verilog.shape.xml'
    read(shape_path)
    record = bits['metrics']['fsm'][SCOPE]
    nodes = [n for n in read_xml(shape_path) if n.get('name') == 'cva6_ptw'
             and n.get('chksum') == record['checksum']
             and any(s.get('name') == SCOPE for s in n.findall('fsminst'))]
    require(len(nodes) == 1 and record['checksum'] == '3345966803', 'FSM ownership differs')
    require(design.source(SCOPE)['resolved_path'] == str(ROOT / paths[-1]), 'Source owner differs')
    rows = candidates(nodes[0])
    require(len(rows) == record['width'] == 35, 'FSM diagnostic width differs')
    selected = [r for r in rows if r['candidate']]
    require([r['raw_index'] for r in selected] == [2, 10, 11, 16], 'State/transition inventory differs')
    for row in rows:
        row['raw_hit'] = bool(int(record['bits'], 16) & (1 << (34 - row['raw_index'])))
        require(not row['candidate'] or not row['raw_hit'], 'Observed hit contradicts proof')
    # Parameter and generated hierarchy evidence is independent of raw FSM order.
    pmp_scope = SCOPE + '.i_pmp_ptw'
    require(design.source(pmp_scope)['resolved_path'] == str(ROOT / paths[2]), 'PMP source owner differs')
    require(not any(s.startswith(pmp_scope + '.gen_pmp.') for s in design.hierarchy),
            'Positive-PMP hierarchy found')
    read(Path(__file__).resolve())
    read(Path(__file__).with_name('test_inventory_ptw_pmp0_candidates.py'))
    for path, expected in list(pins.items()):
        read(path, expected)
    return dict(status='PTW_PMP0_SOURCE_CANDIDATES_NATIVE_FSM_IDENTITY_PENDING', tests=706,
                scope=SCOPE, metric='fsm', metric_checksum=record['checksum'],
                proof=proof, candidates=selected, protected=[r for r in rows if not r['candidate']],
                pins=pins, native_qualified=False, exclusions_applied=False,
                limitations=['Raw state/transition offsets are diagnostic until native DVE binding.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    path = parser.parse_args().output.absolute()
    require(path.parent == OUT and not path.exists(), 'Fresh direct output required')
    result = inventory()
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], candidates=len(result['candidates']),
                          protected=len(result['protected']))))


if __name__ == '__main__':
    main()
