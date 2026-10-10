#!/usr/bin/env python3
"""Bound one old-image raw target and its M4/phase12 byte geometry; no tools."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASELINE = OUT / 'gap80-old-image-20261006-01'
OLD_PLAN = OUT / 'closure90-current-20261005-01/plan.json'
BUILD = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
TARGET_BEFORE = OUT / 'gap81-m4-phase12-target-before-20261006-01.json'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank0'
TARGET = dict(scope=SCOPE, metric='cond', raw_index=400, native_id='150',
              checksum='2250470448', vector='1',
              expression="(activation_target[0].offset[3:0] == 4'(1))")
RTL = ['hardware/include/qbs_pkg.sv', 'apps/common/qbs_abi.h',
       *['hardware/src/vlsu/qbs/' + n + '.sv' for n in
         ('qbs_descriptor_decoder', 'qbs_engine', 'qbs_read_engine',
          'qbs_compute_engine', 'qbs_block_adapter', 'qbs_payload_buffer', 'qbs_commit')]]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bit(row, index):
    require(type(index) is int and 0 <= index < row['width'], 'raw index outside bitmap')
    value = format(int(row['bits'], 16), '0%db' % row['width'])
    require(len(value) == row['width'], 'bitmap overflow')
    return value[index]


def analyze():
    seals = read(OLD_PLAN.parent / 'plan.sha256.json')
    require(seals == {str(OLD_PLAN): sha(OLD_PLAN)}, 'old plan seal differs')
    plan = read(OLD_PLAN)
    require(plan['files'][str(BUILD)] == sha(BUILD), 'old build manifest differs')
    build = read(BUILD)
    source_pins = {}
    for rel in RTL:
        path = ROOT / rel
        digest = sha(path)
        if rel != 'apps/common/qbs_abi.h':
            require(build[str(path)] == digest, 'old RTL source mismatch: ' + rel)
        source_pins[str(path)] = digest
    bits = read(BASELINE / 'combined-bits.json')
    status = read(BASELINE / 'status.json')
    require(status['coverage_status'] == 'COMPLETE' and status['aggregate_passed'] == 687
            and status['image'] == plan['simv'], 'wrong completed gap80 image/population')
    require(bits['design'] == read(OLD_PLAN.parent / 'combined-bits.json')['design'],
            'old design shape differs')
    row = bits['metrics']['cond'][SCOPE]
    require(str(row['checksum']) == TARGET['checksum'] and bit(row, 400) == '0',
            'raw400 no longer an old-image zero')
    db = Path(plan['design_vdb']) / 'snps/coverage/db'
    sys.path.insert(0, str(ROOT / 'verification/coverage'))
    import closure_point_inventory as inventory
    shape_path = db / 'shape/cond.verilog.shape.xml'
    design_path = db / 'design/verilog.design.xml'
    for rel, digest in bits['design'].items():
        require(sha(db / rel) == digest, 'compiled shape drift: ' + rel)
    definitions = inventory.read_xml(shape_path)
    modules = [d for d in inventory.read_xml(design_path).findall('srcdef')
               if d.get('name') == 'qbs_block_adapter']
    matches = []
    for module in modules:
        for definition in definitions:
            if definition.get('id') == module.get('id') and definition.get('chksum') == TARGET['checksum']:
                matches.extend(p for p in inventory.points('cond', definition, row['width'])
                               if p['raw_index'] == 400)
    require(len(matches) == 1 and all(matches[0][k] == TARGET[k]
            for k in ('native_id', 'vector', 'expression')), 'raw/native target mapping differs')
    # AXI compacts an initial four-byte beat, then starts full beats at 4+16*n.
    mapped = [dict(byte=b, context=(132+b-16)&3,
                   native_offset=4+((132+b-16)>>2),
                   payload_offset=(132+b-16)>>2) for b in range(16)]
    require([x['native_offset'] for x in mapped] == [33]*4+[34]*4+[35]*4+[36]*4,
            'M4 mapping prediction differs')
    pending_mask = sum(1 << x['byte'] for x in mapped if x['payload_offset']//32 == 1)
    require(pending_mask == 0xf000 and mapped[0]['native_offset'] & 15 == 1,
            'pending target prediction differs')
    paths = [OLD_PLAN, OLD_PLAN.parent/'plan.sha256.json', BUILD,
             BASELINE/'status.json', BASELINE/'combined-bits.json',
             OLD_PLAN.parent/'combined-bits.json', shape_path, design_path, Path(__file__)]
    if TARGET_BEFORE.exists():
        paths.append(TARGET_BEFORE)
    source_pins.update({str(p): sha(p) for p in paths})
    return dict(status='STATIC_PREDICTION_NOT_RTL_PASS', target=TARGET,
                source_hashes=source_pins, image=plan['image'], simv=plan['simv'],
                design_vdb=plan['design_vdb'], mapped_beat=mapped,
                pending_mask=pending_mask, selected_range_offset=132,
                custom_word='0x06b5045b', vl=1, m=4, n=1, k_blocks=1,
                weight_profile='Q5_K', activation_profile='Q8_K',
                activation_layout='M4_INTERLEAVED', activation_mod16=12,
                data_scope='known native directed fixture, not captured model data',
                measured_gain=None, simulations_started=False, waivers_applied=False)
