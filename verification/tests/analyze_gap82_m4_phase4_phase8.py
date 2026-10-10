#!/usr/bin/env python3
"""Two M4 phase witnesses bound to old-image sources/shapes; no simulation."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
BASELINE = OUT/'gap80-old-image-20261006-01'
OLD_PLAN = OUT/'closure90-current-20261005-01/plan.json'
BUILD = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank0'
COMMANDS = [dict(id=0,phase=4,range_offset=140,pending_mask=0xfff0,native_offset=35,
                 raw_index=408,native_id='154',low_bits=3),
            dict(id=1,phase=8,range_offset=136,pending_mask=0xff00,native_offset=34,
                 raw_index=404,native_id='152',low_bits=2)]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bit(row,index):
    value = format(int(row['bits'],16),'0%db'%row['width'])
    require(len(value) == row['width'] and 0 <= index < len(value), 'invalid bitmap extent')
    return value[index]


def analyze():
    plan = read(OLD_PLAN)
    require(read(OLD_PLAN.parent/'plan.sha256.json') == {str(OLD_PLAN):sha(OLD_PLAN)},
            'old plan seal differs')
    require(plan['files'][str(BUILD)] == sha(BUILD), 'old build manifest differs')
    source_pins = {}
    build = read(BUILD)
    rtl = ['hardware/include/qbs_pkg.sv',
           *['hardware/src/vlsu/qbs/'+n+'.sv' for n in
             ('qbs_descriptor_decoder','qbs_engine','qbs_read_engine','qbs_compute_engine',
              'qbs_block_adapter','qbs_payload_buffer','qbs_commit')]]
    for relative in rtl:
        path = ROOT/relative
        require(sha(path) == build[str(path)], 'old source mismatch: '+relative)
        source_pins[str(path)] = build[str(path)]
    bits = read(BASELINE/'combined-bits.json')
    state = read(BASELINE/'status.json')
    require(state['coverage_status'] == 'COMPLETE' and state['aggregate_passed'] == 687
            and state['image'] == plan['simv'] and len(bits['tests']) == 687,
            'completed old687 baseline required')
    db = Path(plan['design_vdb'])/'snps/coverage/db'
    require(bits['design'] == read(OLD_PLAN.parent/'combined-bits.json')['design'], 'design mismatch')
    for relative,digest in bits['design'].items():
        path = db/relative
        require(sha(path) == digest, 'compiled design/shape drift')
        source_pins[str(path)] = digest
    sys.path.insert(0,str(ROOT/'verification/coverage'))
    import closure_point_inventory as inventory
    import coverage_bitmap_delta as bitmaps
    row = bits['metrics']['cond'][SCOPE]
    require(str(row['checksum']) == '2250470448', 'condition checksum differs')
    design = inventory.read_xml(db/'design/verilog.design.xml')
    shape = inventory.read_xml(db/'shape/cond.verilog.shape.xml')
    definitions = [n for m in design.findall('srcdef') if m.get('name') == 'qbs_block_adapter'
                   for n in shape if n.get('id') == m.get('id') and n.get('chksum') == row['checksum']]
    require(len(definitions) == 1, 'ambiguous condition definition')
    points = {p['raw_index']:p for p in inventory.points('cond',definitions[0],row['width'])}
    # This is only a duplicate-target check, not admission of the GAP81 run.
    files = list((OUT/'gap81-old-image-20261006-01/code.vdb/snps/coverage/db/testdata').glob('*/cond.verilog.data.xml'))
    require(len(files) == 1, 'one actual gap81 condition bitmap required')
    gap81_pin = sha(files[0])
    prior = bitmaps.read_metric(files[0])[SCOPE]
    require(sha(files[0]) == gap81_pin and (prior['checksum'],prior['width']) ==
            (row['checksum'],row['width']), 'gap81 bitmap identity/drift')
    source_pins[str(files[0])] = gap81_pin
    commands = []
    for original in COMMANDS:
        c = dict(original)
        expression = "(activation_target[0].offset[3:0] == 4'(%d))" % c['low_bits']
        point = points[c['raw_index']]
        require(point['native_id'] == c['native_id'] and point['vector'] == '1'
                and point['expression'] == expression, 'native/raw mapping differs')
        require(bit(row,c['raw_index']) == bit(prior,c['raw_index']) == '0',
                'target already covered in old687 or actual gap81')
        events = []
        for start in range(16-c['phase'],1040,16):
            if start < 16 or start+15 >= 1040:
                continue
            mapped = [dict(byte=b,context=(start+b-16)&3,native_offset=4+((start+b-16)>>2),
                           word=((start+b-16)>>2)//32) for b in range(16)]
            first = {ctx:next(x['word'] for x in mapped if x['context'] == ctx) for ctx in range(4)}
            mask = sum(1<<x['byte'] for x in mapped if x['word'] != first[x['context']])
            if mask:
                events.append(dict(range_offset=start,remaining_mask=mask,
                                   saved_target0_offset=mapped[0]['native_offset']))
        require(len(events) == 7 and events[0] == dict(range_offset=c['range_offset'],
                remaining_mask=c['pending_mask'],saved_target0_offset=c['native_offset']),
                'first boundary witness differs')
        require(all(e['remaining_mask'] == c['pending_mask'] and
                    e['saved_target0_offset'] & 15 == c['low_bits'] for e in events),
                'later word boundary phase differs')
        c.update(target=dict(scope=SCOPE,metric='cond',checksum=row['checksum'],
            raw_index=c['raw_index'],native_id=c['native_id'],vector='1',expression=expression),
            events=events,baseline_hit=False,gap81_single_vdb_hit=False)
        commands.append(c)
    for path in [OLD_PLAN,OLD_PLAN.parent/'plan.sha256.json',BUILD,BASELINE/'status.json',
                 BASELINE/'combined-bits.json',OLD_PLAN.parent/'combined-bits.json',
                 ROOT/'apps/common/qbs_abi.h',Path(__file__),Path(inventory.__file__),Path(bitmaps.__file__)]:
        source_pins[str(path)] = sha(path)
    return dict(status='STATIC_PREDICTION_NOT_RTL_PASS',commands=commands,source_hashes=source_pins,
        image=plan['image'],simv=plan['simv'],design_vdb=plan['design_vdb'],
        custom_word='0x06b5045b',vl=1,m=4,n=1,k_blocks=1,weight_profile='Q5_K',
        activation_profile='Q8_K',activation_layout='M4_INTERLEAVED',
        active_outputs=8,custom_commands=2,measured_gain=None,simulations_started=False,
        data_scope='known native directed fixture, not captured model data',
        limits=['Boundary remmask assumes no older pending bank interference.',
                'Only raw408/404 predicted; later native offsets step by32, not4.',
                'GAP81 bitmap check is not aggregate admission or current-checker revalidation.'])
