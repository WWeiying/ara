"""Frozen-image parent MASKU zero alias; static evidence only, never creates EL."""
import argparse
import json
from pathlib import Path
import re

import review_masku_vl_constant770 as prior

ROOT, OUT = prior.ROOT, prior.OUT
SCOPE = prior.SCOPE.rsplit('.', 1)[0]
NAME = 'bit_enable_mask'
REPORT = OUT / 'masku-parent-bit-enable-frozen-static-agent-20261007-01.json'
SIM_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
SOURCE_REVIEW_SHA = '8b2496d8a38f297658cbc91187d0961c3bbfc048f29518af2c35c50de02c66a5'


def parent_contract(parent):
    source = prior.lexical.clean(parent)
    occurrences = list(re.finditer(r'\bbit_enable_mask\b', source))
    prior.require(len(occurrences) == 2, 'Exactly declaration and child output connection; no reader/override')
    prior.require(re.search(r'logic\s*\[NrLanes\*DataWidth-1:0\]\s+bit_enable_mask\s*;', source),
                  'Exact parent internal declaration')
    prior.require(re.search(r'\.bit_enable_mask_o\s*\(\s*bit_enable_mask\s*\)', source),
                  'Exact sole child output driver')
    prior.require(not prior.lexical.writes(parent, (NAME,)), 'No parent assignment driver')
    prior.require(re.search(r'DataWidth\s*=\s*\$bits\(elen_t\)', source), 'Frozen parent width')
    return dict(occurrence_lines=[source.count('\n', 0, m.start()) + 1 for m in occurrences],
                functional_readers=[], parent_assignment_drivers=[],
                sole_driver=prior.SCOPE + '.bit_enable_mask_o')


def validate_node(node):
    prior.require(node.tag == 'vectornode' and all(node.get(k) == v for k, v in dict(
        name=NAME, file='588', line_num='116', type='1', portnode='0', excluded='0',
        left='255', right='0').items()), 'Exact declaration-bound internal vector only')


def collect():
    pins = {}

    def pin(path, expected=None):
        actual = prior.digest(path)
        prior.require(expected is None or actual == expected, 'Frozen pin mismatch: ' + str(path))
        pins[str(path)] = actual
        return path

    book = json.loads(pin(prior.BOOK, prior.BOOK_SHA).read_bytes())
    pin(OUT / 'repaired-aligned-build-20260930-01/sim/simv', SIM_SHA)
    # Three dirty unrelated files are replaced with exact old-image bytes, not used as evidence.
    replacements = {}
    sources = {}
    for name, expected in book.items():
        path = Path(name)
        if path.suffix not in ('.sv', '.svh', '.v', '.vh'):
            continue
        if prior.digest(path) != expected:
            snapshot = OUT / 'old-image-source-evidence-20261006-01' / path.name
            pin(snapshot, expected)
            replacements[name] = str(snapshot)
            path = snapshot
        else:
            pin(path, expected)
        sources[name] = path.read_text()
    parent = sources[str(ROOT / 'hardware/src/masku/masku.sv')]
    child = sources[str(ROOT / 'hardware/src/masku/masku_operands.sv')]
    package = sources[str(ROOT / 'hardware/include/ara_pkg.sv')]
    source_proof = prior.source_contract(child, parent, package)
    alias = parent_contract(parent)
    references = {}
    for name, source in sources.items():
        clean = prior.lexical.clean(source)
        if re.search(r'\bbit_enable_mask(?:_o)?\b', clean):
            references[name] = [i for i, line in enumerate(clean.splitlines(), 1)
                                if re.search(r'\bbit_enable_mask(?:_o)?\b', line)]
    prior.require(set(references) == {str(ROOT / 'hardware/src/masku/masku.sv'),
                                     str(ROOT / 'hardware/src/masku/masku_operands.sv')},
                  'Unexpected compiled-source cross-hierarchy read/drive')
    old = json.loads(pin(prior.REPORT, SOURCE_REVIEW_SHA).read_bytes())
    audit = json.loads(pin(prior.AUDIT, prior.AUDIT_SHA).read_bytes())
    for path, expected in audit['pins'].items():
        pin(Path(path), expected)
    row = next(s for s in audit['scopes'] if s['scope'] == SCOPE)
    db = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    design = prior.typed.xml(pin(db / 'design/verilog.design.xml'))
    shape = prior.typed.xml(pin(db / 'shape/tgl.verilog.shape.xml'))
    prior.typed.xml(pin(db / 'shape/tgl.verilog.info.xml'))
    sourceinfo = prior.typed.xml(pin(db / 'auxiliary/verilog.sourceinfo.xml'))
    definitions = [d for d in shape.findall('tgldef')
                   if d.get('name') == 'masku' and d.get('chksum') == row['checksum']]
    prior.require(len(definitions) == 1, 'Unique compiled parent type')
    definition = definitions[0]
    params = dict(x.split('=', 1) for x in definition.get('param').split(','))
    prior.require(all(params[k] == v for k, v in dict(NrLanes='4', VLEN='1024', DataWidth='64').items()),
                  'Exact frozen compiled geometry')
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}

    def full(key):
        node, _ = nodes[key]
        parent_id = node.get('pid')
        return (full(parent_id) + '.' if parent_id in nodes else '') + node.get('name')

    hierarchy = {full(k): (n, m) for k, (n, m) in nodes.items()}
    prior.require(hierarchy[SCOPE][1].get('name') == 'masku' and
                  hierarchy[SCOPE][1].get('chksum') == row['module_checksum'], 'Exact parent instance')
    prior.require(hierarchy[prior.SCOPE][1].get('chksum') == old['candidates'][0]['module_checksum'],
                  'Exact child instance')
    file = next(n for n in sourceinfo.iter('fileinfo') if n.get('id') == '588')
    prior.require(file.get('name') == str(ROOT / 'hardware/src/masku/masku.sv'), 'Declaration source, not instantiation')
    fields = list(definition.find('tglshape'))
    target = [n for n in fields if n.get('name') == NAME]
    prior.require(len(target) == 1, 'Unique exact target')
    validate_node(target[0])
    raw = next(n for n in row['objects'] if n['name'] == NAME)
    prior.require(raw['logical_bits'] == 256 and raw['serialized_offset'] == 3422 and
                  raw['missing_slots'] == 512 and raw['missing_coordinates'] == list(range(3422, 3934)),
                  'Exact historical770 missing slots')
    protected = [dict(kind=n.tag, **n.attrib) for n in fields if n is not target[0]]
    children = [dict(scope=s, module=m.get('name'), module_checksum=m.get('chksum'),
                     all_fields_protected=True) for s, (n, m) in hierarchy.items() if s.startswith(SCOPE + '.')]
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_review_masku_parent_bit_enable_static.py'),
                 Path(prior.__file__), Path(prior.lexical.__file__), Path(prior.typed.__file__)):
        pin(path)
    for path, expected in pins.items():
        prior.require(prior.digest(Path(path)) == expected, 'Final pin drift')
    return dict(status='FROZEN_MASKU_PARENT_ALIAS_SOURCE_PROVEN_NATIVE_PENDING',
        scope=SCOPE, target=dict(kind=target[0].tag, **target[0].attrib),
        module_checksum=row['module_checksum'], toggle_checksum=row['checksum'],
        compiled_parameters=params, sourceinfo=dict(file.attrib), source_proof=source_proof,
        parent_alias_proof=alias, compiled_source_references=references,
        old_image_source_replacements=replacements, source_files_checked=len(sources),
        reachability='All 256 bits are zero after settled combinational evaluation for every legal input. '
                     'No legal software/mask/VL/vstart/operation/reset/abort sequence sets them; no functional readers. '
                     'No claim about pre-settle delta/X or force.',
        exact_candidate_bits=256, historical770_missing_slots=512,
        historical770_missing_coordinates=raw['missing_coordinates'],
        local_inventory_count=len(fields), protected_count=len(protected),
        protected_array_count=sum(n['kind'] == 'arrays' for n in protected),
        protected_inventory=protected, protected_children=children,
        protected_policy='Every other parent object and every child object/port protected, including bit_enable_mask_o, '
                         'alu_result_compressed_seq, actual masks/data/queues/control/reset/flags/handshake. '
                         'Prior two child-internal candidates remain separate; no expansion here.',
        native_display_identity=None, native_qualification=False,
        coordinate_semantics='512 historical serialized pair slots, NOT a DVE denominator or current incremental gain.',
        official_percentage=None, EL_created=False, EDA_launched=False, RTL_modified=False,
        waivers_applied=False, pins=pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    result = collect()
    if args.verify:
        prior.require(json.loads(REPORT.read_bytes()) == result, 'Static replay differs')
    else:
        prior.require(not REPORT.exists(), 'Fresh independent output only')
        with REPORT.open('x') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(dict(path=str(REPORT), seal=prior.digest(REPORT), status=result['status'],
                         protected=result['protected_count'], pins=len(result['pins']))))
