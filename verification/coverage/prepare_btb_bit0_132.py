"""Static BTB bit0 partial-Toggle plan; never launches EDA or grants approval."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import targeted_toggle_evidence_v2 as native

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.i_frontend.btb_gen.i_btb'
BASE = OUT / 'btb-ring-admitted779-parent-20261008-01/admission-manifest.json'
BASE_SHA = '299cc1cf1bd65f2f64f495c9f791c3a190ba5329e86344f035224678ccfbb9ca'
PRIOR = OUT / 'global777-compact-parent-20261007-03/qualification.json'
PRIOR_SHA = '1bfdf26a417c142c8a24238f011f42f88b58c3883f566952e26776b2d101bf50'
BOOK = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
CHECKSUM = '3392269442 1574888635'
NOTE = 'BTB accepted JumpR target bit0 cleared; initialized ASIC storage induction; partial bit0 only; native qualification pending.'
NAMES = {f'gen_asic_btb.btb_{q}[{r}][{s}].target_address'
         for q in ('d', 'q') for r in range(16) for s in range(2)} | {
             f'btb_prediction_o[{s}].target_address' for s in range(2)}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def compact(text):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S))


def source_proof(btb, frontend, branch, cfg, cva6):
    b, f, j, c, a = map(compact, (btb, frontend, branch, cfg, cva6))
    for token in ("FpgaEn:bit'(0)", "RVZCMT:bit'(0)", "VLEN:unsigned'(64)",
                  'localparamCVA6ConfigBTBEntries=32;', 'localparamCVA6ConfigCExtEn=1;'):
        require(token in c, 'Frozen configuration: ' + token)
    require("if(fu_data_i.operation==ariane_pkg::JALR)target_address[0]=1'b0;" in j,
            'JALR LSB clear missing')
    require('resolved_branch_o.target_address=(branch_comp_res_i)?target_address:next_pc;' in j and
            'next_pc=pc_i+((is_compressed_instr_i)?' in j, 'Aligned next-PC alternative')
    require(j.count('resolved_branch_o.is_mispredict=') == 4 and
            j.count('resolved_branch_o.cf_type=ariane_pkg::JumpR;') == 2 and
            'if(CVA6Cfg.RVZCMT){' not in j and 'if(CVA6Cfg.RVZCMT)begin' in j and
            'resolved_branch_o.cf_type=ariane_pkg::Branch;' in j,
            'Complete producer classification changed')
    require('assignbtb_update.valid=resolved_branch_i.valid&resolved_branch_i.is_mispredict&(resolved_branch_i.cf_type==ariane_pkg::JumpR);' in f and
            'assignbtb_update.target_address=resolved_branch_i.target_address;' in f,
            'Accepted JumpR gate/copy changed')
    require('.resolved_branch_i(resolved_branch)' in a and '.resolved_branch_o(resolved_branch)' in a,
            'Branch-unit/frontend wire forwarding')
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', btb, flags=re.S)
    writers = [tuple(compact(v) for v in row) for row in re.findall(
        r'\b(btb_[dq](?:\[[^\]]+\]|\.\w+)*)\s*(<=|=(?!=))\s*([^;]+);', clean)]
    require(writers == [('btb_d', '=', 'btb_q'),
        ('btb_d[update_pc][update_row_index].valid', '=', "1'b1"),
        ('btb_d[update_pc][update_row_index].target_address', '=', 'btb_update_i.target_address'),
        ('btb_q[i]', '<=', "'{default:0}"), ('btb_q[i][j].valid', '<=', "1'b0"),
        ('btb_q', '<=', 'btb_d')], 'Complete ASIC writers differ')
    for token in ('if(btb_update_i.valid&&!debug_mode_i)begin',
                  "if(!rst_ni)beginfor(inti=0;i<NR_ROWS;i++)btb_q[i]<='{default:0};",
                  'assignbtb_prediction_o[i]=btb_q[index][i];'):
        require(token in b, 'Reset/capture/output contract differs')
    return dict(writers=writers, induction='Only accepted mispredicted JumpR updates storage. RVZCMT is disabled; branch operations override cf_type to Branch; other operations do not assert mispredict. JALR target clears bit0; the alternate next_pc advances an aligned legal PC by 2/4. q resets zero, d holds/copies q or accepted target; flush only clears valid; prediction directly copies q.',
                boundary='Legal instruction execution and actual reset, not startup-X or forced internal state. All valid/reset/control and bits63:1 remain protected.')


def el_text():
    return '\n'.join(['CHECKSUM: "' + CHECKSUM + '"', 'INSTANCE: ' + SCOPE,
                      'ANNOTATION: "' + NOTE + '"'] + [
        f'Toggle {name} [0] "logic {name}[63:0]"' for name in sorted(NAMES)]) + '\n'


def records(text):
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    require(lines[:3] == el_text().splitlines()[:3], 'Exact scope/checksum/annotation')
    found = set()
    for line in lines[3:]:
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) \[0\] "logic (\S+)\[63:0\]"', line)
        require(m is not None and m[2] in NAMES and m[2] == m[3], 'Unknown/nonpartial native directive')
        for direction in [m[1]] if m[1] else ['0to1', '1to0']:
            key = (m[2], 0, direction)
            require(key not in found, 'Duplicate native direction')
            found.add(key)
    require(found == {(n, 0, d) for n in NAMES for d in ('0to1', '1to0')},
            'Incomplete native direction set')
    return found


def no_overlap(text):
    require(not re.search(r'^(MODULE|FILE):', text, re.M), 'Broad prior EL needs explicit review')
    scope, directives = None, []
    def finish():
        if scope and (scope == SCOPE or SCOPE.startswith(scope + '.')):
            require(directives, 'Existing whole ancestor/scope exclusion')
            for line in directives:
                m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+)(?: \[(\d+)(?::(\d+))?\])? "(?:logic|reg|wire|net) [^"]+"', line)
                if not line.startswith('Toggle '):
                    continue
                require(m is not None, 'Unreviewed ancestor Toggle directive')
                full = scope + '.' + m[2]
                if full in {SCOPE + '.' + n for n in NAMES}:
                    require(m[3] is not None and min(int(m[3]), int(m[4] or m[3])) > 0,
                            'Existing target bit0 exclusion')
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(('CHECKSUM:', 'INSTANCE:')):
            finish(); directives = []
            scope = line.split(':', 1)[1].strip() if line.startswith('INSTANCE:') else None
        elif line and not line.startswith(('ANNOTATION:', '//')):
            directives.append(line)
    finish()


def prepare(output):
    pins = {}
    def read(p, sha):
        p = Path(p)
        require(p.resolve(strict=True) == p and not p.is_symlink(), 'Aliased evidence')
        data = p.read_bytes()
        require(hashlib.sha256(data).hexdigest() == sha, 'Evidence hash differs: ' + str(p))
        require(str(p) not in pins or pins[str(p)] == sha, 'Conflicting evidence pin')
        pins[str(p)] = sha
        return data
    base = json.loads(read(BASE, BASE_SHA)); require(base['coverage_admitted'] is True, 'Not admitted779')
    gain_path = BASE.parent / 'btb-toggle-gain.json'
    gain = json.loads(read(gain_path, base['output_pins'][str(gain_path)]))
    inputs = BASE.parent / 'combined-inputs.txt'
    ledger = read(inputs, base['output_pins'][str(inputs)]).decode().splitlines()
    require(len(ledger) == len(set(ledger)) == 780, 'Exact779 unique input population')
    book = json.loads(read(BOOK, BOOK_SHA))
    rels = ['frontend/btb.sv', 'frontend/frontend.sv', 'branch_unit.sv',
            'include/cv64a6_imafdcv_sv39_config_pkg.sv', 'cva6.sv']
    texts = [read(ROOT/'hardware/deps/cva6/core'/r, book[str(ROOT/'hardware/deps/cva6/core'/r)]).decode() for r in rels]
    proof = source_proof(*texts)
    paths = {Path(k).name: Path(k) for k in base['input_pins'] if k.endswith(
        ('verilog.design.xml', 'tgl.verilog.info.xml', 'tgl.verilog.shape.xml'))}
    trees = []
    for n in ('verilog.design.xml', 'tgl.verilog.info.xml', 'tgl.verilog.shape.xml'):
        data = read(paths[n], base['input_pins'][str(paths[n])])
        trees.append(native.base.ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data))
    checks, definitions = native.definitions(*trees, [SCOPE])
    definition = definitions[SCOPE]
    require(checks[SCOPE] == '1574888635' and definition['module'] ==
        dict(id='-131', name='btb', type='module', chksum='3392269442'), 'Compiled identity differs')
    shape = native.base.ET.fromstring(definition['shape'])
    require('NR_ENTRIES=32,OFFSET=1,NR_ROWS=16,' in shape.get('param'), 'Compiled ASIC dimensions')
    nodes, offset, targets = [], 0, []
    bits = int(gain['after']['bits'], 16)
    require(gain['scope'] == SCOPE and gain['after']['width'] == 8992 and
            gain['after']['checksum'] == checks[SCOPE] and bits.bit_length() <= 8992, '779 Toggle identity')
    for item in shape.find('tglshape'):
        require(item.tag in ('node', 'vectornode') and item.get('excluded') == '0', 'Unreviewed shape node')
        width = 1 if item.tag == 'node' else abs(int(item.get('left')) - int(item.get('right'))) + 1
        row = dict(kind=item.tag, attrs=dict(item.attrib), offset=offset, width=width)
        nodes.append(row)
        if item.get('name') in NAMES:
            require(width == 64 and item.get('left') == '63' and item.get('right') == '0', 'Target type/bounds')
            require((bits >> (8992-offset-2)) & 3 == 0, 'Candidate serialized low pair hit')
            targets.append(dict(row, bit=0, directions=['0to1', '1to0'],
                                serialized_positions=[offset, offset+1], protected_bits=list(range(1,64))))
        offset += width * 2
    require(offset == 8992 and len(targets) == len(NAMES) == 66 and
            {n['attrs']['name'] for n in targets} == NAMES, 'Exact compiled target inventory')
    target_positions = {i for n in targets for i in n['serialized_positions']}
    zero_positions = {i for i in range(8992) if not (bits >> (8991-i)) & 1}
    require(len(zero_positions) == 148 and target_positions <= zero_positions,
            'Exact779 residual inventory')
    prior = json.loads(read(PRIOR, PRIOR_SHA))
    require(prior['status'] == 'FORMAL777_COMPACT_GLOBAL_FIVE_PHASE_VERIFIED', 'Prior EL authority')
    prior_path = PRIOR.parent / 'applied.el'
    no_overlap(read(prior_path, prior['output_pins'][str(prior_path)]).decode())
    candidate = el_text(); require(len(records(candidate)) == 132, 'Native adapter identity')
    for p in [Path(__file__).resolve(), Path(__file__).with_name('test_prepare_btb_bit0_132.py'),
              Path(native.__file__).resolve(), Path(native.base.__file__).resolve(),
              Path(__file__).with_name('capture_csr_reserved1193.py'),
              Path(__file__).with_name('capture_tlb_rvh0_726.py')]:
        read(p, digest(p))
    for p, sha in pins.items():
        require(digest(p) == sha, 'Phase-end drift')
    output = Path(output).absolute(); output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        with (output/name).open('x') as f:
            if isinstance(value, str): f.write(value)
            else: json.dump(value, f, indent=2); f.write('\n')
    save('candidate.el', candidate)
    save('proof.json', proof)
    save('inventory.json', dict(scope=SCOPE, module=definition['module'], parameters=shape.get('param'),
        targets=targets, all_nodes=nodes, target_serialized_count=132, protected_serialized_count=8860,
        all_residual_serialized_positions=sorted(zero_positions),
        protected_residual_serialized_positions=sorted(zero_positions-target_positions),
        raw_position_rule='MSB-first serialized offset i tests integer bit width-1-i; direction ordering remains uncalibrated.',
        all_valid_fields_protected=True, serialized_direction_order_calibrated=False,
        native_checksums_basis='Compiled module checksum plus Toggle checksum, existing partial-bit EL convention; actual BTB native export still required.'))
    save('existing-el-overlap.json', dict(prior_qualification=str(PRIOR), prior_seal=PRIOR_SHA,
        prior_EL=str(prior_path), overlap_count=0, no_duplicate_proposal=True))
    save('prepare-manifest.json', dict(status='STATIC_PREPARED_NOT_NATIVE_APPROVED', population=779,
        baseline_seal=BASE_SHA, input_pins=pins,
        output_pins={str(output/n):digest(output/n) for n in
                     ('candidate.el','proof.json','inventory.json','existing-el-overlap.json')},
        native_validation_required=['actual exact partial identity export', 'both directions complete',
            'all8860 protected serialized positions', 'save/reset/reload/final empty and rooted metrics'],
        EDA_run=False, coverage_admitted=False))
    return digest(output/'prepare-manifest.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(prepare(args.output))
