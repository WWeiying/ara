"""Offline source/compiled/EL review only; never creates an exclusion or runs EDA."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'toggle796-net-static-agent-20261008-01.json'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
REPORT = OUT / 'csr-rvh-debug796-readonly-agent-20261008-01.json'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i'
HREGS = ('hcounteren', 'hedeleg', 'hgeie', 'hideleg', 'htinst', 'htval', 'mtinst')
FIXED = {'xdebugver': ([28, 29, 30, 31], 4), 'nmip': ([3], 0),
         'stopcount': ([10], 0), 'stoptime': ([9], 0)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xml(path):
    data = path.read_bytes()
    return ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)


def target_conflict(row):
    if row['directive'].startswith('WHOLE_SCOPE'):
        return True
    match = re.match(r'^Toggle(?: (?:0to1|1to0))? (\S+)', row['directive'])
    assert match, 'Unknown Toggle directive'
    prefix = '' if row['scope'] == SCOPE else SCOPE[len(row['scope']) + 1:] + '.'
    return bool(re.match(re.escape(prefix) + r'(?:' + '|'.join(HREGS + ('dscratch0', 'dscratch1', 'dcsr')) +
                         r')(?:_[qd])?(?:\.|\[|$)', match[1]))


def collect():
    rank = json.loads(RANK.read_bytes())
    assert rank['population'] == 796
    pins = dict(rank['pins'])
    pins[str(RANK)] = digest(RANK)
    book = json.loads((BUILD / 'build-source-pins.json').read_bytes())
    rels = ('hardware/deps/cva6/core/csr_regfile.sv',
            'hardware/deps/cva6/core/include/riscv_pkg.sv',
            'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
            'hardware/deps/cva6/core/include/build_config_pkg.sv',
            'hardware/deps/cva6/core/cva6.sv', 'hardware/deps/cva6/core/decoder.sv',
            'hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv')
    texts = {}
    for rel in rels:
        path = ROOT / rel
        assert digest(path) == book[str(path)], 'Source drift: ' + rel
        pins[str(path)] = book[str(path)]
        texts[rel] = path.read_text()
    db = BUILD / 'sim/simv.vdb/snps/coverage/db'
    shape = xml(db / 'shape/tgl.verilog.shape.xml')
    definitions = [n for n in shape.iter('tgldef') if n.get('chksum') == '1176918775']
    assert len(definitions) == 1
    definition = definitions[0]
    sourceinfo = xml(db / 'auxiliary/verilog.sourceinfo.xml')
    files = {n.get('id'): n.get('name') for n in sourceinfo.iter('fileinfo')}
    assert files['401'] == str(ROOT / rels[2])
    assert files['428'] == str(ROOT / rels[0])
    assert 'CVA6Cfg=-1,' in definition.get('param')
    cfg = texts[rels[2]]
    assert 'localparam CVA6ConfigHExtEn = 0;' in cfg
    assert "RVH: bit'(CVA6ConfigHExtEn)" in cfg and "DebugEn: bit'(1)" in cfg
    assert 'cfg.RVH = CVA6Cfg.RVH;' in texts[rels[3]]
    assert 'cfg.DebugEn = CVA6Cfg.DebugEn;' in texts[rels[3]]
    soc = texts['hardware/src/ara_soc.sv']
    config_function = soc[soc.index('function automatic config_pkg::cva6_user_cfg_t'):soc.index('endfunction', soc.index('function automatic config_pkg::cva6_user_cfg_t'))]
    assert not re.search(r'cfg\.(RVH|DebugEn|XLEN|RVXHCLIC)\s*=', config_function)
    assert 'build_config_pkg::build_config(CVA6AraConfig_user)' in soc
    csr = texts[rels[0]]
    assert "dcsr_d.xdebugver = 4'h4;" in csr
    for field in ('nmip', 'stopcount', 'stoptime'):
        assert re.search(r'dcsr_d\.' + field + r'\s*=\s*1\x27b0;', csr)
    assert "dcsr_q       <= '{xdebugver: 4'h4, prv: riscv::PRIV_LVL_M, default: '0};" in csr
    objects = [r for r in rank['objects'] if r['scope'] == SCOPE and
               r['attributes']['name'].startswith(HREGS + ('dscratch', 'dcsr'))]
    nodes = {n.get('name'): n for n in definition.find('tglshape')}
    for row in objects:
        assert row['checksum'] == definition.get('chksum')
        assert row['expected_frozen_source_sha256'] == book[row['source_file']]
        for key, value in nodes[row['attributes']['name']].attrib.items():
            assert row['attributes'][key] == value
    # Audit the exact scope and every ancestor; observer aliases remain distinct.
    elpath = OUT / 'current-population796-alua137-ptw156-agent-20261008-01/combined.el'
    el_rows = []
    current, checksum = None, None
    for number, line in enumerate(elpath.read_text().splitlines(), 1):
        if line.startswith('CHECKSUM: '):
            checksum = line
        elif line.startswith('INSTANCE: '):
            current = line.split(': ', 1)[1]
        elif current and (current == SCOPE or SCOPE.startswith(current + '.')):
            if line.startswith('Toggle ') or line.startswith('WHOLE_SCOPE'):
                el_rows.append(dict(line=number, scope=current, checksum=checksum, directive=line))
    conflicts = [r for r in el_rows if target_conflict(r)]
    assert not conflicts, 'Target/packed parent/ancestor ownership requires HOLD'
    assert all(r['both_direction_EL_removed'] == r['single_direction_EL_HOLD'] == 0 for r in objects)
    const, held, reachable = [], [], []
    for row in objects:
        name = row['attributes']['name']
        item = dict(name=name, compiled_attributes=row['attributes'],
                    residual_unnamed_pair_slots=row['coordinates'],
                    residual_count=row['net_missing_serialized_positions'])
        if name.startswith('dcsr') and name.split('.', 1)[1] in FIXED:
            field = name.split('.', 1)[1]
            bits, value = FIXED[field]
            item.update(architectural_bits=bits, field_local_bits=list(range(len(bits))),
                        constant_field_value=value, physical_mask=hex(sum(1 << b for b in bits)),
                        rationale='Reset establishes value; default holds q; whole DCSR write immediately forces field; other partial writers never modify field; q captures d.')
            const.append(item)
        elif name.startswith(HREGS):
            item.update(physical_bits=list(range(64)), known_zero=False,
                        reason='RVH0 removes reset, capture, default hold, CSR and trap writers. q/d are uninitialized/undriven, not constant-zero storage. No zero extension or masked write proves disabled storage.')
            held.append(item)
        else:
            item.update(known_zero=False, waive=False,
                        reason='DebugEn1: preserve externally enabled debug capability; legal debug CSR write can change bits. SoC request tieoff is not a disabled-debug parameter.')
            reachable.append(item)
    assert len(const) == 8 and sum(r['residual_count'] for r in const) == 28
    assert len(held) == 14 and sum(r['residual_count'] for r in held) == 1792
    refs = {}
    for stem in HREGS + ('dscratch0', 'dscratch1', 'dcsr', 'debug_mode'):
        refs[stem] = [dict(line=i + 1, text=line.strip()) for i, line in enumerate(csr.splitlines())
                      if re.search(r'\b' + stem + r'_[qd]\b', line)]
    spans = [(1050, 1128), (1193, 1218), (1438, 1530), (1698, 1708),
             (2117, 2141), (2168, 2190), (2200, 2293), (2416, 2483),
             (2565, 2584), (2815, 2833), (2868, 2887), (2919, 2931), (2965, 2984)]
    lines = csr.splitlines()
    result = dict(status='FROZEN796_CSR_SOURCE_REVIEW_NOT_NATIVE_APPROVAL', population=796,
                  requested_rank_name='rank toggle796-net-static-agent-20261008-01.json',
                  actual_rank=str(RANK), scope=SCOPE, checksum='1176918775',
                  compiled_parameters=definition.get('param'),
                  composite_parameter_note='CVA6Cfg=-1 is an opaque composite encoding, not literal minus-one. File401 package, frozen forwarding and typed compiled widths establish XLEN64/RVH0/DebugEn1/RVXHCLIC0.',
                  const_physical_objects=const, disabled_uninitialized_HOLD=held,
                  debug_capability_preserved=reachable,
                  config=dict(XLEN=64, RVH=0, DebugEn=1, RVXHCLIC=0),
                  dedup=dict(target_or_ancestor_EL_conflicts=conflicts, already_EL_removed_slots=0,
                             new_const_residual_slots=28, physical_const_bits_q_plus_d=14,
                             rvfi_observers_not_internal_identity=True,
                             source_and_compiled_evidence_not_additive=True),
                  existing_observer_EL_not_added=[r for r in el_rows if '.csr.dcsr_' in r['directive'] or '.csr.dscratch' in r['directive']],
                  fixed_bit_proof_boundary='Valid reset followed by settled evaluation, all operating cycles including enabled debug writes/traps/returns. No time-zero X, delta transient, force, fault or native direction order claim.',
                  all_reference_inventory=refs,
                  full_reviewed_source_spans=[dict(first=a, last=b, text='\n'.join(lines[a-1:b])) for a, b in spans],
                  directed_cases=[
                      dict(name='debug-entry-prerequisite', plan='Parent-owned bounded debug entry through a real supported harness input. Current ara_system:185 ties debug_req_i to0; normal application cannot assert it. If current frozen harness has no entry route, keep capability/HOLD, do not force internal debug_mode or relabel constants.',
                           discriminators=['debug_req_i at cva6/decoder', 'decoder instruction_o.ex.valid/cause=DEBUG_REQUEST', 'CSR ex_i.valid/cause', 'debug_mode_d/q', 'set_debug_pc_o']),
                      dict(name='dscratch-two-register-zero-ones-zero', plan='In confirmed debug mode: for CSR0x7b2/0x7b3, csrrw -1 then csrrw0 with a readback after each write. Four writes cover both binary transitions on all64 bits in each q/d. Assert no CSR exception and observed retire/readback; no counter delay loop.',
                           discriminators=['csr_op_i', 'csr_addr_i', 'csr_wdata', 'csr_we', 'privilege_violation', 'dscratch0_q/d', 'dscratch1_q/d', 'csr_rdata_o']),
                      dict(name='dcsr-writable-fields-and-fixed-mask', plan='In debug mode, write bits27:18,17,16,15,14,13,12,11,5,4 using mask0x0ffff830 then write0; readback each. Deliberately also write ones to fixed fields28..31/10/9/3 and check xdebugver=4 and10/9/3=0. zero1/zero2 are writable in this RTL; v can be1 during debug although outside-debug override sets0. Set step only for a separate single-step case.',
                           discriminators=['csr_we', 'debug_mode_q', 'dcsr_q/d', 'csr_exception_o']),
                      dict(name='cause-and-step-bounded', plan='External request entry -> cause3; set step and valid dpc then DRET, retire exactly one simple instruction -> cause4; in a separate phase set ebreakm then DRET to one EBREAK -> cause1. Compare q/d and set_debug_pc_o; no long counter stimulus. Restore controls. S/U privilege/ebreak cases only if their residual fields are separately targeted.'),
                      dict(name='illegal-debug-and-H-CSR-controls', plan='Outside debug attempt CSR read/write0x7b0/0x7b2/0x7b3 and RVH0 accesses0x606/0x602/0x607/0x603/0x64a/0x643/0x34a. Bounded trap handler checks cause2 and next PC. Debug writes require privilege_violation1/csr_we0 and unchanged scratch; H access must report read/update_access_exception. This covers rejection control only, never H q/d bits.')],
                  EDA_started=False, RTL_changed=False, exclusions_generated=False,
                  whole_CSR_waiver=False, measured_gain=None, official_denominator=None,
                  parent_next_action='Review exact8 typed leaves/14 physical bits only. Any native admission/roundtrip/population application is separate; remaining debug needs supported entry, H storage needs nonzero-specific disabled-storage policy review.',
                  input_pins=pins)
    pins[str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    for path, expected in pins.items():
        assert digest(Path(path)) == expected, 'Evidence drift: ' + path
    return result


if __name__ == '__main__':
    result = collect()
    with REPORT.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(REPORT, digest(REPORT))
