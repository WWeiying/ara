"""One 600s same-ELF FINAL_DRAIN reset experiment; no automatic qualification/admission."""
import argparse
import json
import struct
from pathlib import Path
from types import FunctionType
import run_gap113_full8_cached as cached
import targeted_toggle_evidence_v2 as t

life = cached.life
RUN = life.OUT / 'gap113-cached-final-drain-reset-old-image-742-agent-20261007-01'
BASE = life.OUT / 'gap113-full8-cached-offline-admitted-742-agent-20261007-01'
BASE_SHA = 'f07f7ccdcfc7257faad21aabdc45a48008658c70ee26abda275065f1e204a730'
BUILD = life.OUT / 'repaired-aligned-build-20260930-01'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_fp_accumulator'
ARGS = ['+ARA_UVM_RESET_ON_AXI=state', '+ARA_UVM_RESET_STATE_TARGET=qbs_compute_final_drain',
        '+ARA_UVM_TRACE_LIMIT=100000', '+ARA_CONTRACT_TRACE_LIMIT=100000']


def loaded_segments(blob):
    t.require(blob[:5] == b'\x7fELF\x02' and blob[5] == 1, 'ELF64 little-endian required')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', blob)
    rows = [struct.unpack_from('<IIQQQQQQ', blob, h[5]+i*h[9]) for i in range(h[10])]
    loads = [dict(address=p[4], filesz=p[5], memsz=p[6]) for p in rows if p[0] == 1 and p[6]]
    t.require(loads and all(p['filesz'] == p['memsz'] and p['filesz'] > 0 for p in loads),
              'Unproven reset reload for BSS-only/trailing memory')
    return loads


def prepare():
    out, record = cached.run_adapter().prepare(RUN)
    t.require(life.digest(BASE / 'admission-manifest.json') == BASE_SHA, 'Formal742 drift')
    pins = record['pins']
    ledger = BUILD / 'build-source-pins.json'
    t.require(life.digest(ledger) == '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b', 'Build pins drift')
    source = json.loads(ledger.read_bytes())
    names = ['hardware/tb/ara_tb.sv', 'hardware/tb/ara_commit_monitor.sv',
             'hardware/src/ara_soc.sv', 'hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv',
             'hardware/deps/cva6/corev_apu/tb/dpi/elfloader.cc',
             'hardware/src/vlsu/qbs/qbs_fp_accumulator.sv',
             'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
             'verification/uvm/ara_cvxif_uvm_pkg.sv', 'verification/uvm/ara_acc_contract_monitor.sv']
    for name in names:
        p = life.ROOT / name
        t.require(str(p) in source and life.digest(p) == source[str(p)], 'Frozen source mismatch: '+name)
        pins = life.merge_pins(pins, {str(p): source[str(p)]})
    row = json.loads((BASE / 'combined-bits.json').read_bytes())['metrics']['fsm'][SCOPE]
    shape = BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml'
    definition = [d for d in t.xml(shape).iter('fsmdef') if d.get('name') == 'qbs_fp_accumulator']
    t.require(len(definition) == 1 and definition[0].get('chksum') == row['checksum'], 'FSM identity differs')
    bits = format(int(row['bits'], 16), '0%db' % row['width']); offset = 0; targets = []
    for machine in definition[0].find('fsmshape'):
        states = list(machine.findall('state')); arcs = list(machine.findall('transition'))
        ids = {s.get('id'): s.get('name') for s in states}
        matches = [i for i, a in enumerate(arcs) if ids[a.get('fromid')] == 'FP_SCALE_MULTIPLY'
                   and ids[a.get('toid')] == 'FP_DOT_CONVERT']
        t.require(len(matches) == 1, 'Ambiguous named arc')
        index = offset + len(states) + matches[0]
        targets.append(dict(machine=machine.get('name'), machine_checksum=machine.get('chksum'),
            from_state='FP_SCALE_MULTIPLY', to_state='FP_DOT_CONVERT', line=366,
            compiled_serialized_position=index, before_hit=bits[index] == '1'))
        offset += len(states) + len(arcs)
    t.require(offset == row['width'] == 288 and len(targets) == 16 and
              not any(x['before_hit'] for x in targets), 'No exact uncovered16 target set')
    old = life.OUT / 'targeted-toggle-offline-admitted-741-parent-20261007-01/admission-manifest.json'
    prior = json.loads(old.read_bytes())
    t.require(cached.ELF_SHA not in prior['input_pins'].values(), 'Same ELF already in741; recheck reset dedup')
    for p in (ledger, old, shape, BASE/'combined-bits.json', BASE/'admission-manifest.json',
              Path(__file__).resolve(), Path(__file__).with_name('test_run_gap113_cached_reset.py')):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    record.update(pins=pins, command=record['command']+ARGS, targets=targets,
        elf_load_segments=loaded_segments(Path(record['preflight']['binary']).read_bytes()),
        reset_contract=dict(trigger='one negedge QBS_FINAL_DRAIN; reset held4negedges',
            memory='frozen VCS DRAM SimInit=random copies ELF-loaded init_val on reset',
            fp_state='valid/inflight clear; entry_state retained until fresh accepted request writes DOT',
            epoch0='must cancel live custom/backend; no custom VRF completion crossing reset',
            epoch1='complete unchanged2commands:41checks/fullVRF/sourceguard/24CSR/native gold',
            independent_accounting='check_real_uvm_log reset_kind=state + epoch VID/vector digest; '
                'request=response+aborted, allocation=completion+aborted; no trace truncation',
            full_scalar_ISA=False, spike_custom_ISA=False),
        budget_basis='Same cached normal CPU217.650s; first aborted command plus fresh normal run bounded600s',
        coverage_admitted=False, automatic_retry=False)
    life.check(pins)
    return out, record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run')); p.add_argument('--prepared-seal')
    a = p.parse_args(); out, record = prepare(); path = RUN.with_name(RUN.name+'.prepared.json')
    if a.mode == 'prepare':
        t.require(not path.exists() and not a.prepared_seal, 'Fresh prepare only')
        life.save(path, record)
        print(json.dumps(dict(prepared=str(path), seal=life.digest(path), targets=16, budget=600)))
    else:
        t.require(a.prepared_seal and life.read_bound(path, a.prepared_seal) == record, 'Prepared drift')
        namespace = dict(vars(cached.frozen_run.reused), command=lambda output: record['command'])
        FunctionType(cached.frozen_run.reused.run.__code__, namespace)(out, record)


if __name__ == '__main__': main()
