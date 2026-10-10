"""Frozen-source post-reset address padding proof; no native/application approval."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.'
RANK = OUT / 'toggle-outside-prepared-union770-static-agent-20261007-01.json'
RANK_SHA = 'c6dd804cbee8e8d872c6058da0defb8e1c0facd1ca816caf8326e6b12105f036'
BASE = OUT / 'mfpu-restart-word-boundary-offline-admitted-770-agent-20261007-01'
BASE_SHA = '7f8cbc5061a61c776d008590617c8727a07ead3c87dfb762139626166d2ba80a'
SOURCES = {
    'hardware/src/vlsu/addrgen.sv': 'abbdabe6a9d13cc81ad27ffa38f0149ec9c8f9f3b0383bf142b7d9987da5d2ac',
    'hardware/src/vlsu/vstu.sv': '139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2',
    'hardware/include/ara_pkg.sv': '49a4fd9879cad35c2c77241bd5114fb8d02ab520e833335fd916122854830971',
    'hardware/deps/axi/src/axi_pkg.sv': '244bd5cb3c5bc58d786f2ed2f5eeefd910c4fe03a175f4a2888c6a2ea1c430dc',
    'hardware/deps/common_cells/src/fifo_v3.sv': '861ea44cbd3129731b77977da36fb0dac1a1350d7df664a1b4310423e7d272bc',
    'hardware/tb/ara_tb.sv': 'c6416eabbc9a77c49ffbaec4643dcafdc1a31e758a35f1418cf084d63049f3e8',
    'hardware/src/ara.sv': 'ab7af0adead3fbc3a78cba5029ab8fb3fe3066b6f954085dff27971343be1eac',
    'hardware/src/ara_soc.sv': '41268269246a564bec870bab1a45bdb260786ffa95d2f50cb912cc61792d3e62',
    'hardware/src/vlsu/vlsu.sv': '9e620fb98efe420ff01ff9919461565b3c65a53bc518dc2f6cdb5f8241cf3ba2',
    'hardware/deps/cva6/core/include/build_config_pkg.sv': 'f8da8e2736ed10549187d06c2bd58f4d562ad3967ec62b3def290e0fc29e2f1b',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv': '0fbfd7729bce2cc7994686d27ff0adab053c816a958231556c335a09deb18ee3',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_contract(texts):
    # Exact frozen bytes also close extra whole-struct/field writers and signed casts.
    require(set(texts) == set(SOURCES), 'Incomplete source closure')
    for rel, sha in SOURCES.items():
        require(hashlib.sha256(texts[rel].encode()).hexdigest() == sha, 'Frozen source changed: ' + rel)
    a = texts['hardware/src/vlsu/addrgen.sv']
    v = texts['hardware/src/vlsu/vstu.sv']
    f = texts['hardware/deps/common_cells/src/fifo_v3.sv']
    blocks = re.findall(r"axi_addrgen_queue\s*=\s*'\{(.*?)\};", a, re.S)
    writers = []
    for block in blocks:
        values = dict(re.findall(r'\b(addr|vaddr)\s*:\s*([^,\n]+)', block))
        require(set(values) == {'addr', 'vaddr'}, 'Incomplete whole-record writer')
        writers.append({k: val.strip() for k, val in values.items()})
    require(writers == [dict(addr="'0", vaddr="'0"), dict(addr='paddr', vaddr='axi_addrgen_q.addr'),
                        dict(addr='paddr', vaddr='axi_addrgen_q.addr'),
                        dict(addr='idx_final_paddr', vaddr='idx_final_vaddr_q'),
                        dict(addr='paddr', vaddr="'0")], 'New or widened address writer')
    for fragment in ("axi_addrgen_queue      = '0;", 'axi_addr_t                        idx_final_vaddr_d, idx_final_vaddr_q;',
                     'idx_final_vaddr_d = pe_req_q.scalar_op + idx_vaddr;',
                     'automatic logic [CVA6Cfg.PLEN-1:0] paddr;',
                     'automatic logic [CVA6Cfg.PLEN-1:0] idx_final_paddr;'):
        require(fragment in a, 'Address producer width/default changed')
    require("b_meta_in               = '0;" in v and v.count('b_meta_in.vaddr = axi_addrgen_req_i.vaddr;') == 1,
            'Metadata producer/default changed')
    for fragment in ('mem_n           = mem_q;', 'mem_n[write_pointer_q] = data_i;',
                     "mem_q <= {FifoDepth{dtype'('0)}};", 'mem_q <= mem_n;'):
        require(fragment in f, 'FIFO reset/hold/write changed')
    return dict(AxiAddrWidth=64, PLEN=56, largest_addr_width=128, signed=False,
                addrgen_whole_record_writers=writers, indexed_addition_destination_width=64,
                induction=['reset: all FIFO rows zero', 'default producer zero',
                           'unsigned56/64 RHS zero-extends to128', 'hold preserves all rows',
                           'push replaces exactly one row with proven producer',
                           'clock-gated update copies proven mem_n; pop/flush change pointers only'],
                initial_X_waived=False, interface_excluded=False)


def names():
    return {
        PREFIX + 'i_addrgen': {'axi_addrgen_queue.addr', 'axi_addrgen_queue.vaddr'},
        PREFIX + 'i_addrgen.i_addrgen_req_queue': {f'mem_{q}[{i}].{field}' for q in ('n', 'q')
                                                  for i in range(4) for field in ('addr', 'vaddr')},
        PREFIX + 'i_vstu': {'b_meta_in.vaddr'},
        PREFIX + 'i_vstu.i_store_b_metadata': {f'mem_{q}[{i}].vaddr' for q in ('n', 'q') for i in range(16)},
    }


def duplicates(text, targets):
    scope = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
        elif line.startswith('MODULE:'):
            # Module-wide exclusions require explicit human review, never silently ignore.
            require(not any(k in line for k in ('addrgen', 'vstu', 'fifo_v3')), 'Relevant module-wide old EL')
            scope = None
        elif scope in targets and line.startswith('Toggle '):
            m = re.fullmatch(r'Toggle(?:\s+(?:0to1|1to0))?\s+([\w.]+(?:\[\d+\]\.[\w.]+)?)\s*(?:\[(\d+)(?::(\d+))?\])?(?:\s+"[^"]+")?', line)
            require(m is not None, 'Unknown existing EL in target scope')
            name, left, right = m.groups()
            if name in targets[scope]:
                require(left is not None and max(int(left), int(right or left)) < 64, 'Old EL overlaps high padding')


def evidence():
    pins = {}
    def bound(p, sha):
        require(digest(p) == sha, 'Input drift: ' + str(p)); pins[str(p)] = sha
        return p.read_text()
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    base = json.loads(bound(BASE / 'admission-manifest.json', BASE_SHA))
    book = json.loads(bound(book_path, base['input_pins'][str(book_path)]))
    texts = {}
    for rel, sha in SOURCES.items():
        require(book.get(str(ROOT / rel)) == sha, 'Source not in frozen build')
        texts[rel] = bound(ROOT / rel, sha)
    contract = source_contract(texts)
    rank = json.loads(bound(RANK, RANK_SHA))
    require(rank['population'] == 770 and rank['formal_manifest_sha256'] == BASE_SHA, 'Wrong population')
    for p, sha in rank['pins'].items():
        require(digest(p) == sha, 'Ranking provenance drift: ' + p)
        pins[p] = sha
    targets = names(); candidates = []
    for scope, fields in targets.items():
        rows = [s for s in rank['scopes'] if s['scope'] == scope]
        require(len(rows) == 1, 'Missing/ambiguous compiled scope')
        row = rows[0]
        for name in sorted(fields):
            nodes = [o for o in row['objects'] if o['name'] == name]
            require(len(nodes) == 1, 'Missing/duplicate shape target')
            node = nodes[0]
            require(node['kind'] == 'vectornode' and node['portnode'] == '0' and
                    node['left'] == '127' and node['right'] == '0' and node['excluded'] == '0', 'Not internal128 vector')
            offset = node['serialized_offset']
            require(set(range(offset + 128, offset + 256)) <= set(node['missing_coordinates']), 'Padding position observed hit')
            candidates.append(dict(scope=scope, name=name, checksum=row['checksum'],
                                   selected_left=127, selected_right=64, shape=node))
    old_files = sorted(set((ROOT / 'verification/coverage/waivers').rglob('*.el')) | set(OUT.rglob('*.el')))
    reviewed = []
    for p in old_files:
        text = p.read_text(); duplicates(text, targets)
        reviewed.append(dict(path=str(p), sha256=hashlib.sha256(text.encode()).hexdigest()))
    require(len(candidates) == 51, 'Not exact51')
    for p, sha in pins.items():
        require(digest(p) == sha, 'End-of-read drift')
    return dict(schema='VLSU_ADDRESS_PADDING770_SOURCE_PROOF_V1', status='STATIC_NOT_NATIVE_NOT_APPLIED',
                baseline=770, pins=pins, source_contract=contract, candidates=candidates,
                bits=3264, directions=6528, retained_bits_per_target=list(range(64)),
                old_EL_inventory=reviewed, old_EL_overlap_count=0,
                protected_interfaces=['axi_addrgen_req_o/i', 'FIFO data_i/o', 'b_meta_head'],
                population_application=False, official_denominator_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evidence()
    require(not args.output.exists(), 'Fresh proof output required')
    result['pins'][str(Path(__file__).resolve())] = digest(__file__)
    result['pins'][str(Path(__file__).with_name('test_prove_vlsu_address_padding770.py'))] = digest(Path(__file__).with_name('test_prove_vlsu_address_padding770.py'))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(digest(args.output))
