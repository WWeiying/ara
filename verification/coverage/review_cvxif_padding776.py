"""Prepared-only passive CVXIF padding audit; no EL, EDA or DUT gain claim."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as typed
from branch720_next_report_contract import native_inventory

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASE = OUT / 'vfirst-offline-admitted776-parent-20261007-01'
BASE_SHA = '85abeb09ddfc3c4ddbfc43eefa7c71d860932dd66af572edac0bd7030ce3c33c'
CONFIG = OUT / 'native-full775-cached-parent-20261007-01/config.json'
CONFIG_SHA = '9ebd932ebdc0dfba10f12b4d6d5ddd988be7d2af067650eab91fb4f653b8286f'
RANK = OUT / 'toggle-outside-prepared-union770-static-agent-20261007-01.json'
RANK_SHA = 'c6dd804cbee8e8d872c6058da0defb8e1c0facd1ca816caf8326e6b12105f036'
BOOK = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind'
SCOPES = (SCOPE, SCOPE + '.cvxif')
CHANNELS = ('ar', 'r', 'aw', 'w', 'b')
FILES = ('hardware/tb/ara_tb.sv', 'hardware/tb/ara_testharness.sv',
         'hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv',
         'hardware/deps/axi/include/axi/typedef.svh', 'hardware/deps/axi/src/axi_pkg.sv',
         'verification/uvm/ara_cvxif_dut_bind.sv', 'verification/uvm/ara_cvxif_if.sv')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def clean(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def source_contract(sources, params):
    """Derive channel sizes from actual compiled parameters and unsigned macros."""
    need(all(params[k] == v for k, v in dict(NrLanes='4', AxiDataWidth='128',
         AxiAddrWidth='64', AxiUserWidth='1', AxiIdWidth='5', AxiCoreIdWidth='4').items()),
         'Compiled AXI geometry differs')
    soc = clean(sources['hardware/src/ara_soc.sv'])
    for anchor in ('localparam NrAXIMasters = 1;',
                   'AxiIdWidth - $clog2(NrAXIMasters)', 'AxiSocIdWidth - 1',
                   'typedef logic [AxiCoreIdWidth-1:0] axi_core_id_t;',
                   '`AXI_TYPEDEF_ALL(ara_axi, axi_addr_t, axi_core_id_t, axi_data_t, axi_strb_t, axi_user_t)',
                   '.AxiIdWidth        (AxiCoreIdWidth'):
        need(anchor in soc, 'Unsigned producer/actual parameter anchor: ' + anchor)
    macro = clean(sources['hardware/deps/axi/include/axi/typedef.svh'])
    pkg = clean(sources['hardware/deps/axi/src/axi_pkg.sv'])
    widths = dict(addr_t=64, id_t=4, user_t=1, data_t=128, strb_t=16, logic=1)
    for left, right, name in re.findall(r'typedef\s+logic\s*\[(\d+):(\d+)\]\s+(\w+)\s*;', pkg):
        widths['axi_pkg::' + name] = abs(int(left) - int(right)) + 1
    required = dict(ar=['id','addr','len','size','burst','lock','cache','prot','qos','region','user'],
                    aw=['id','addr','len','size','burst','lock','cache','prot','qos','region','atop','user'],
                    w=['data','strb','last','user'], r=['id','data','resp','last','user'], b=['id','resp','user'])
    sizes = {}
    for ch in CHANNELS:
        matches = re.findall(r'`define AXI_DECL_' + ch.upper() + r'_CHAN_T\([^\n]+\)\s*\\\s*'
                             r'struct packed\s*\{(.*?)\}', macro, re.S)
        need(len(matches) == 1 and 'signed' not in matches[0], 'Unique unsigned packed channel')
        fields = re.findall(r'([\w:]+)\s+(\w+)\s*;', matches[0].replace('\\',''))
        need([n for _, n in fields] == required[ch] and all(t in widths for t, _ in fields),
             'Unknown/extra channel field')
        sizes[ch] = sum(widths[t] for t, _ in fields)
    need(sizes == dict(ar=98, aw=104, w=146, r=136, b=7), 'Derived sizes differ')
    bind = clean(sources['verification/uvm/ara_cvxif_dut_bind.sv'])
    interface = clean(sources['verification/uvm/ara_cvxif_if.sv'])
    for ch in CHANNELS:
        name = 'axi_' + ch + '_payload'
        cast = re.findall(r'\.' + name + r'_i\s*\(([^\n]+)\)', bind)
        need(cast == ["1024'(ara_axi_%s.%s)" % ('resp' if ch in ('r','b') else 'req', ch)],
             'Exact unsigned cast binding; no signed/arithmetic producer')
        need(re.findall(r'assign\s+cvxif\.' + name + r'\s*=\s*([^;]+);', bind) == [name+'_i'],
             'Unique mirror driver')
        need(len(re.findall(r'\bcvxif\.'+name+r'\b', bind)) == 1 and
             not re.search(r'\b'+name+r'\s*(?:\[[^\]]+\])?\s*(?:<=|=(?!=))', interface),
             'Extra payload writer')
        need(re.search(r'input\s+logic\s*\[1023:0\]\s*'+name+r'_i\s*[,;]', bind) and
             re.search(r'logic\s*\[1023:0\]\s*'+name+r'\s*;', interface), 'Exact unsigned observation declaration')
    return dict(channel_widths=sizes, extension='Unsigned packed AXI struct -> sized unsigned1024 cast -> sole mirror assign',
                reset_hold='Combinational padding is zero independently of low payload reset/hold/X; no initial-X waiver',
                scope_kind='Passive verification fields under product hierarchy, NOT DUT functional improvement')


def bind_scope(scope, definition, checksum, module_checksum):
    child = scope == SCOPES[1]
    need(scope in SCOPES, 'Foreign scope')
    need(definition.get('chksum') == checksum and definition.get('name') ==
         ('ara_cvxif_if' if child else 'ara_cvxif_dut_bind'), 'Compiled checksum/module mismatch')
    selected, protected, offset = [], [], 0
    names = {'axi_'+ch+'_payload'+('' if child else '_i'): ch for ch in CHANNELS}
    for node in definition.find('tglshape'):
        if node.tag == 'arrays':
            protected.append(dict(kind='arrays', xml=ET.tostring(node, encoding='unicode')))
            continue
        need(node.tag in ('node','vectornode'), 'Unknown compiled object')
        width = 1 if node.tag == 'node' else abs(int(node.get('left'))-int(node.get('right')))+1
        item = dict(scope=scope, kind=node.tag, **node.attrib, serialized_offset=offset)
        if node.get('name') in names:
            ch = names[node.get('name')]; line = (48 if child else 41) + CHANNELS.index(ch)
            need(node.tag == 'vectornode' and all(node.get(k) == v for k,v in dict(
                left='1023', right='0', type='1', portnode='0' if child else '2',
                file='607' if child else '610', line_num=str(line), excluded='0').items()),
                'Typed declaration/role/bounds mismatch')
            item.update(channel=ch, checksum=checksum, module_checksum=module_checksum)
            selected.append(item)
        else:
            protected.append(item)
        offset += 2*width
    need(len(selected) == 5 and len({x['name'] for x in selected}) == 5, 'Missing/duplicate payload')
    return selected, protected, offset


def existing_overlap(text, targets):
    """Exact old native directives only; no filesystem scan or guessed labels."""
    inventory, _ = native_inventory(text.encode('ascii'))
    overlap = set()
    for scope, checksum, _, directive in inventory:
        related = [t for t in targets if t['scope'] == scope or
                   (directive == 'WHOLE_SCOPE' and t['scope'].startswith(scope+'.'))]
        if not related:
            continue
        if directive == 'WHOLE_SCOPE':
            for t in related:
                overlap.update((t['scope'],t['name'],bit,d) for bit in t['bits'] for d in ('0to1','1to0'))
            continue
        if not directive.startswith('Toggle '):
            continue
        match = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+)(?: \[(\d+)(?::(\d+))?\])? "(logic|reg|net) ([^"]+)"',directive)
        need(match is not None, 'Unknown relevant native Toggle format')
        direction, name, hi, lo, kind, decl = match.groups()
        exact = [t for t in related if t['name'] == name]
        if not exact:
            continue
        need(len(exact) == 1, 'Ambiguous target identity'); t = exact[0]
        need(checksum == t['module_checksum']+' '+t['checksum'] and kind in ('logic','net') and
             decl == name+'[1023:0]', 'Native checksum/declaration identity mismatch')
        low, high = (0,1023) if hi is None else (int(lo or hi),int(hi))
        need(0 <= low <= high <= 1023, 'Native selector bounds')
        overlap.update((scope,name,b,d) for b in t['bits'] if low<=b<=high
                       for d in ((direction,) if direction else ('0to1','1to0')))
    return overlap


def evidence():
    pins = {}
    def read(path, expected=None, json_data=False):
        data = path.read_bytes(); sha = hashlib.sha256(data).hexdigest()
        need(expected is None or sha == expected, 'Input drift: '+str(path))
        need(str(path) not in pins or pins[str(path)] == sha, 'Conflicting pin')
        pins[str(path)] = sha
        return json.loads(data) if json_data else data
    c = read(CONFIG,CONFIG_SHA,True); m = read(BASE/'admission-manifest.json',BASE_SHA,True)
    book = read(BOOK,c['pins'][str(BOOK)],True)
    sources = {f:read(ROOT/f,book[str(ROOT/f)]).decode() for f in FILES}
    ledger = read(BASE/'combined-inputs.txt',m['output_pins'][str(BASE/'combined-inputs.txt')]).decode().splitlines()
    need(len(ledger)==len(set(ledger))==777 and ledger[:776]==c['input_ledger'], 'Exact776 population/775 prefix')
    rank = read(RANK,RANK_SHA,True)
    oldbase = OUT/'mfpu-restart-word-boundary-offline-admitted-770-agent-20261007-01/combined-inputs.txt'
    need(ledger[:771] == read(oldbase,rank['pins'][str(oldbase)]).decode().splitlines(), 'Exact raw770 cache prefix')
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml',
             db/'auxiliary/verilog.sourceinfo.xml']
    trees = [ET.fromstring(__import__('gzip').decompress(data) if data[:2]==b'\x1f\x8b' else data)
             for data in (read(p,c['pins'][str(p)]) for p in paths)]
    checks, defs = typed.definitions(*trees[:3],SCOPES)
    soc = [d for d in trees[2].findall('tgldef') if d.get('name')=='ara_soc']
    need(len(soc)==1,'Unique compiled SoC'); params=dict(x.split('=',1) for x in soc[0].get('param').split(','))
    proof = source_contract(sources,params)
    targets=[]; protected={}; raw={}
    for scope in SCOPES:
        definition=ET.fromstring(defs[scope]['shape'])
        chosen,other,width=bind_scope(scope,definition,checks[scope],defs[scope]['module']['chksum'])
        row=next(r for r in rank['scopes'] if r['scope']==scope)
        need(row['checksum']==checks[scope] and row['module_checksum']==defs[scope]['module']['chksum'], 'Raw/compiled identity')
        missing=set(i for obj in row['objects'] for i in obj['missing_coordinates'])
        for t in chosen:
            sourcefile=ROOT/FILES[-1 if scope==SCOPES[1] else -2]
            fi=[n for n in trees[3].iter('fileinfo') if n.get('id')==t['file']]
            need(len(fi)==1 and fi[0].get('name')==str(sourcefile),'Compiled source file identity')
            t['low_payload_width']=proof['channel_widths'][t['channel']]
            t['bits']=list(range(t['low_payload_width'],1024))
            t['raw_positions']=[t['serialized_offset']+2*b+d for b in t['bits'] for d in range(2)]
            need(set(t['raw_positions'])<=missing,'Padding observed hit in raw770')
            t['retained_low_range']=[t['low_payload_width']-1,0]
        targets+=chosen;protected[scope]=other;raw[scope]=dict(width=width,checksum=checks[scope])
    for vdb in ledger[771:]:
        data=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(data)==1,'One admitted suffix Toggle file')
        path=data[0];read(path,m['input_pins'][str(path)])
        rows,sha=typed.rows(path,SCOPES);need(sha==pins[str(path)],'Suffix read drift')
        for t in targets:
            row=rows[t['scope']];need((row['width'],row['checksum'])==(raw[t['scope']]['width'],t['checksum']), 'Suffix shape')
            need(all(not(int(row['bits'],16)>>(row['width']-1-i)&1) for i in t['raw_positions']), 'Padding observed hit776')
    canonical=CONFIG.parent/'combined.el'; text=read(canonical,c['pins'][str(canonical)]).decode('ascii')
    overlap=existing_overlap(text,targets)
    # Coordinate identity is bit/direction; serialization is not a native direction ID.
    expected={(t['scope'],t['name'],b,d) for t in targets for b in t['bits'] for d in ('0to1','1to0')}
    need(len(expected)==18516,'Exact ten-object padding capacity')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_review_cvxif_padding776.py').resolve(),
              Path(typed.__file__).resolve(),Path(__import__('branch720_next_report_contract').__file__).resolve()):read(p)
    for path,sha in pins.items():need(typed.digest(Path(path))==sha,'Final pin drift: '+path)
    return dict(schema='PASSIVE_CVXIF_PADDING776_STATIC_PREPARATION_V1',
        status='EXACT_TYPED_PADDING_OLD_NATIVE_EL_DIFFERENCE_PREPARED_ONLY',population=776,pins=pins,
        source_proof=proof,targets=targets,protected_by_scope=protected,compiled_geometry=params,
        old_EL_inventory=str(canonical),old_overlap_directions=len(overlap),
        old_overlap=sorted(overlap),new_candidate_directions=len(expected-overlap),
        logical_padding_bits=9258,objects=10,raw_missing_directions=18516,
        native_binding='Typed shape + exact existing-native inventory difference only. New range native binding is NOT qualified.',
        native_qualified=False,EL_generated=False,EDA_authorized=False,DUT_functional_gain=False,
        official_denominator_verified=False,official_percentage=None,
        protection='Both payload low ranges and every other scalar/vector/array, control/handshake/Assert/Group remain protected.',
        masku='Excluded from this audit; existing parent bit_enable_mask native qualification owned by Helmholtz.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();need(out.parent==OUT and not out.exists(),'Fresh static output only')
    result=evidence()
    with out.open('x') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps(dict(output=str(out),seal=typed.digest(out),status=result['status'],
                         new_candidate_directions=result['new_candidate_directions'],EDA_launched=False)))
