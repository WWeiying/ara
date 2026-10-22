"""Narrow read-wdata source/typed audit; existing read108 ownership, no new EL."""
import argparse
import json
from pathlib import Path
import re

import review_requester_read_payload767 as old
import qualify_requester_read108_native as native

life, need, ROOT, OUT = old.life, old.require, old.ROOT, old.OUT
CONFIG = OUT / 'native-full775-cached-parent-20261007-01/config.json'
CONFIG_SHA = '9ebd932ebdc0dfba10f12b4d6d5ddd988be7d2af067650eab91fb4f653b8286f'
BASE = OUT / 'vmacc-offline-admitted775-parent-20261007-01'
BASE_SHA = '59d67f7d5088baefaa498eda1d8e0f607e0eaf87945cc79a5f83607f8d679a13'
CAPTURE = OUT / 'requester-read108-native767-agent-20261007-01'


def source_guard(source, package, lane, vrf):
    result = old.source_contract(source, package)
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', package, flags=re.S)
    need(re.search(r'ELEN\s*=\s*64\s*;', clean) and
         'typedef logic [ELEN-1:0] elen_t;' in clean, 'Actual unsigned64 wdata type')
    need('elen_t wdata;' in source and 'payload_t [NrMasters-1:0]' in source,
         'Exact internal payload declaration')
    for anchor in ('operand_payload[MulFPUC:AluA]', 'operand_payload[SlideAddrGenA:MaskB]',
                   '.data_o ({vrf_addr_o[bank], vrf_wen_o[bank], vrf_wdata_o[bank], vrf_be_o[bank],'):
        need(anchor in source, 'Frozen read/write arbitration consumer')
    need('.vrf_wdata_o' in lane and '.wdata_i        (vrf_wdata' in lane and
         '.we_i   (wen_i[bank]' in vrf and '.wdata_i(wdata_i[bank]' in vrf,
         'Physical write consumer retains wen and write data')
    result.update(references=[dict(line=i, text=line.strip()) for i,line in enumerate(source.splitlines(),1)
                             if re.search(r'\boperand_payload\b', line)],
                  wdata_type='unsigned logic [63:0]',
                  consumer='Read slots0..4 HP,5..8 LP; arbiters also select dynamic write slots9..13. '
                           'VRF write data/ports are NOT constant and remain outside this subset.',
                  no_hold='Combinational full default each evaluation; no wdata register/hold/reset writer. '
                          'Only settled normal/reset evaluation is proven; no initial-X exclusion.')
    return result


def subset(scope, record, shape):
    targets, protected = old.compiled(scope, record, shape)
    chosen = [t for t in targets if t['field'] == 'wdata']
    protected += [t for t in targets if t['field'] != 'wdata']
    need(len(chosen) == 9 and {t['queue'] for t in chosen} == set(range(9)) and
         len(protected) == 737, 'Exact9 internal fields, complete737 protected definitions')
    return chosen, protected


def evidence():
    pins = {}
    def read(path, seal=None):
        digest = life.digest(path)
        need(seal is None or digest == seal, 'Bound input drift: '+str(path))
        pins[str(path)] = digest
        return json.loads(path.read_bytes())
    c = read(CONFIG, CONFIG_SHA)
    manifest = read(BASE/'admission-manifest.json', BASE_SHA)
    book = read(old.BOOK, c['pins'][str(old.BOOK)])
    sources = [old.REQUESTER, old.PACKAGE, ROOT/'hardware/src/lane/lane.sv',
               ROOT/'hardware/src/lane/vector_regfile.sv']
    for path in sources:
        need(life.digest(path) == book[str(path)], 'Actual frozen source binding')
        pins[str(path)] = book[str(path)]
    proof = source_guard(*(p.read_text() for p in sources))
    rank = read(old.RANK, old.RANK_SHA)
    ledger_path = BASE/'combined-inputs.txt'
    need(life.digest(ledger_path) == manifest['output_pins'][str(ledger_path)], '775 ledger SHA')
    pins[str(ledger_path)] = life.digest(ledger_path)
    ledger = ledger_path.read_text().splitlines()
    need(ledger == c['input_ledger'] and len(ledger) == len(set(ledger)) == 776, 'Exact775 population')
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/'design/verilog.design.xml', db/'shape/tgl.verilog.info.xml', db/'shape/tgl.verilog.shape.xml']
    for path in paths:
        need(life.digest(path) == c['pins'][str(path)] == rank['pins'][str(path)], 'Actual compiled shape identity')
        pins[str(path)] = c['pins'][str(path)]
    scopes = ['ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_requester'%i for i in range(4)]
    checks, definitions = old.shared.toggle.definitions(*(old.shared.toggle.xml(p) for p in paths), scopes)
    shape = old.shared.toggle.xml(paths[-1]); targets=[]; protections={}
    for scope in scopes:
        row = next(r for r in rank['scopes'] if r['scope'] == scope)
        need(checks[scope] == row['checksum'] == '553408029', 'Requester Toggle checksum')
        selected, other = subset(scope, row, shape)
        for node in selected:
            need(node['file'] == node['aux_file'] and node['line_num'] == '271' and
                 node['aux_line_num'] == '280' and node['type'] == '1', 'Compiled internal declaration role')
            node['design_module_checksum'] = definitions[scope]['module']['chksum']
        targets += selected; protections[scope] = other
    receipt = read(CAPTURE/'capture-result.json', c['pins'][str(CAPTURE/'capture-result.json')])
    need(receipt['status'] == 'REQUESTER_READ_FIELDS108_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED' and
         receipt['all_five_stage_excluded_flags_checked'] and receipt['initial_reset_final_global_EL_empty'],
         'Existing scoped native qualification')
    nc = read(CAPTURE/'config.json', receipt['config_seal'])
    signatures = []
    for name in ('first.el','second.el'):
        path = CAPTURE/name; need(life.digest(path) == receipt['pins'][str(path)], 'Native EL pin')
        pins[str(path)] = life.digest(path); signatures.append(native.parse_el(path.read_text(), nc))
    need(signatures[0] == signatures[1], 'Existing exact semantic roundtrip')
    canonical = CONFIG.parent/'combined.el'
    need(life.digest(canonical) == c['pins'][str(canonical)], 'Frozen775 combined EL')
    pins[str(canonical)] = life.digest(canonical)
    # Use the sealed parser only on the four exact read108 scope blocks.
    blocks = re.split(r'(?m)(?=^CHECKSUM:)', canonical.read_text())
    relevant = ''.join(b for b in blocks if any('INSTANCE: '+scope+'\n' in b for scope in scopes))
    need(native.parse_el(relevant, nc) == signatures[0], 'Exact existing read108 ownership in full775')
    wanted={(t['scope'],t['name']) for t in targets}
    owned=[r for r in signatures[0] if (r[0],r[1]) in wanted]
    need(len(owned)==36, 'Exact36 native subset, no index/whole-array inference')
    # Frozen766 zero coordinate evidence plus every later formally admitted sample.
    for target in targets:
        row = next(r for r in rank['scopes'] if r['scope']==target['scope'])
        oldnode = next(o for o in row['objects'] if o['name']==target['name'])
        coords=list(range(target['serialized_offset'],target['serialized_offset']+128))
        need(oldnode['missing_coordinates']==coords, 'Exact766 zero positions')
        target['raw775_missing_coordinates']=coords
    for vdb in ledger[767:]:
        files=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(files)==1,'Exactly one admitted suffix')
        rows, sha=old.shared.toggle.rows(files[0],scopes)
        need(sha==manifest['input_pins'][str(files[0])], '775 suffix pin')
        pins[str(files[0])]=sha
        for target in targets:
            row=rows[target['scope']]
            need(row['checksum']==target['checksum'] and row['width']==11238 and
                 all(not(int(row['bits'],16)>>(row['width']-1-i)&1) for i in target['raw775_missing_coordinates']),
                 'Source constant observed hit / width mismatch')
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_review_requester_wdata775.py').resolve(),
                 Path(old.__file__).resolve(),Path(native.__file__).resolve()): pins[str(path)]=life.digest(path)
    life.check(pins)
    return dict(status='EXACT36_SOURCE_TYPED_ZERO_ALREADY_IN_FULL775_EL_NOT_NEW_APPROVAL',
                population=775,pins=pins,source_proof=proof,targets=targets,protected_by_scope=protections,
                native_signatures=owned,typed_objects=36,constant_bits=2304,raw_missing_directions=4608,
                unbound_HOLD=[],new_exclusion_directions=0,EDA_launched=False,EL_generated=False,
                official_percentage=None,initial_X_excluded=False,
                protection='Only wdata[63:0] of literal slots0..8. All other fields, write slots9..13, '
                           'ports/returned data/all arrays protected from expansion by this audit; existing '
                           'read108 be/wen ownership is retained unchanged, not revoked or newly approved.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();need(out.parent==OUT and not out.exists(),'Fresh independent static file')
    result=evidence();life.save(out,result)
    print(json.dumps(dict(status=result['status'],output=str(out),seal=life.digest(out),objects=36,new_directions=0)))
