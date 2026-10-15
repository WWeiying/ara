"""One-pass offline CSV acceptance; no guest execution or live service query."""
import collections
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import time

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
R = ROOT / 'original_e16_mf4_vcs_m6_plan02'
P = R / 'prepared01'
T = P / 'replay/tests/original_e16_mf4'
F = ROOT / 'original_e16_mf4_prepare01'
PLAN_SHA = '51711836aab45fa44a34f16e80801fb9ac0dbf2412cf6660577e0737c17f013c'
COMPLETE_SHA = 'c8db1b3ab326c64c2ee00384490ffa02724494487fb65a4591b5693d520507a1'
OLD_SHA = 'a9a60cc30f3d88d4b15441ec3d2da2bd7367f9334c9cb36731b262bbade50d3e'


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def load(p, name):
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def elf_reader(p):
    b = Path(p).read_bytes()
    assert b[:6] == b'\x7fELF\x02\x01'
    ph = struct.unpack_from('<Q', b, 32)[0]
    size, n = struct.unpack_from('<HH', b, 54)
    segments = []
    for j in range(n):
        t, _, off, va, _, fs, _, _ = struct.unpack_from('<IIQQQQQQ', b, ph+j*size)
        if t == 1:
            segments.append((va, va+fs, off))
    def get(a, size):
        for lo, hi, off in segments:
            if lo <= a and a+size <= hi:
                return b[off+a-lo:off+a-lo+size]
        raise AssertionError(('unmapped', hex(a)))
    return get


def input_index(s, i):
    if s == 0: return i % 2, False
    if s == 1: return 14, False
    if s == 2: return (2 if i % 2 else 15), False
    if s == 3: return (13 if i % 2 else 12), False
    if s == 4: return [2, 7, 3, 7, 11, 11][i % 6], i % 6 in (3, 5)
    if s == 5: return [8, 9, 10, 8, 9, 10][i % 6], i % 6 >= 3
    if s == 6: return (15 if i % 2 else 2), False
    return (7 if i % 2 else 2), False


def vector(i):
    op, width = i & 127, (i >> 12) & 7
    return (op in (0x57, 0x5b) or op in (7, 0x27, 0x2f) and width in (0, 5, 6, 7)
            or op == 0x73 and i >> 20 in (8, 9, 10, 15, 0xc20, 0xc21, 0xc22))


class Observer:
    def __init__(self, spec):
        self.spec = spec
        self.count = collections.Counter()
        self.pc = collections.Counter()
        self.pending, self.uops = {}, {}
        self.requests, self.arch, self.retvec = [], [], []
        self.first = self.last = -1
        self.maxcvx = self.maxuop = 0
        self.before = hashlib.sha256()
        self.after = hashlib.sha256()
        self.regs = [0]*32
        self.fixture_reads, self.output_reads, self.restores = [], [], []
        self.capacity, self.prelude, self.helper = [], [], []
        self.exit = None
        self.hp = [x['pc'] for x in spec['routine']]
        self.cp = [x['pc'] for x in spec['capacity_routine']]
        self.pp = [x['pc'] for x in spec['csr_prelude']]
        self.bits = [int(x, 16) for x in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)',
                                                  (F/'prepared/input_bits.h').read_text())]
        assert len(self.bits) == 16

    def rows(self, reader):
        assert reader.fieldnames == ['cycle', 'event', 'order', 'port', 'trans_id', 'pc', 'insn',
                                    'rd', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata', 'trap']
        for row in reader:
            original = tuple(row.items())
            assert None not in row and all(isinstance(v, str) for v in row.values())
            payload = json.dumps(original, separators=(',', ':')).encode()+b'\n'
            self.before.update(payload)
            self.observe(row)
            yield row
            assert tuple(row.items()) == original, 'Sealed consumer changed original row'
            self.after.update(json.dumps(tuple(row.items()), separators=(',', ':')).encode()+b'\n')
            self.count['unmodified_delivered_rows'] += 1

    def observe(self, r):
        c, e, i, order = int(r['cycle']), r['event'], int(r['insn'], 16), int(r['order'])
        assert c >= self.last and int(r['trap']) == 0
        if self.first < 0: self.first = c
        self.last = c
        self.count['rows'] += 1
        self.count[e] += 1
        if e == 'cvx_req':
            tid = int(r['trans_id'])
            assert vector(i) and tid not in self.pending
            self.pending[tid] = i
            self.requests.append(i)
            self.maxcvx = max(self.maxcvx, len(self.pending))
        elif e == 'cvx_resp':
            assert int(r['trans_id']) in self.pending
            del self.pending[int(r['trans_id'])]
        elif e == 'arch_start':
            assert order == len(self.arch)
            self.arch.append(i)
        elif e == 'uop_alloc':
            vid = int(r['port'])
            assert 0 <= order < len(self.arch) and self.arch[order] == i and vid not in self.uops
            self.uops[vid] = (order, i)
            self.maxuop = max(self.maxuop, len(self.uops))
        elif e == 'uop_done':
            assert self.uops.pop(int(r['port'])) == (order, i)
        else:
            assert e == 'retire' and order == self.count['retire']-1
            if vector(i): self.retvec.append(i)
            self.retirement(r, c, i, order)

    def retirement(self, r, cycle, i, order):
        s, sy, sites = self.spec, self.spec['symbols'], self.spec['sites']
        pc, rd, value = int(r['pc'], 16), int(r['rd']), int(r['rd_wdata'], 16)
        addr, rm, wm, wd = (int(r[k], 16) for k in ('mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'))
        assert int(s['instructions'][f'{pc:x}']['insn'], 16) == i
        self.pc[pc] += 1
        assert not any(lo <= pc < hi for lo, hi in s['unused_ranges']) and pc != sy['trap_entry']
        hp, cp, pp = self.hp, self.cp, self.pp
        if pc in hp:
            j = len(self.helper)
            assert j < 21 and pc == hp[j]
            if j: assert order == self.helper[-1]['order']+1
            self.helper.append(dict(pc=hex(pc), order=order, cycle=cycle))
            if j in (9, 10, 16, 17):
                src = (i >> 15) & 31
                assert self.regs[src] == 0 and rd == 0
                self.restores.append(dict(pc=hex(pc), csr=i >> 20, source_register=src,
                                          source_value=self.regs[src], order=order))
        if pc in cp:
            j = len(self.capacity)
            assert j < 3 and pc == cp[j]
            if j: assert order == self.capacity[-1]['order']+1
            self.capacity.append(dict(pc=hex(pc), order=order, rd=rd, value=value))
        if i & 127 == 0x73 and (i >> 12) & 7 and pc not in hp:
            assert len(self.prelude) < 7 and pc == pp[len(self.prelude)] and not self.capacity
            self.prelude.append(pc)
        # Every initialization write is checked against the unchanged original source loop.
        for name, area, width in [('input_store', 'input', 2), ('seed_store', 'seed', 2),
                                  ('mask_store', 'mask', 1), ('output_init', 'output', 1)]:
            if pc != sites[name]: continue
            n = self.count[name]
            if name == 'input_store':
                scenario, j = divmod(n, 16)
                assert scenario < 8
                idx, sign = input_index(scenario, j)
                want = self.bits[idx] ^ (0x8000 if sign else 0)
            elif name == 'seed_store':
                scenario, j = divmod(n, 64)
                assert scenario < 8
                want = self.bits[[1, 14, 2, 12, 2, 8, 1, 12][scenario]]
            elif name == 'mask_store':
                fill, j = divmod(n, 64)
                assert fill < 3360
                want = [255, 0, 85, 36][(fill//15) % 4]
            else:
                j, want = n, 91
                assert j < 144 and not self.helper
            assert addr == sy[area]+j*width and wm == ((1 << width)-1) << (addr % 8)
            assert wd & ((1 << (8*width))-1) == want
            self.count[name] += 1
        if pc in (sites['fixture_bits'], sites['fixture_flags']):
            n = len(self.fixture_reads)
            row, field = 3360+n//2, n % 2
            assert n < 6720 and addr == sy['fixtures']+row*16+field*8
            assert pc == sites['fixture_flags' if field else 'fixture_bits']
            assert rm == (15 if field else 255) and rd == (15 if field else 14)
            assert value == s['fixtures'][row][field]
            self.fixture_reads.append([addr, value])
        if pc == sites['output_read']:
            n = len(self.output_reads)
            want = 0 if n == 8 else 126 if n == 9 else 91
            assert n < 144 and len(self.helper) == 21 and addr == sy['output']+n
            assert rd == 16 and value == want and rm == 1 << (addr % 8)
            self.output_reads.append([addr, value])
        if addr == s['exit_address'] and wm:
            assert self.exit is None and pc == s['exit_store']['pc'] and wm == 255 and wd == 0
            assert len(self.output_reads) == 144 and len(self.fixture_reads) == 6720
            self.exit = dict(pc=hex(pc), order=order, cycle=cycle, address=hex(addr), value=wd)
        if rd: self.regs[rd] = value

    def finish(self):
        c = self.count
        assert not self.pending and not self.uops and self.retvec == self.requests == self.arch
        assert c['rows'] == c['unmodified_delivered_rows'] and self.before.digest() == self.after.digest()
        assert len(self.helper) == 21 and len(self.capacity) == 3 and len(self.prelude) == 7
        assert len(self.restores) == 4 and self.exit and len(self.output_reads) == 144
        assert [c[k] for k in ('input_store', 'seed_store', 'mask_store', 'output_init')] == [128, 512, 215040, 144]
        return dict(rows=c['rows'], first_cycle=self.first, last_cycle=self.last, retire_count=c['retire'],
                    vector_retire_count=len(self.retvec), cvx_request_count=c['cvx_req'],
                    cvx_response_count=c['cvx_resp'], cvx_max_inflight=self.maxcvx, cvx_replay_count=0,
                    arch_request_replay_count=0, cvx_exception_count=0, architecture_request_count=len(self.arch),
                    backend_uop_alloc_count=c['uop_alloc'], backend_uop_done_count=c['uop_done'],
                    backend_uop_max_inflight=self.maxuop)


def main():
    started = time.monotonic()
    assert not (OUT/'result.json').exists()
    assert sha(P/'complete.json') == COMPLETE_SHA and sha(P/'plan.json') == PLAN_SHA
    plan, terminal = read(P/'plan.json'), read(P/'complete.json')
    oldpath = ROOT/'original_e16_mf4_vcs_m6_plan01/prepared01/plan.json'
    assert sha(oldpath) == OLD_SHA
    old = read(oldpath)
    assert len(old['pins']) == 733 and len(plan['pins']) == 738
    pins = {}
    def add(mapping):
        for path, digest in mapping.items():
            assert path not in pins or pins[path] == digest, ('conflicting pin', path)
            pins[path] = digest
    add(old['pins']); add(plan['pins']); add(terminal['evidence_pins'])
    add({str(P/'complete.json'): COMPLETE_SHA, str(P/'plan.json'): PLAN_SHA, str(oldpath): OLD_SHA})
    image = Path(plan['image'])
    assert sha(image/'image.json') == plan['image_sha256'] == 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
    ledger = read(image/'image.json')
    snap = Path(ledger['snapshot'])
    snapshot = read(snap/'snapshot.json')
    assert sha(snap/'snapshot.json') == plan['snapshot_sha256'] == ledger['snapshot_sha256']
    assert snapshot['state'] == 'SEALED' and len(snapshot['files']) == 539 and len(ledger['files']) == 66
    assert ledger['configuration_sha256'] == '6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
    assert sha(image/'_build/vcs/simulator.conf') == ledger['configuration_sha256']
    assert sha(image/'_build/vcs/vcs_source_manifest.json') == ledger['manifest_sha256']
    add(ledger['files']); add({str(Path(snapshot['root'])/p): h for p, h in snapshot['files'].items()})
    proof = read(F/'sourceproof.json')
    add(proof['external_pins']); add(proof['prepared_pins'])
    for path, digest in pins.items(): assert sha(path) == digest, ('pre-audit drift', path)
    print('All identity pins verified; beginning single full CSV parse', flush=True)
    canonical = Path(proof['canonical'])
    assert 'rvv_verified_handoff03/rvv_small_redspecial02/' in str(canonical)
    for name in ('scenario.c', 'operations.S', 'operations.h', 'fixtures.h', 'input_bits.h', 'fp_reduction_inputs.h'):
        assert (canonical/name).read_bytes() == (F/'prepared'/name).read_bytes(), name
    spec = plan['spec']
    actual = elf_reader(T/'input.elf')
    original = elf_reader(F/'prepared/scenario.elf')
    for pc, row in spec['instructions'].items():
        assert int(pc, 16) == row['pc']
        assert actual(row['pc'], len(row['insn'])//2) == bytes.fromhex(row['insn'])[::-1]
    for name, window in proof['helper_windows']['soc'].items():
        assert len(window['original']) == len(window['new']) == 21
        for a, b in zip(window['original'], window['new']):
            assert a[1] == b[1] and original(a[0], len(a[1])//2) == actual(b[0], len(b[1])//2)
    assert spec['routine'] == [dict(pc=p, insn=i, text=t) for p, i, t in proof['helper_windows']['soc']['op_0']['new']]
    unused = [proof['helper_windows']['soc'][n]['new'] for n in ('op_1', 'op_2')]
    assert spec['unused_ranges'] == [[w[0][0], w[-1][0]+len(w[-1][1])//2] for w in unused]
    assert [x['insn'] for x in spec['capacity_routine']] == ['52fd', '00e2f557', '8082']
    assert [x['insn'] for x in spec['csr_prelude']] == ['30401073', '30529073', '3002a073',
                                                     '00305073', '00805073', 'c2202773', 'c22024f3']
    assert spec['symbols'] == read(F/'soc/symbols.json')
    fixtures = [[int(a, 16), int(b)] for a, b in re.findall(r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', (F/'prepared/fixtures.h').read_text())]
    assert spec['fixtures'] == fixtures and len(fixtures) == 6720
    checker = load(R/'checker.py', 'sealed_e16mf4_checker')
    assert terminal['status'] == 'PASS_M6_ORIGINAL_E16_MF4_SINGLE144_NOT_FULL_PARENT'
    assert terminal['plan_sha256'] == PLAN_SHA and terminal['aborted'] is False and terminal['pins_unchanged'] is True
    assert terminal['retries'] == 0 and terminal['full_parent_accepted'] is False and terminal['all11_accepted'] is False
    assert terminal['results'] == read(P/'replay/summary.json') and len(terminal['results']) == 1
    result = terminal['results'][0]
    assert result['name'] == checker.NAME and result['status'] == 'PASS' and result['returncode'] == 0 and not result['reason']
    assert result['artifact_dir'] == str(T) and 0 < result['elapsed_s'] < plan['timeout_s'] == 5400
    run = read(P/'replay/run.json')
    assert run['status'] == 'COMPLETE' and run['completed_at'] and run['status_counts'] == {'PASS': 1}
    assert run['tests'] == [checker.NAME] and run['jobs'] == 1 and run['timeout_s'] == 5400
    assert run['commit_trace'] is True and run['input_snapshots'] is True and run['simv'] == ledger['simv']
    assert not list(P.rglob('*firstfailure*')) and not list(P.rglob('*firsterror*')) and not (P/'complete.tmp').exists()
    inputs = read(T/'inputs.json')
    assert inputs['binary']['sha256'] == sha(T/'input.elf') == sha(F/'soc/program.elf') == checker.ELF_SHA
    assert inputs['binary']['path'] == str(T/'input.elf') and inputs['simv']['image_sha256'] == ledger['files']
    command = read(T/'command.json')
    assert command == dict(command=[ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                            '+PRELOAD='+str(T/'input.elf'), '+TESTCASE='+checker.NAME, '+NO_FSDB',
                            '+COMMIT_TRACE='+str(T/'commit_trace.csv')], cwd=str(T/'work'))
    for p in (T/'console.log', T/'work/run.vcs.log'):
        text = p.read_text()
        checker.console_gate(text)
        assert not re.search(r'first[ _-]?(?:error|failure)|\b(?:TIMEOUT|CANCELLED|FATAL)\b', text, re.I)
    observer = Observer(spec)
    with (T/'commit_trace.csv').open(newline='') as f:
        strict = checker.retirement(observer.rows(csv.DictReader(f)), spec)
    generic = observer.finish()
    generated = dict(generic=generic, strict=strict, csv_sha256=sha(T/'commit_trace.csv'))
    assert json.loads(json.dumps(generated)) == read(T/'strict_original.json')
    assert dict(generic, status='VALID') == read(T/'trace_summary.json')
    for path, digest in pins.items(): assert sha(path) == digest, ('post-audit drift', path)
    audit = dict(status='INDEPENDENT_M6_ORIGINAL_E16_MF4_SINGLE144_ACCEPTED_NOT_FULL_PARENT',
        accepted=True, DUT_accepted=True, plan_sha256=PLAN_SHA, complete_sha256=COMPLETE_SHA,
        image_sha256=plan['image_sha256'], elf_sha256=checker.ELF_SHA, source_canonical=str(canonical),
        old_plan_pins_verified=733, plan_pins_verified=738, unique_pins_pre_post=len(pins),
        frozen_sources=539, image_files=66, evidence_pins=len(terminal['evidence_pins']), pins_unchanged=True,
        returncode=result['returncode'], elapsed_s=result['elapsed_s'], aborted=False,
        marked_complete=run['status'], complete_matches_summary=True,
        console_and_runlog_firsterror_veto_pass=True, outer_service_terminal_observed=False,
        outer_service_returncode=None, outer_service_result=None,
        csv_parses=1, original_rows_delivered_unmodified=observer.count['unmodified_delivered_rows'],
        observer_before_sha256=observer.before.hexdigest(), observer_after_sha256=observer.after.hexdigest(),
        generated=generated, observer_counts=dict(observer.count),
        actual_pc_counts={hex(k): v for k, v in observer.pc.items()},
        observer_helper=observer.helper, observer_capacity=observer.capacity,
        observer_prelude=[hex(x) for x in observer.prelude], csr_write_operands=observer.restores,
        output_reads=observer.output_reads, fixture_field_reads=len(observer.fixture_reads), exit=observer.exit,
        raw_vector_payload_observed=False, full_parent_accepted=False, all11_accepted=False,
        source_scope='one canonical reduced single, original scenario3/l4/mask3/frm0/op0/sticky0; full144 oracle; all3360 fixture rows read, not3360 targets',
        no_live_query=True, no_guest_execution=True, audit_seconds=time.monotonic()-started,
        audit_script_sha256=sha(__file__))
    with (OUT/'result.json').open('x') as f:
        json.dump(audit, f, indent=2); f.write('\n')
    with (OUT/'verified_pins.json').open('x') as f:
        json.dump(pins, f, indent=2); f.write('\n')
    print(audit['status'], audit['audit_seconds'], sha(OUT/'result.json'), flush=True)


if __name__ == '__main__':
    main()
