"""One V1 descriptor/stride fixture: Host/Spike software reference, never EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from elftools.elf.elffile import ELFFile
import build_akv_column_boundary_v2_preflight as reuse
import targeted_toggle_evidence_v2 as toggle
from rank_cva6_scalar_data767 import typed_nodes
from branch720_next_report_contract import native_inventory

shared = reuse.shared
ROOT, OUT, require, save = shared.ROOT, shared.OUT, shared.require, shared.save
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vakv_descriptor_entropy_stride.c'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
BASE = OUT / 'itlb-bulk-offline-admitted774-parent-20261007-01'
BASE_SHA = '5a5f9cdb4fcd5a26ba48628344a1c1028426709453bd8cb1adbc2c94d3344a28'
SCOPE = reuse.SCOPE
WORDS = [0x0000505b, 0x00b5205b, 0x00b5205b, 0x00b5205b, 0x0005345b, 0x0000505b]
CHECKS_SW, CHECKS_DUT = 3930, 3932
FIELDS = {'descriptor_q', 'descriptor.reserved0', 'descriptor.reserved1', 'descriptor.reserved2',
          'context_q_stride_q', 'context_k_stride_q', 'context_v_stride_q'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ranges(bases, stride, rows=1, tokens=1, head=64, tile=0, v2=False):
    require(all(type(x) is int for x in [*bases, stride, rows, tokens, head, tile]), 'Integer ABI')
    require(len(bases) == 3 and rows == tokens == 1 and head == 64 and tile == 0,
            'Only the one-row/one-token D64 oracle')
    require(128 <= stride <= 0xffffffff and not stride & (31 if v2 else 1), 'Exact V1/V2 alignment')
    require(all(b >= 0 and not b & 1 and b + 127 <= 0xffffffffffffffff for b in bases), 'Mapped even row range')
    return [(role, b, 128) for role, b in enumerate(bases, 1)]


def descriptor(bases, stride):
    ranges(bases, stride)
    return struct.pack('<4B2H4I5Q', 1, 1, 1, 0, 64, 1, stride, stride, stride, 0, *bases, 0, 0)


def frame(phase):
    require(type(phase) is int and 0 <= phase < 6, 'Exact phase')
    return struct.pack('<8Q', *(0xc100+phase*16+i for i in range(8))) + struct.pack('<2048H',
        *(0x2400+i if phase >= 4 and r == 8 else 0x1000+r*64+i
          for r in range(32) for i in range(64))) + struct.pack('<8Q', *(0xc200+phase*16+i for i in range(8)))


def source_bytes():
    return b''.join(struct.pack('<8Q', *(0xb100+s*16+i for i in range(8))) +
        struct.pack('<64H', *(0x2400+s*0x1000+i for i in range(64))) +
        struct.pack('<8Q', *(0xb200+s*16+i for i in range(8))) for s in range(3))


def native_sites(blob, symbols):
    h = struct.unpack_from('<HHIQQQIHHHHHH', blob, 16)
    require(blob[:6] == b'\x7fELF\x02\x01' and h[0:3] == (2, 243, 1) and
            not h[6] & 1 and h[8] == 56, 'Exact RV64 noC ELF')
    found = {}
    for n in range(h[9]):
        kind, flags, off, addr, _, size, total, _ = struct.unpack_from('<IIQQQQQQ', blob, h[4]+56*n)
        if kind != 1:
            continue
        require(size <= total and off+size <= len(blob) and
                0x80000000 <= addr <= addr+total <= 0x80200000, 'ELF fit/load segment')
        if flags & 1:
            require(addr % 4 == size % 4 == 0, 'No compressed executable')
            for k in range(0, size, 4):
                w = int.from_bytes(blob[off+k:off+k+4], 'little')
                if w & 127 == 0x5b:
                    found[addr+k] = w
    expected = {symbols['entropy_site_'+str(n)]: w for n, w in enumerate(WORDS)}
    require(len(expected) == 6 and found == expected, 'Exact six native commands, V1 FULL only')
    return [dict(phase=n, pc=symbols['entropy_site_'+str(n)], opcode=w, fault=n == 1)
            for n, w in enumerate(WORDS)]


def symbols(path, names):
    with path.open('rb') as stream:
        table = ELFFile(stream).get_section_by_name('.symtab')
        require(table is not None, 'Missing ELF symbols')
        found = {n: [] for n in names}
        for s in table.iter_symbols():
            if s.name in found:
                found[s.name].append(s['st_value'])
    require(all(len(v) == 1 for v in found.values()), 'Missing/ambiguous business symbol')
    return {k: v[0] for k, v in found.items()}


def validate(commits, sym):
    require(commits and len(commits) <= 100000 and not any(c.vector_writes or c.pc == sym['trap_fail']
            for c in commits), 'Incomplete/oversize/unexpected software execution')
    mem = reuse.memory(commits)
    def read(name, length):
        a = sym[name]
        require(all(a+i in mem for i in range(length)), 'Missing actual bytes: '+name)
        return bytes(mem[a+i] for i in range(length))
    require(read('tohost', 8) == struct.pack('<Q', 1) and
            read('g75_result', 8) == struct.pack('<2I', CHECKS_SW, 0) and
            read('num_failed', 4) == bytes(4), 'Software signature')
    require(read('entropy_snapshots', 6*4224) == b''.join(frame(p) for p in range(6)), 'Full VRF/guards')
    seed = struct.pack('<8Q', *(0xa100+i for i in range(8))) + frame(0)[64:-64] + struct.pack('<8Q', *(0xa200+i for i in range(8)))
    require(read('entropy_seed', 4224) == seed and read('entropy_sources', 768) == source_bytes(), 'Seed/source guards')
    bases = [sym['entropy_sources']+s*256+64 for s in range(3)]
    require(read('entropy_descriptors', 192) == b'\xff'*64+descriptor(bases, 128)+descriptor(bases, 0xfffffffe), 'All descriptor bytes')
    require(read('entropy_csrs', 288) == struct.pack('<36Q', *([21,0,64,8,2,1]*6)), 'Exact actual CSR observations')
    require(read('entropy_status', 24) == struct.pack('<6I', 0,1,0,0,0,0) and
            read('entropy_trap_count', 8) == struct.pack('<Q', 1) and
            read('entropy_semantic_error', 4) == struct.pack('<I', 3), 'VERSION3 not architectural cause2')
    require(read('entropy_scan', 48) == struct.pack('<12I', *([512,0]*6)) and
            read('g75_trap', 24) == bytes(24), 'Complete frame scans / no real Spike trap')
    terminal = [v for c in commits for a,v in c.memory_accesses if a == sym['tohost'] and v is not None]
    require(terminal == [1], 'Unique terminal')
    return dict(status='HOST_SPIKE_SOFTWARE_ADAPTER_PASS_NOT_NATIVE_CUSTOM', commits=len(commits),
        checks=CHECKS_SW, native_checks=CHECKS_DUT, full_frames=6, VRF_bytes=24576, CSR_bytes=288,
        real_Spike_traps=0, semantic_VERSION_error=3, native_custom_executed=False,
        full_native_scalar_qualified=False, full_native_protocol_qualified=False)


def typed_path(name):
    require(re.fullmatch(r'[A-Za-z_$][\w$]*(?:\[-?\d+(?::-?\d+)?\]|\.[A-Za-z_$][\w$]*)*', name),
            'Invalid typed native object path')
    return tuple(re.findall(r'[A-Za-z_$][\w$]*|\[-?\d+(?::-?\d+)?\]', name))


def typed_overlap(left, right):
    a, b = typed_path(left), typed_path(right)
    # A member/container prefix owns descendants; distinct array selectors do not.
    return a[:len(b)] == b or b[:len(a)] == a


def assert_unexcluded(blob, target_names=FIELDS):
    entries, _ = native_inventory(blob)
    for scope, _, _, line in entries:
        if line == 'WHOLE_SCOPE':
            require(not (scope == SCOPE or SCOPE.startswith(scope+'.')), 'Whole exclusion overlaps stimulus')
        elif scope == SCOPE and line.startswith('Toggle '):
            match = re.match(r'Toggle (?:0to1 |1to0 )?(\S+)', line)
            require(match and not any(typed_overlap(match[1], f) for f in target_names),
                    'Qualified Toggle overlaps target field')


def parser_dependencies():
    functions = (reuse.memory, typed_nodes, native_inventory, toggle.rows, toggle.union,
                 toggle.definitions, toggle.xml, toggle.digest, toggle.require,
                 shared.parse_spike_commits, shared.sha, shared.check, shared.save, shared.require)
    return sorted({Path(f.__code__.co_filename).resolve() for f in functions} |
                  {Path(reuse.__file__).resolve(), Path(shared.__file__).resolve(),
                   Path(toggle.__file__).resolve()})


def evidence():
    pins = {}
    def bound(p, expected):
        require(sha(p) == expected, 'Pin drift: '+str(p)); pins[str(p)] = expected
        return p.read_bytes()
    manifest = json.loads(bound(BASE/'admission-manifest.json', BASE_SHA))
    require(manifest['coverage_admitted'] is True, 'Formal774 required')
    ledger_path = BASE/'combined-inputs.txt'
    ledger = bound(ledger_path, manifest['output_pins'][str(ledger_path)]).decode().splitlines()
    require(len(ledger) == len(set(ledger)) == 775, '774 exact unique input ledger')
    book_path = BUILD/'build-source-pins.json'
    book = json.loads(bound(book_path, manifest['input_pins'][str(book_path)]))
    rels = ['hardware/src/vlsu/akv/akv_engine.sv','hardware/src/vlsu/akv/akv_context.sv',
            'hardware/src/vlsu/vlsu.sv','hardware/include/akv_pkg.sv','hardware/src/vlsu/qbs/qbs_read_engine.sv']
    for rel in rels:
        p = ROOT/rel; bound(p, book[str(p)])
    decoder = OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    bound(decoder, book[str(ROOT/'hardware/src/ara_dispatcher.sv')])
    cache_path = OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    cache = json.loads(bound(cache_path, '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'))
    old_ledger = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(ledger[:742] == bound(old_ledger, cache['input_pins'][str(old_ledger)]).decode().splitlines(), 'Exact741 cache prefix')
    union = {SCOPE: {k: cache['instances'][SCOPE][k] for k in ('width','checksum','bits')}}
    for vd in ledger[742:]:
        p, = (Path(vd)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml')
        rows, actual = toggle.rows(p, [SCOPE])
        require(actual == manifest['input_pins'][str(p)], 'Exact admitted suffix XML'); pins[str(p)] = actual
        union = toggle.union(union, rows)
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    for p in paths: bound(p, manifest['input_pins'][str(p)])
    checks, defs = toggle.definitions(*(toggle.xml(p) for p in paths), [SCOPE])
    require(checks[SCOPE] == union[SCOPE]['checksum'] == '4015856550', 'Compiled Toggle identity')
    ns, _ = typed_nodes(defs[SCOPE]['shape'], union[SCOPE])
    targets = [n for n in ns if n['name'] in FIELDS]
    require({n['name'] for n in targets} == FIELDS and len(targets) == 7, 'Complete exact typed target groups')
    qpath = OUT/'native-full771-pack-owner-offline-closure-agent-20261007-01/qualification.json'
    q = json.loads(bound(qpath, '5cb90569a4cde0cfaa8dc064269f90cb2eb9c20a88c732fbaf7b615e1b1b29fd'))
    el = OUT/'native-full771-padding-pack-prepared-agent-20261007-01/combined.el'
    target_names = {n['name'] for n in targets}
    assert_unexcluded(bound(el, q['output_pins'][str(el)]), target_names)
    # Pending newer families are not inferred from filenames: qualified native
    # receipts, their exact pinned ELs, and each complete scope are inspected.
    for result_path, status in [
        (OUT/'mfpu272-five-phase-prepared-agent-20261007-01/capture-result.json', 'MFPU272_EXACT_FIVE_PHASE_LOCAL_QUALIFIED_NOT_APPLIED'),
        (OUT/'rvh0-exception60-native772-v5-agent-prepared-20261007-01/capture-result.json', None)]:
        r = json.loads(result_path.read_bytes()); pins[str(result_path)] = sha(result_path)
        if status: require(r['status'] == status, 'Qualified MFPU receipt')
        p = result_path.parent/'first.el'; require(str(p) in r['pins'], 'Missing qualified EL pin')
        assert_unexcluded(bound(p, r['pins'][str(p)]), target_names)
    return pins, dict(population=774, manifest_sha256=BASE_SHA, scope=SCOPE, toggle_checksum=checks[SCOPE],
        design_module=defs[SCOPE]['module'], fields=targets, arrays_not_flattened=True,
        prediction_is_not_measured_gain=True, official_percentage=None, exclusions_generated=False,
        existing_qualified_EL_target_overlap=0, required_final_admission_baseline='latest formal explicit seal, no fork')


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh agent-owned output')
    pins, target=evidence()
    deps=[APP, ROOT/'apps/common/akv_abi.h', ROOT/'apps/common/string.c', ROOT/'verification/tests/gap75_start.S',
          ROOT/'verification/tests/gap75.ld', Path(__file__), Path(__file__).with_name('test_build_akv_descriptor_entropy_preflight.py'),
          *parser_dependencies(),
          shared.LLVM/'clang',shared.LLVM/'ld.lld',shared.LLVM/'llvm-readelf',shared.LLVM/'llvm-objdump',shared.SPIKE,
          Path('/usr/bin/cc').resolve()]
    deps += list((ROOT/'verification/ara_verify').glob('*.py'))
    for p in deps: pins[str(p)] = sha(p)
    shared.check(pins); out.mkdir(); save(out/'target-before.json',target)
    def run(cmd,name,timeout=120):
        cmd=list(map(str,cmd)); save(out/(name+'-command.json'),cmd)
        with (out/(name+'.stdout')).open('x') as stdout,(out/(name+'.stderr')).open('x') as stderr:
            subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=timeout,check=True)
    try:
        include='-I'+str(ROOT/'apps/common')
        run(['/usr/bin/cc','-O2','-fno-tree-vectorize','-DAKV_ENTROPY_SOFTWARE','-DAKV_ENTROPY_HOST',include,APP,'-o',out/'host'],'host-compile')
        run([out/'host'],'host',30)
        require((out/'host.stdout').read_text() == 'AKV_ENTROPY checks=3930 errors=0\n','Independent Host failure')
        flags=['--target=riscv64-unknown-elf','-march=rv64gv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany',
            '-mno-relax','-msmall-data-limit=0','-O2','-fno-vectorize','-fno-slp-vectorize','-ffreestanding',
            '-fno-builtin','-mno-implicit-float','-fuse-ld=lld','-nostdlib',include,
            '-T'+str(ROOT/'verification/tests/gap75.ld'), ROOT/'verification/tests/gap75_start.S']
        run([shared.LLVM/'clang',*flags,APP,ROOT/'apps/common/string.c','-o',out/'input.elf'],'native-compile')
        run([shared.LLVM/'clang',*flags,'-DAKV_ENTROPY_SOFTWARE',APP,ROOT/'apps/common/string.c','-o',out/'software.elf'],'software-compile')
        names=['tohost','g75_result','num_failed','g75_trap','trap_fail','entropy_seed','entropy_sources','entropy_descriptors',
               'entropy_snapshots','entropy_csrs','entropy_status','entropy_scan','entropy_trap_count','entropy_trap','entropy_semantic_error']
        sw=symbols(out/'software.elf',names); native=symbols(out/'input.elf',names+['entropy_handler']+['entropy_site_'+str(n) for n in range(6)])
        sites=native_sites((out/'input.elf').read_bytes(),native); save(out/'native-sites.json',sites)
        run([shared.LLVM/'llvm-objdump','-d',out/'input.elf'],'native-disassembly')
        run([shared.SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',out/'software.elf'],'spike',180)
        validation=validate(shared.parse_spike_commits(out/'spike.stderr'),sw); save(out/'spike-validation.json',validation)
        bases=[native['entropy_sources']+s*256+64 for s in range(3)]
        proof=dict(V1_opcodes=WORDS, V2_FULL_executed=False, valid_stride=[128,0xfffffffe],
            offered_payload_ranges_each_FULL=ranges(bases,128), high_stride_payload_ranges=ranges(bases,0xfffffffe),
            rejected_VERSION_error=3, native_exception=dict(pc=native['entropy_site_1'],cause=2,tval=0),
            rejected_FULL=dict(read_ranges=1,read_payload_bytes=64,q_external_bytes=0,kv_external_bytes=0,replay_bytes=0),
            valid_FULL=dict(read_ranges=4,read_payload_bytes=448,q_external_bytes=128,kv_external_bytes=256),
            cursor_after_last_offer_may_advance=True, later_offers_blocked_by_range_count=True,
            native_read_and_protocol_evidence_still_required=True)
        save(out/'range-oracle.json',proof); shared.check(pins)
        outputs={str(p):sha(p) for p in out.iterdir()}; pins.update(outputs)
        save(out/'preflight-manifest.json',dict(status='AKV_DESCRIPTOR_ENTROPY_V1_SOFTWARE_PREFLIGHT_PASS_NOT_VCS',
            baseline_tests=774, baseline_seal=BASE_SHA, pins=pins, input_elf=str(out/'input.elf'), software_elf=str(out/'software.elf'),
            symbols=native,software_symbols=sw,validation=validation,oracle=proof,
            dut_commands=6,dut_checks=CHECKS_DUT,dut_traps=1,dut_custom_write_bytes=128,timeout_seconds=600,
            full_native_scalar_qualified=False, full_native_protocol_qualified=False,
            software_reference_is_not_native_Spike=True, coverage_admitted=False,EDA_launched=False,rtl_changed=False))
        print(json.dumps(dict(output=str(out),seal=sha(out/'preflight-manifest.json'),validation=validation)),flush=True)
    except Exception as error:
        save(out/'failure.json',dict(status='PREFLIGHT_FAILED_NOT_NATIVE_FAILURE',reason=str(error))); raise


if __name__ == '__main__': main()
