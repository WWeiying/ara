"""Reuse measured native1264 declarations for eight source/evidence-reviewed FP16 scopes."""
import argparse
import json
from pathlib import Path

import c910_srt_datapath_native_v4 as measured
from closure_point_inventory import read_xml

base = measured.base
life, require = base.life, base.require
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT / 'fp16-c910-additional8-source-evidence742-agent-20261007-01.json'
REVIEW_SHA = '3eb5732cebd7dc3bed24c0bec2da09728b1f608cc192163c2284b4623e550cd2'
REFERENCE = life.OUT / 'c910-srt-native1264-recovery-agent-20261007-01'
REFERENCE_SHA = '5fa9180cf70f658fbf355e7510a8d9c99af0240f6be22084139791f47fddbf38'
SCRIPT = Path(__file__).resolve()


def compiled_contract(review):
    db = life.IMAGE.with_suffix('.vdb') / 'snps/coverage/db'
    design = read_xml(db / 'design/verilog.design.xml')
    nodes = {i.get('id'): (i, m) for m in design.findall('srcdef') for i in m.findall('srcinst')}
    def path(key):
        i, _ = nodes[key]
        return (path(i.get('pid')) + '.' if i.get('pid') in nodes else '') + i.get('name')
    hierarchy = {path(k): (k, m) for k, (_, m) in nodes.items()}
    files = {f.get('id'): f.get('name') for f in read_xml(db / 'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    shape = read_xml(db / 'shape/tgl.verilog.shape.xml')
    bindings = []
    for i in review['instances']:
        require(i['scope'] in hierarchy, 'Missing compiled FP16 source scope')
        instance_id, module = hierarchy[i['scope']]
        require(module.get('name') == 'ct_vfdsu_srt_radix16_with_sqrt' and
                module.get('chksum') == i['design_module_checksum'], 'Compiled module checksum differs')
        source = files[module.find('srclocmult').get('file_id')]
        require(source == str(life.ROOT / 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_srt_radix16_with_sqrt.v'),
                'Compiled source location differs')
        defs = [d for d in shape.iter('tgldef') if d.get('chksum') == i['toggle_checksum']]
        require(len(defs) == 1, 'Compiled Toggle shape ambiguous')
        shapes = {n.get('name'): n for n in defs[0].find('tglshape')}
        for s in i['signals']:
            n = shapes[s['name']]
            require(n.tag == 'vectornode' and n.get('portnode') == '0' and
                    (int(n.get('left')), int(n.get('right')), int(n.get('line_num'))) ==
                    (s['left'], s['right'], s['declline']), 'Compiled target declaration differs')
        require(len(shapes) == 210 and len(i['signals']) == 158 and len(i['protected']) == 52,
                'Exact protected shape differs')
        bindings.append(dict(scope=i['scope'], compiled_instance_id=instance_id, source=source,
                             module_checksum=module.get('chksum'), toggle_checksum=i['toggle_checksum']))
    return bindings


def candidate(review, origin, text):
    require(review['status'] == 'FP16_C910_ADDITIONAL8_SOURCE_AND_OBSERVED_RTZ_DIV_PASS_NATIVE_PENDING',
            'Unqualified FP16 source/evidence')
    require(review['actual_evidence']['observed_halfwords'] == 64 and
            review['actual_evidence']['skipped_unknown'] == 0, 'Incomplete FP16 oracle')
    instances = review['instances']
    expected = {(lane, slot) for lane in range(4) for slot in (2, 3)}
    require(len(instances) == 8 and {(i['physical_lane'], i['simd_subslot']) for i in instances} == expected,
            'Not exact eight additional FP16 scopes')
    mapping = {}
    for old in origin['instances']:
        require(old['simd_subslot'] in (0, 1), 'Reference scope role differs')
        found = [i for i in instances if i['physical_lane'] == old['physical_lane'] and
                 i['simd_subslot'] == old['simd_subslot'] + 2]
        require(len(found) == 1, 'Ambiguous scope remap')
        new = found[0]
        require(new['signals'] == old['signals'] and new['protected'] == old['protected'] and
                new['design_module_checksum'] == old['design_module_checksum'] and
                new['toggle_checksum'] == old['toggle_checksum'], 'Signal/protection/signature drift')
        suffix = '.gen_num_lanes[%d].active_lane' % old['simd_subslot']
        require(new['scope'] == old['scope'].replace(suffix, '.gen_num_lanes[%d].active_lane' % new['simd_subslot']),
                'Unexpected hierarchy remap')
        mapping[old['scope']] = new['scope']
    measured.parse_el(text, origin)
    lines = []
    for line in text.splitlines():
        if line.startswith('INSTANCE: '):
            scope = line[len('INSTANCE: '):]
            require(scope in mapping, 'Extra reference instance')
            line = 'INSTANCE: ' + mapping[scope]
        lines.append(line)
    text = '\n'.join(lines) + '\n'
    measured.parse_el(text, dict(instances=instances))
    return text


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    review = life.read_bound(REVIEW, REVIEW_SHA); life.check(review['pins'])
    bindings = compiled_contract(review)
    result = life.read_bound(REFERENCE / 'capture-result.json', REFERENCE_SHA); life.check(result['pins'])
    origin = json.loads((REFERENCE / 'config.json').read_bytes())
    text = candidate(review, origin, (REFERENCE / 'first.el').read_text())
    pins = life.merge_pins(review['pins'], result['pins'])
    pins = life.merge_pins(pins, {str(REVIEW): REVIEW_SHA,
                                str(REFERENCE / 'capture-result.json'): REFERENCE_SHA})
    for p in (SCRIPT, SCRIPT.with_suffix('.tcl'), HERE / 'test_capture_c910_fp16_additional8.py',
              HERE / 'c910_srt_datapath_native_v3.tcl', Path(measured.__file__).resolve()):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    sourceinfo = life.IMAGE.with_suffix('.vdb') / 'snps/coverage/db/auxiliary/verilog.sourceinfo.xml'
    pins = life.merge_pins(pins, {str(sourceinfo): life.digest(sourceinfo)})
    base.tools.revalidate(origin['identity'])
    vdb = life.OUT / 'repaired-aligned-600-20260930-01/results/c0279-extra-rvv-vfdiv-46c98dbd428e/tests/rvv_vfdiv/work/code.vdb'
    dirs = list((vdb / 'snps/coverage/db/testdata').iterdir())
    require(len(dirs) == 1, 'Ambiguous admitted FP16 sample')
    out.mkdir()
    with (out / 'candidate.el').open('x') as stream: stream.write(text)
    values = dict(fma_design=str(life.IMAGE) + '.vdb', fma_vdb=str(vdb),
                  fma_test=str(vdb.with_suffix('') / dirs[0].name), fma_python='/usr/bin/python3',
                  fma_helper=str(SCRIPT), c910_fma_tcl=str(HERE / 'fma_datapath_native.tcl'))
    require(all(v and not any(c in v for c in '{}\\\r\n') for v in values.values()), 'Unsafe Tcl value')
    lines = ['set %s {%s}\n' % pair for pair in values.items()] + ['set fma_instances {}\n']
    for index, i in enumerate(review['instances']):
        labels = ' '.join('%s[%d:%d]' % (s['name'], s['left'], s['right']) for s in i['signals'])
        lines.append('lappend fma_instances [list {%s} {%s} {%s} %d]\n' %
                     (i['scope'], labels, ' '.join(i['protected']), index))
    with (out / 'selection.tcl').open('x') as stream: stream.write(''.join(lines))
    pins = life.merge_pins(pins, {str(out / name): life.digest(out / name) for name in ('candidate.el', 'selection.tcl')})
    life.check(pins)
    c = dict(schema='C910_SRT_NATIVE1264_PREPARED_V1', output=str(out), pins=pins,
             identity=origin['identity'], instances=review['instances'], timeout_seconds=900,
             input_VDB_count=1, objects=1264, logical_bits=77472, population_application=False,
             automatic_retry=False, protected_local_objects=416, source_evidence_seal=REVIEW_SHA,
             compiled_source_bindings=bindings,
             source_evidence_limit=review['scope_limit'], candidate_is_not_native_qualification=True)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins), native='PENDING')))


# Existing strict terminal/inventory/EL parser and foreground lifecycle, unchanged.
base.SCRIPT = SCRIPT
base.TCL = SCRIPT.with_suffix('.tcl')
base.TEST = HERE / 'test_capture_c910_fp16_additional8.py'
base.verify = measured.prior.original_verify

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'inspect', 'el', 'inventory'))
    p.add_argument('--output', required=True, type=Path); p.add_argument('--seal'); p.add_argument('--file')
    p.add_argument('--stage'); p.add_argument('--index', type=int)
    a = p.parse_args(); out = a.output.absolute()
    if a.mode == 'prepare': prepare(out)
    elif a.mode == 'el':
        require(a.file in ('first.el', 'second.el'), 'Invalid native EL filename')
        print(json.dumps(dict(objects=len(measured.parse_el((out / a.file).read_text(),
                                                           json.loads((out / 'config.json').read_bytes()))))))
    elif a.mode == 'inventory':
        c = json.loads((out / 'config.json').read_bytes())
        print(json.dumps(dict(rows=len(base.inventory(out, c, a.stage, a.index)))))
    else:
        require(a.seal, 'Exact config seal required')
        if a.mode == 'check':
            c = life.read_bound(out / 'config.json', a.seal); life.check(c['pins']); print('PREPARED_PINS_PASS')
        elif a.mode == 'run': base.run(out, a.seal)
        else: base.verify(out, a.seal)
