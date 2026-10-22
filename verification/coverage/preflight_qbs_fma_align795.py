"""One two-K-block alignment fixture: host/compile/Spike only, no EDA."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
import preflight_valu_restart783 as mature
import review_qbs_fma_padding795 as proof

ROOT, OUT, need = proof.ROOT, proof.OUT, proof.need
APP = ROOT / 'verification/tests/qbs_fma_align795.c'
WITNESS = OUT / 'qbs-fma-padding795-source-witness-agent-20261008-02.json'
WITNESS_SHA = 'c92eefa33755a221921cc6a2688e2463d8f6d49be966faa06ac4055bf5b1f6b8'
HEADER = 2 | 1 << 4 | 1 << 8 | 1 << 12 | 1 << 16 | 1 << 20 | 1 << 25
GUARD, CHECKS = 0x5a39c781, 6705
SNAP_SIZE = 4224
STAGES = ('qf_scale_mul', 'qf_dot_fma', 'qf_min_mul', 'qf_min_fma')
STAGE_WORDS = (0x10100053, 0x18200043, 0x101181d3, 0x00418043)


def blocks(phase):
    need(type(phase) is int and phase in (0, 1), 'Only the two approved orders')
    order = (0, 1) if phase == 0 else (1, 0)
    weights, activation = [], []
    for row in range(2):
        for index in order:
            quant = bytearray(128)
            for offset in (0, 32, 64, 96):
                quant[offset + row] = 0x11
            weights.append(struct.pack('<HH', (0x3d55, 0x0401)[index], 0) +
                           bytes([1]*4+[0]*4+[1]*4) + quant)
    for index in order:
        activation.append(struct.pack('<I', (0x3f555555, 0x00800001)[index]) +
                          bytes([1, 255]+[0]*30)*8 + bytes(32))
    return weights, activation


def payload(phase):
    weights, activation = blocks(phase)
    body = struct.pack('<I', GUARD)*4 + b''.join(weights + activation)
    result = body + struct.pack('<I', GUARD)*26
    need(len(result) == 1280, 'Full explicit payload/guard bytes')
    return result


def header():
    array = lambda values: '{'+','.join(str(v) for v in values)+'}'
    rows = []
    for phase in range(2):
        weights, activation = blocks(phase)
        ws = ['{'+str(int.from_bytes(w[:2], 'little'))+',0,'+
              array(w[4:16])+','+array(w[16:])+'}' for w in weights]
        acts = ['{'+('0x1.aaaaaap-1f' if int.from_bytes(a[:4], 'little') == 0x3f555555 else
                    '0x1.000002p-126f')+','+array([b if b < 128 else b-256 for b in a[4:260]])+','+
                array([0]*16)+'}' for a in activation]
        rows.append('{'+array([GUARD]*4)+','+'{'+','.join(ws)+'},'+
                    '{'+','.join(acts)+'},'+array([GUARD]*4)+','+array([GUARD]*22)+'}')
    return ('#define QF_HEADER UINT64_C('+hex(HEADER)+')\n#define QF_GUARD '+hex(GUARD)+'u\n'
      '#define QF_CHECKS '+str(CHECKS)+'u\n'
      'static const struct __attribute__((aligned(128))) qf_input {\n'
      ' uint32_t before[4]; qbs_block_q4_k_t weights[4]; qbs_block_q8_k_t activation[2];\n'
      ' uint32_t after[4],padding[22];\n} qf_inputs[2] = {'+','.join(rows)+'};\n'
      '_Static_assert(sizeof(qf_inputs[0])==1280,"explicit input bytes");\n'
      '_Static_assert(offsetof(struct qf_input,activation)==592,"activation address");\n'
      '#ifndef QF_HOST\nstatic const uint32_t qf_output_gold[2]={0x410e3000,0xc10e3000};\n'
      'static const uint64_t qf_csr_gold[6]={32,16,0,0,3,3};\n'
      'static const unsigned char qf_input_gold[2][1280]={'+
      ','.join(array(payload(p)) for p in range(2))+'};\n#endif\n')


def block_gold():
    result = []
    for phase in range(2):
        order = (0, 1) if phase == 0 else (1, 0)
        for row in range(2):
            acc = 0
            for block, index in enumerate(order):
                scale, _ = proof.gold.round32(proof.gold.value((0x3d55, 0x0401)[index], 10, 15) *
                                              proof.gold.value((0x3f555555, 0x00800001)[index]))
                before = acc
                acc, _ = proof.gold.round32(proof.gold.value(scale) * 8 + proof.gold.value(acc & 0x7fffffff))
                if row: acc |= 1 << 31
                result.append(dict(phase=phase, row=row, block=block, scale=scale,
                                   dot=(-8 if row else 8), before=before, after=acc))
    return result


def host_gate(text):
    expected = []
    gold = block_gold()
    for phase in range(2):
        for r in sorted(gold, key=lambda r:(r['phase'], r['block'], r['row'])):
            if r['phase'] == phase:
                expected.append('B {phase} {row} {block} {dot} 0 {before:08x} {after:08x}'.format(**r))
        expected.append('F %d 3 2' % phase)
        expected += ['Q %d %d %08x' % (phase, i, (0x410e3000, 0xc10e3000)[i] if i < 2 else 0)
                     for i in range(32)]
    need(text.splitlines() == expected, 'Full independent host block/flags/output oracle')


def metadata(elf):
    with elf.open('rb') as stream:
        e = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
        segments = [(s['p_vaddr'], s.data()) for s in e.iter_segments() if s['p_type'] == 'PT_LOAD']
    def read(address, size):
        matches = [data[address-base:address-base+size] for base, data in segments
                   if base <= address and address+size <= base+len(data)]
        need(len(matches) == 1, 'File-backed ELF bytes')
        return matches[0]
    need(read(symbols['qf_inputs'], 2560) == payload(0)+payload(1), 'All actual ELF packed input/guard bytes')
    need(symbols['tohost'] == 0x80001000, 'Frozen harness tohost address')
    return symbols, read


def spike_gate(commits, symbols):
    registers, memory, stage, snapshots, owners = [0]*32, {}, 0, set(), 0
    vector = {}
    records = block_gold()
    for commit in commits:
        need(commit.pc != symbols['trap_fail'], 'No unexpected trap')
        if commit.pc in [symbols[s] for s in STAGES]:
            entry, kind = divmod(stage, 4)
            need(entry < 8 and commit.pc == symbols[STAGES[kind]], 'Exact eight ordered four-op scalar reference blocks')
            r = records[entry]
            need(commit.instruction == STAGE_WORDS[kind], 'Exact scalar FP instruction operands and RNE')
            expect = (r['scale'], r['after'], 0, r['after'])[kind]
            target = (0, 0, 3, 0)[kind]  # ft0=f0, ft3=f3
            need(commit.fpr_writes == {target: 0xffffffff00000000 | expect},
                 'Independent exact nan-boxed scalar FP result at owned site')
            stage += 1
        if commit.pc == symbols['qf_reference_load']:
            need(owners < 2 and (commit.vector_sew, commit.vector_lmul, commit.vector_vl,
                 commit.vector_vstart, commit.vector_vtype) == (32, 'm1', 32, 0, 16), 'Exact fallback destination shape')
            need(set(vector) == set(range(32)), 'Complete initialized before VRF')
            expected = {reg:sum((0x6a000000+reg) << (32*i) for i in range(32)) for reg in range(32)}
            need(vector == expected, 'Full independent pre-command VRF')
            need(set(commit.vector_writes) == {8} and commit.vector_writes[8] ==
                 0xc10e3000410e3000, 'Only v8 full128-byte golden destination update')
            owners += 1
        word = commit.instruction
        if word & 127 == 39 and commit.vector_sew is not None:
            base = registers[word >> 15 & 31]
            reg = word >> 7 & 31
            owner, offset = divmod(base-symbols['qf_snap'], SNAP_SIZE)
            need(0 <= owner < 4 and offset == 16+reg*128 and (owner, reg) not in snapshots,
                 'Exact unique snapshot owner/address')
            values = [(0x410e3000, 0xc10e3000)[i] if i < 2 else 0 for i in range(32)] if owner % 2 and reg == 8 else [0x6a000000+reg]*32
            data = b''.join(v.to_bytes(4,'little') for v in values)
            need(commit.memory_accesses == tuple((base+i,b) for i,b in enumerate(data)), 'Full exact128 byte snapshot store')
            memory.update({base+i:b for i,b in enumerate(data)})
            snapshots.add((owner, reg))
        elif word & 127 in (3, 35) and word & 3 == 3:
            kind, size = mature.shared.spike_trace._scalar_memory_access(word)
            if kind == 'write':
                for address, value in commit.memory_accesses:
                    memory.update({address+i:b for i,b in enumerate(value.to_bytes(size,'little'))})
        elif word & 3 != 3:
            access = mature.rv64c.decode(word)
            if access and access['kind'] == 'write':
                for address, value in commit.memory_accesses:
                    memory.update({address+i:b for i,b in enumerate(value.to_bytes(access['size'],'little'))})
        registers = [commit.gpr_writes.get(i,v) for i,v in enumerate(registers)]
        registers[0] = 0
        vector.update(commit.vector_writes)
    need(stage == 32 and owners == 2 and len(snapshots) == 128, 'All FP sites, owners, full snapshots')
    def read(name, offset=0, size=4):
        base = symbols[name]+offset
        need(all(base+i in memory for i in range(size)), 'Missing defined terminal/memory byte')
        return int.from_bytes(bytes(memory[base+i] for i in range(size)), 'little')
    need([read('qf_result'), read('qf_result',4), read('num_failed'), read('tohost',size=8)] ==
         [CHECKS,0,0,1], 'Exact checks/no failure/success terminal')
    for phase in range(2):
        need([read('qf_csr',(phase*6+i)*8,8) for i in range(6)] == [32,16,0,0,3,3], 'Full recorded CSR gold')
        for side in range(2):
            for offset in (0, 4112):
                need([read('qf_snap',(phase*2+side)*SNAP_SIZE+offset+4*i) for i in range(4)] == [GUARD]*4,
                     'All snapshot guards preserved')
    return dict(retired=len(commits), software_checks=CHECKS, scalar_FP_owned_sites=32,
                full_VRF_snapshot_bytes=16384, snapshot_registers=128, custom_native_owners_executed=0,
                software_reference_owners=2, CSR_words=12, defined_output_bytes_skipped=0)


def binding796(witness):
    base = OUT/'akv-canonical-alias-offline-admitted796-parent-20261008-01'
    prior = OUT/'scalar-div-subnormal-offline-admitted795-parent-20261008-01'
    manifest = json.loads((base/'admission-manifest.json').read_text())
    old = json.loads((prior/'admission-manifest.json').read_text())
    need(proof.gold.digest(prior/'admission-manifest.json') == witness['baseline_seal'] and
         manifest['coverage_admitted'] is True and manifest['baseline'] == str(prior) and
         manifest['baseline_seal'] == witness['baseline_seal'], 'Formal796 exact795 genealogy')
    pins = {}
    for directory, record in ((base,manifest), (prior,old)):
        for name in ('admission-manifest.json', 'combined-inputs.txt', 'combined-toggle-bits.json'):
            path = directory/name
            expected = proof.gold.digest(path) if name == 'admission-manifest.json' else record['output_pins'][str(path)]
            need(proof.gold.digest(path) == expected, 'Formal sealed output')
            pins[str(path)] = expected
    ledger = (base/'combined-inputs.txt').read_text().splitlines()
    need(len(ledger) == len(set(ledger)) == 797 and ledger[:-1] ==
         (prior/'combined-inputs.txt').read_text().splitlines(), 'Formal796 one exact append')
    new = json.loads((base/'combined-toggle-bits.json').read_text())[witness['scope']]
    oldrow = json.loads((prior/'combined-toggle-bits.json').read_text())[witness['scope']]
    need(new['checksum'] == oldrow['checksum'] == witness['checksum'] and
         new['width'] == oldrow['width'] and int(oldrow['bits'],16) & ~int(new['bits'],16) == 0,
         'Compiled identity and no lost795 hits')
    bitmap = int(new['bits'],16)
    remaining = lambda positions:[p for p in positions if not bitmap >> (new['width']-1-p) & 1]
    const = remaining(witness['constant_serialized_positions'])
    need(len(const) == 56, 'Full796 padding zero audit')
    fields = [dict(name=r['name'], prior_count=r['count'], missing796_positions=
                   remaining(r['missing_positions_with_one_witness'])) for r in witness['mutable_missing_witnesses']]
    return dict(population=796, manifest=str(base/'admission-manifest.json'),
                manifest_sha256=pins[str(base/'admission-manifest.json')], pins=pins,
                fields=fields, remaining_host_one_witness_positions=sum(len(r['missing796_positions']) for r in fields),
                native_gain_prediction=False, direction_order_inferred=False)


def prepare(out):
    need(out.parent == OUT and not out.exists(), 'Fresh isolated output')
    need(proof.gold.digest(WITNESS) == WITNESS_SHA, 'Frozen source witness')
    witness = json.loads(WITNESS.read_text())
    for path, sha in witness['pins'].items():
        need(proof.gold.digest(Path(path)) == sha, 'Frozen source pin changed')
    latest = binding796(witness)
    spec = importlib.util.spec_from_file_location('qf_build', ROOT/'verification/tests/build_gap38_i8_f16_lane3.py')
    helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
    plan = helpers.read(OUT/'repaired-aligned-600-20260930-01/plan.json')
    case = next(c for c in plan['cases'] if c.get('spike'))
    spike = Path(case['spike'])
    need(helpers.sha(spike) == case['spike_sha256'], 'Frozen Spike binary')
    out.mkdir()
    (out/'qbs_fma_align795_data.h').write_text(header())
    b = helpers.Build(out)
    b.flags = [('-march=rv64gc_zfh' if f.startswith('-march=') else f) for f in b.flags]
    b.inc += ['-I'+str(out)]
    b.bind_sources([APP, Path(__file__), Path(__file__).with_name('test_preflight_qbs_fma_align795.py'),
                    WITNESS, Path(proof.__file__), Path(mature.shared.spike_trace.__file__)])
    host = b.compile(APP, 'host-case', ['-DQF_HOST=1', '-I'+str(out)], host=True)
    ref = b.compile(ROOT/'verification/qbs/qbs_ref.c', 'host-ref', host=True)
    exe = out/'host-reference'
    b.link([b.host,host,ref,'-lm','-o',exe], 'host-link')
    host_gate(b.run([exe], 'host-reference').stdout.decode())
    start = b.compile(ROOT/'verification/tests/gap75_start.S', 'startup')
    strings = b.compile(ROOT/'apps/common/string.c', 'strings', ['-fno-builtin'])
    b.bind_sources([ROOT/'verification/tests/gap75.ld'])
    metadata_rows = {}
    for label, flags in (('dut', []), ('reference', ['-DQF_SOFTWARE_REFERENCE=1'])):
        obj = b.compile(APP, label, flags)
        elf = out/(label+'.elf')
        b.link([b.cc,*b.flags,'-fuse-ld=lld','-nostdlib','-static','-Wl,--gc-sections',
                '-T'+str(ROOT/'verification/tests/gap75.ld'),start,strings,obj,'-o',elf], label+'-link')
        symbols, read = metadata(elf)
        if label == 'dut':
            need(int.from_bytes(read(symbols['qf_native_site'],4),'little') == 0x00b5045b,
                 'Exact native M1 vd8 rs1a0 rs2a1 QBEXEC')
        else:
            need([int.from_bytes(read(symbols[s],4),'little') for s in STAGES] == list(STAGE_WORDS),
                 'All authored scalar FP reference sites assembled exactly')
        metadata_rows[label] = dict(elf=str(elf), sha256=helpers.sha(elf), symbols=symbols)
    result = b.run([spike,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                    '-l','--log-commits',out/'reference.elf'], 'spike', timeout=180)
    need('exception ' not in result.stderr.decode(), 'No Spike trap')
    commits = mature.shared.spike_trace.parse_spike_commits(out/'spike.stderr.log')
    checks = spike_gate(commits, metadata_rows['reference']['symbols'])
    helpers.verify(witness['pins']); helpers.verify(b.sources); helpers.verify(b.tools); helpers.verify(b.link_inputs)
    inputs = dict(witness['pins'], **latest['pins'], **helpers.pins([spike,Path(mature.__file__),Path(mature.rv64c.__file__)]))
    helpers.save(out/'preflight.json',dict(status='QBS_FMA_ALIGN795_HOST_SPIKE_REFERENCE_PASS_NOT_CUSTOM_NATIVE',
        source_witness_sha256=WITNESS_SHA, baseline=latest, EL_seal=witness['EL_seal'],
        inputs=inputs, sources=b.sources, tools=b.tools, link_inputs=b.link_inputs,
        artifacts=metadata_rows, outputs=helpers.pins(p for p in out.iterdir() if p.is_file()), checks=checks,
        compiler_scalar_ISA='rv64gc_zfh; explicit .option arch,+v only for authored RVV',
        candidate_missing_positions_with_host_one_witness=latest['remaining_host_one_witness_positions'], gain_measured=None,
        native_custom_execution_verified=False, EDA_started=False, RTL_changed=False, coverage_admitted=False,
        future_native_gates=['Exact sealed custom ELF/owner operands', 'FP accepted requests, alignment fields and status per owner',
                             'Full scalar/memory and all defined VRF bytes', 'AXI/drain and latest formal raw OR incremental gain'],
        source_only_padding_positions=56, padding_applied=False))
    print(json.dumps(dict(output=str(out), seal=helpers.sha(out/'preflight.json'), checks=checks)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); prepare(args.output.resolve())
