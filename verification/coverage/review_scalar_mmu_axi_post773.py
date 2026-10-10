"""Static exact raw773 OR qualified ITLB/VMACC, no simulation or exclusions."""
import argparse
import json
from pathlib import Path
import targeted_toggle_evidence_v2 as t
import rank_ordinary_rvv_toggle766 as cache_source

ROOT, OUT = cache_source.ROOT, cache_source.OUT
BASE = OUT / 'sv39-fault-alternating-offline-admitted-773-agent-20261007-01'
BASE_SHA = '65710f130e698571f9e17800e57361b0baa2a9d407a02287409797de64f64060'
QUALIFIED = [OUT / 'itlb-asid-exec-bulk-offline-qualified-773-agent-20261007-01/qualification.json',
             OUT / 'vmacc-C-fifo-qualified-parent-20261007-01/qualification.json']


def collect():
    pins = {}
    def bound(p, sha=None):
        value = t.digest(p)
        t.require(sha is None or sha == value, 'Input pin differs: ' + str(p))
        pins[str(p)] = value
        return json.loads(p.read_bytes())
    manifest = bound(BASE / 'admission-manifest.json', BASE_SHA)
    cache = bound(cache_source.CACHE, cache_source.CACHE_SHA)
    ledger_path = BASE / 'combined-inputs.txt'
    ledger = ledger_path.read_text().splitlines()
    pins[str(ledger_path)] = t.digest(ledger_path)
    t.require(pins[str(ledger_path)] == manifest['output_pins'][str(ledger_path)] and
              len(ledger) == len(set(ledger)) == 774 and manifest['coverage_admitted'], 'Formal773 exact ledger')
    old = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    t.require(t.digest(old) == cache['input_pins'][str(old)] and ledger[:742] == old.read_text().splitlines(), 'Exact cached741 prefix')
    pins[str(old)] = cache['input_pins'][str(old)]
    scopes = [s for s in cache['instances'] if s.startswith('ara_tb.dut.i_ara_soc.i_system.') and
              ('.i_ariane.ex_stage_i.lsu_i' in s or '.i_ariane.csr_regfile_i' in s
               or '.i_ariane.ex_stage_i.csr_buffer_i' in s or '.i_ariane_axi_dwc' in s
               or '.i_cache_subsystem.i_adapter' in s)]
    union = {s: {k: cache['instances'][s][k] for k in ('width', 'checksum', 'bits')} for s in scopes}
    samples = []
    for vdb in ledger[742:]:
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(files) == 1, 'Unique admitted sample')
        samples.append((files[0], manifest['input_pins'][str(files[0])]))
    overlays = []
    for qp in QUALIFIED:
        q = bound(qp)
        paths = [Path(p) for p in q['input_pins'] if p.endswith('tgl.verilog.data.xml') and
                 ('itlb-asid-exec-bulk-old-image-773' in p or 'vmacc-C-fifo-vcs-parent' in p)]
        t.require(len(paths) == 1 and ('PASS' in q['status'] or 'QUALIFIED' in q['status']), 'Unique qualified actual overlay')
        samples.append((paths[0], q['input_pins'][str(paths[0])]))
        overlays.append(dict(qualification=str(qp), sha256=pins[str(qp)], toggle=str(paths[0])))
    t.require(len(samples) == 34 and len({str(p) for p, _ in samples}) == 34, 'Exact32 suffix plus two overlays')
    for index, (p, sha) in enumerate(samples):
        t.require(t.digest(p) == sha, 'Bound Toggle input drift')
        rows, read_sha = t.rows(p, scopes)
        t.require(read_sha == sha, 'Read drift')
        pins[str(p)] = sha
        union = t.union(union, rows)
        if index % 10 == 0: print('STATIC_SUFFIX', index + 1, flush=True)
    db = Path(ledger[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml', db / 'shape/tgl.verilog.shape.xml']
    for p in paths:
        authority = manifest['input_pins'].get(str(p), cache['input_pins'].get(str(p)))
        t.require(authority and t.digest(p) == authority, 'Compiled identity authority')
        pins[str(p)] = authority
    design, info, shape = map(t.xml, paths)
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def fullname(key):
        n, _ = nodes[key]
        return (fullname(n.get('pid')) + '.' if n.get('pid') in nodes else '') + n.get('name')
    modules = {fullname(k): m for k, (_, m) in nodes.items()}
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    ranking = []
    for scope in scopes:
        row = union[scope]
        t.require(checks[scope] == row['checksum'], 'Compiled/sample checksum')
        matches = [d for d in shape.findall('tgldef') if d.get('chksum') == row['checksum'] and
                   d.get('name', '').split(' (')[0] == modules[scope].get('name', '').split(' (')[0]]
        if len(matches) != 1:
            ranking.append(dict(scope=scope, missing=row['width'] - bin(int(row['bits'], 16)).count('1'),
                                mapping='HOLD_AMBIGUOUS', objects=[]))
            continue
        offset = 0
        objects = []
        binary = format(int(row['bits'], 16), '0%db' % row['width'])
        for n in matches[0].find('tglshape'):
            if n.tag == 'arrays': continue
            t.require(n.tag in ('node', 'vectornode'), 'Unknown native shape')
            width = 1 if n.tag == 'node' else abs(int(n.get('left')) - int(n.get('right'))) + 1
            zeros = [offset + k for k, value in enumerate(binary[offset:offset + 2 * width]) if value == '0']
            if zeros:
                objects.append(dict(kind=n.tag, **n.attrib, logical_width=width, serialized_offset=offset,
                                    missing=len(zeros), zeros=zeros))
            offset += 2 * width
        t.require(offset == row['width'], 'Complete exact serialization')
        ranking.append(dict(scope=scope, module=modules[scope].get('name'), checksum=row['checksum'],
                            missing=row['width'] - bin(int(row['bits'], 16)).count('1'),
                            mapping='EXACT_CHECKSUM_MODULE_FAMILY_NOT_PARAMETER_WAIVER',
                            objects=sorted(objects, key=lambda b: -b['missing'])))
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = bound(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    for rel in ('core/cva6_mmu/cva6_mmu.sv', 'core/cva6_mmu/cva6_ptw.sv', 'core/cva6_mmu/cva6_tlb.sv',
                'core/cva6_mmu/cva6_shared_tlb.sv', 'core/load_unit.sv', 'core/store_unit.sv',
                'core/include/build_config_pkg.sv', 'core/include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        p = ROOT / 'hardware/deps/cva6' / rel
        t.require(t.digest(p) == book[str(p)], 'Frozen producer source drift')
        pins[str(p)] = book[str(p)]
    pins[str(Path(__file__).resolve())] = t.digest(__file__)
    for p, sha in pins.items(): t.require(t.digest(p) == sha, 'End-of-read drift')
    return dict(status='STATIC_RAW773_PLUS_TWO_QUALIFIED_OVERLAYS_NOT_FORMAL775', scopes=sorted(ranking, key=lambda x: -x['missing']),
                overlay_qualifications=overlays, samples=34, pins=pins, union=union,
                arrays_not_mapped=True, coordinates='Paired serialized positions; not native direction IDs or official denominator',
                EDA_launched=False, waivers_proposed=False, official_percentage=None)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    t.require(args.output.absolute().parent == OUT and not args.output.exists(), 'Fresh verification-only output')
    result = collect()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('STATIC_POST773_SEAL', t.digest(args.output))
