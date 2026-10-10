"""Exact literal concat bits, closed historical EL inventory, frozen770 provenance."""
import argparse
import json
from pathlib import Path
import re
import prove_vlsu_address_padding770 as shared

ROOT, OUT, require, digest = shared.ROOT, shared.OUT, shared.require, shared.digest
STATIC = OUT/'c910-pack-literal-constant-bits-static770-agent-20261007-01.json'
STATIC_SHA = 'f4b2f879a78f5ccdefddda6541ac47580a4531e102979e1155863ec5fe20b0b8'
SOURCE = ROOT/'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_pack.v'
SOURCE_SHA = 'fe2cc8b2717ab39b627c67c4f9c831208216c8ac7f1c6e4b77670d114b56fc1a'
VARIABLE_WIDTHS = {'vfdsu_ex4_result_sign':1, 'vfdsu_ex4_qnan_sign':1,
                   'vfdsu_ex4_qnan_f':52, 'ex4_expnt_rst':13, 'ex4_frac_52':52}


def split_concat(text):
    depth = 0; start = 0; parts = []
    for pos,char in enumerate(text):
        if char == '{': depth += 1
        elif char == '}': depth -= 1
        require(depth >= 0, 'Unbalanced concat')
        if char == ',' and depth == 0: parts.append(text[start:pos]); start = pos+1
    require(depth == 0, 'Unbalanced concat')
    parts.append(text[start:]); return parts


def symbolic(expression):
    """MSB-first bits: integers0/1 for literals, None for dynamic bits. No SV eval."""
    expression = re.sub(r'\s+', '', expression)
    m = re.fullmatch(r"(\d+)'([bh])([0-9a-fA-F]+)", expression)
    if m:
        width = int(m[1]); value = int(m[3], 2 if m[2]=='b' else 16)
        require(0 < width <= 64 and value < 1<<width, 'Literal width/overflow')
        return [(value>>bit)&1 for bit in range(width-1,-1,-1)]
    m = re.fullmatch(r'\{(\d+)\{(.+)\}\}', expression)
    if m:
        child = symbolic(m[2]); count = int(m[1])
        require(0<count<=64 and all(bit is not None for bit in child) and len(child)*count<=64,
                'Only bounded literal replication')
        return child*count
    if expression.startswith('{') and expression.endswith('}'):
        parts = split_concat(expression[1:-1])
        require(len(parts)>1, 'Unknown concat')
        result = [bit for part in parts for bit in symbolic(part)]
        require(len(result)<=64, 'Widened concatenation'); return result
    m = re.fullmatch(r'(\w+)(?:\[(\d+):(\d+)\])?', expression)
    require(m is not None and m[1] in VARIABLE_WIDTHS, 'Unknown arithmetic/cast/dynamic producer')
    width = VARIABLE_WIDTHS[m[1]]
    if m[2] is not None:
        hi,lo = int(m[2]),int(m[3]); require(width>hi>=lo>=0, 'Dynamic slice bounds'); width=hi-lo+1
    return [None]*width


def semantics(text, reference):
    text = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
    for name,width in VARIABLE_WIDTHS.items():
        ranges = re.findall(r'\b(?:input|wire|reg)\s*(?:\[\s*(\d+)\s*:\s*(\d+)\s*\])?\s+'+name+r'\s*;', text)
        require(ranges and all((int(hi)-int(lo)+1 if hi else 1)==width for hi,lo in ranges), 'Dynamic source declaration changed')
    result = []
    for item in reference['signals']:
        name = item['name']
        require(len(re.findall(r'\bwire\s*\[63:0\]\s+'+name+r'\s*;',text))==1, 'Not internal wire64')
        writes = re.findall(r'\b'+name+r'(?:\[[^]]+\])?\s*(?:<=|=(?!=))',text)
        assignments = re.findall(r'\bassign\s+'+name+r'\[63:0\]\s*=\s*(.*?);',text,re.S)
        require(len(writes)==len(assignments)==1, 'Extra/procedural writer or partial assignment')
        actual,expected = symbolic(assignments[0]),symbolic(item['RHS'])
        require(len(actual)==64 and actual==expected, 'Literal value or dynamic partition changed')
        constants = {63-index:value for index,value in enumerate(actual) if value is not None}
        selected = {bit for hi,lo in item['selected_ranges'] for bit in range(lo,hi+1)}
        require(set(constants)==selected, 'Selected range crosses sign/payload/normal data')
        result.append(dict(name=name,constant_values={str(bit):value for bit,value in sorted(constants.items())},
                           selected_ranges=item['selected_ranges'],unconditional_single_writer=True))
    require(len(result)==19 and sum(len(x['constant_values']) for x in result)==1048, 'Exact19/1048 boundary')
    return result


def old_overlap(text, scopes, fields):
    scope = None
    for line in map(str.strip,text.splitlines()):
        if line.startswith('INSTANCE:'): scope=line.split(':',1)[1].strip()
        elif line.startswith('MODULE:'):
            require('ct_vfdsu_pack' not in line,'Historical whole-pack exclusion');scope=None
        elif scope in scopes and line.startswith('Toggle '):
            m=re.match(r'Toggle(?:\s+(?:0to1|1to0))?\s+(\w+)',line)
            require(m is not None,'Unknown target-scope Toggle grammar')
            require(m[1] not in fields,'Historical target field exclusion requires explicit overlap review')


def evidence(closed_inventory=None):
    pins={}
    def bound(path,sha):
        require(digest(path)==sha,'Input drift: '+str(path));pins[str(path)]=sha
        return path.read_bytes()
    static=json.loads(bound(STATIC,STATIC_SHA))
    base=json.loads(bound(shared.BASE/'admission-manifest.json',shared.BASE_SHA))
    book_path=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book=json.loads(bound(book_path,base['input_pins'][str(book_path)]))
    require(book.get(str(SOURCE))==SOURCE_SHA,'Source absent from actual frozen build')
    derived=semantics(bound(SOURCE,SOURCE_SHA).decode(),static)
    ledger=shared.BASE/'combined-inputs.txt';paths=bound(ledger,base['output_pins'][str(ledger)]).decode().splitlines()
    require(len(paths)==len(set(paths))==771,'Exact770 ordered ledger')
    rank=json.loads(bound(shared.RANK,shared.RANK_SHA))
    require(rank['population']==770 and rank['formal_manifest_sha256']==shared.BASE_SHA,'Ranking population identity')
    for path,sha in rank['pins'].items():bound(Path(path),sha)
    from targeted_toggle_evidence_v2 import xml
    from inventory_operand_debug import Design
    db=Path(paths[0])/'snps/coverage/db'
    shape_path=db/'shape/tgl.verilog.shape.xml';info_path=db/'shape/tgl.verilog.info.xml'
    files_path=db/'auxiliary/verilog.sourceinfo.xml';design_path=db/'design/verilog.design.xml'
    for path in (shape_path,info_path,files_path,design_path):bound(path,base['input_pins'][str(path)])
    shapes,info,files=xml(shape_path),xml(info_path),xml(files_path);design=Design(Path(paths[0]))
    require([n.get('name') for n in files.iter('fileinfo') if n.get('id')=='370']==[str(SOURCE)],'Actual compiled source370 owner')
    defs=[d for d in shapes.findall('tgldef') if d.get('name')=='ct_vfdsu_pack' and d.get('chksum')=='146603553']
    require(len(defs)==1,'Unique actual pack definition');nodes=list(defs[0].find('tglshape'))
    check={n.get('name'):n.get('chksum') for n in info.iter('instance_data')}
    rows=[s for s in rank['scopes'] if s['module']=='ct_vfdsu_pack' and '.i_system.' in s['scope']]
    require(sorted(s['scope'] for s in rows)==static['scopes'] and len(rows)==17,'Actual17 instance ownership')
    fields={s['name']:s for s in static['signals']};instances=[]
    for row in rows:
        scope=row['scope'];require(check[scope]=='146603553' and design.hierarchy[scope].get('chksum')=='3434235298','Actual checksums')
        signals=[]
        for name,item in fields.items():
            ns=[n for n in nodes if n.get('name')==name];require(len(ns)==1,'Unique typed target')
            n=ns[0];require(n.tag=='vectornode' and all(n.get(k)==v for k,v in dict(file='370',line_num=str(item['declaration_line']),left='63',right='0',type='3',portnode='0',excluded='0').items()),'Actual internal wire shape')
            data=next(o for o in row['objects'] if o['name']==name);offset=data['serialized_offset']
            bits=[b for hi,lo in item['selected_ranges'] for b in range(lo,hi+1)]
            require({offset+2*b+d for b in bits for d in range(2)}<=set(data['missing_coordinates']),'Literal raw position unexpectedly hit')
            signals.append(dict(name=name,bits=sorted(bits),shape=dict(n.attrib),selected_ranges=item['selected_ranges']))
        instances.append(dict(scope=scope,design_module_checksum='3434235298',toggle_checksum='146603553',signals=signals,
                              full_shape=[dict(n.attrib,tag=n.tag) for n in nodes]))
    # First prepare consumes this closed inventory. Later prepared/native requests
    # are NOT silently reclassified as historical application by a global rescan.
    history=[]
    if closed_inventory is None:
        inventory_paths=sorted(set(OUT.rglob('*.el'))|set((ROOT/'verification/coverage/waivers').rglob('*.el')))
    else:
        require(len({row['path'] for row in closed_inventory})==len(closed_inventory),'Duplicate historical inventory path')
        for row in closed_inventory:require(digest(row['path'])==row['sha256'],'Closed historical EL drift')
        inventory_paths=[Path(row['path']) for row in closed_inventory]
    for path in inventory_paths:
        text=path.read_text();old_overlap(text,set(static['scopes']),set(fields))
        history.append(dict(path=str(path),sha256=digest(path)))
    for path,sha in pins.items():require(digest(path)==sha,'End-of-read drift')
    for name in ('prove_c910_pack_literals770.py','test_prove_c910_pack_literals770.py'):
        path=Path(__file__).with_name(name);pins[str(path)]=digest(path)
    return dict(schema='C910_PACK_LITERAL770_SOURCE_PROOF_V1',status='STATIC_NOT_NATIVE_NOT_APPLIED',baseline=770,
                pins=pins,semantic_literal_proof=derived,instances=instances,objects=323,bits=17816,directions=35632,
                historical_EL_inventory=history,historical_EL_overlaps=0,
                inventory_policy='Closed input inventory; do not rerun broad scanner after preparing candidates. Consumers revalidate this exact list.',
                protected='All nonliteral bits including sign/NaN payload/normal exponent and fraction, dynamic muxes, ports, flags, selectors',
                pre_reset_rationale='Unconditional combinational literal assignments, no register/reset or unknown-value waiver',
                population_application=False,official_denominator_verified=False)


def replay(path,seal):
    require(digest(path)==seal,'Proof replay seal')
    prior=json.loads(Path(path).read_bytes())
    require(prior['schema']=='C910_PACK_LITERAL770_SOURCE_PROOF_V1','Wrong closed inventory owner')
    current=evidence(prior['historical_EL_inventory'])
    require(current==prior,'Closed source/shape/population/EL replay differs')
    return current


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'Fresh proof only');result=evidence()
    with a.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(digest(a.output))
