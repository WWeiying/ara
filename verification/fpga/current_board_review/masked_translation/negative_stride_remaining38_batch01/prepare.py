#!/usr/bin/env python3
"""Source/parameter and native-oracle preparation only; no simulator launcher."""
import hashlib
import json
import re
import struct
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01')
MANIFEST = ARCHIVE / 'evidence/single_manifest.json'
PREFIX = 'rvv_small_fault_strided_negative_stride_e16_m1_'
ACCEPTED = {PREFIX + 'u1_s0_b3_m2_f0_g3', PREFIX + 'u1_s1_b3_m2_f0_g3'}
SELECT = re.compile(r'        if\(!\(unmapped==(\d) && store_case==(\d) && boundary==(\d) && mode==(\d) && split==(\d) && gap==(\d)\)\)continue;')
KEYS = ('unmapped', 'store', 'boundary', 'mode', 'split', 'gap')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def geometry(t):
    require(set(t) == set(KEYS), 'Tuple keys')
    require(all(type(t[k]) is int for k in KEYS), 'Tuple numeric types')
    require(t['unmapped'] in (0, 1) and t['store'] in (0, 1) and
            t['boundary'] in (1, 3, 5) and t['mode'] in (2, 3) and
            t['split'] == 0 and t['gap'] in (1, 3), 'Unsupported tuple')
    require(t['mode'] == 3 or t['boundary'] in (1, 3), 'Not one of archived40')
    stride = -2 * (1 + t['gap'])
    base = 4096 - t['boundary'] * stride - 2
    mask = 0x24 if t['mode'] == 2 else 0
    active = [i for i in range(8) if mask >> i & 1]
    fault = next((i for i in active if base + stride * i < 4096), None)
    completed = [i for i in active if fault is not None and i < fault]
    return dict(stride=stride, base_offset=base, mask=mask,
                active=active, fault_start=fault,
                original_expected_start=8 if fault is None else fault,
                fault_offset=None if fault is None else base + stride * fault,
                completed=completed, expected_faults=int(fault is not None),
                cause=None if fault is None else 15 if t['store'] else 13,
                permission_restore_only=not bool(t['unmapped']),
                refill_halfwords=2048 if t['unmapped'] else 0,
                repair_after_target_return=fault is None)


def original(h):
    return (37 * h + 11) & 65535


def oracle_rows(t):
    g = geometry(t)
    b, step = g['base_offset'], g['stride']
    start = g['original_expected_start']
    yield f"C {start} {b + start * step} {b} {step}"
    for i in range(128):
        slot = (i + 1) % t['boundary'] if i < t['boundary'] else (
            t['boundary'] + (i - t['boundary'] + 1) % (8 - t['boundary']) if i < 8 else i)
        yield f'I {i} {101 + 13 * i if i < 64 else 0} {2 * slot}'
    for i in range(16):
        yield f'K {i} {g["mask"]}'
    for i in range(130):
        yield f'B {i} 91'
    for i in range(64):
        value = 101 + 13 * i if t['store'] else (
            original((b + i * step) // 2) if i in g['active'] else 91)
        yield f'V {i} {value}'
    addresses = {b + i * step: i for i in range(8)}
    for h in range(4096):
        value = original(h)
        i = addresses.get(2 * h)
        if i in g['active']:
            if t['store']:
                value = 101 + 13 * i
            if i in g['completed']:
                value ^= 91
        yield f'D {h} {original(h)} {value}'


def compare_rows(t, text):
    require(text.splitlines() == list(oracle_rows(t)), 'Original-C/native independent oracle mismatch')


def block(source, first, last):
    require(source.count(first) == source.count(last) == 1, 'Source extraction anchors')
    return source[source.index(first):source.index(last)]


def native_source(source):
    # Keep archived address, initialization, and final wanted-value expressions.
    funcs = block(source, 'static unsigned active(', 'static void fill(')
    init = block(source, '        unsigned accessible_fields=', 'faults=0;handler_errors=0;')
    checks = block(source, '        for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){\n            word wanted=',
                   '        if(output[0]')
    old = '            if(output[f*cap+i+1]!=wanted)++errors;'
    require(checks.count(old) == 1, 'Original output oracle anchor')
    checks = checks.replace(old, '            printf("V %u %u\\n",i,(unsigned)wanted);')
    old = '            if(((word *)mapping)[i]!=wanted)++errors;'
    require(checks.count(old) == 1, 'Original memory oracle anchor')
    checks = checks.replace(old, '            printf("D %u %u %u\\n",i,(unsigned)original(at),(unsigned)wanted);')
    return '''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define STRIDED_REPLAY 1
#define NEGATIVE_STRIDE 1
#define ZERO_STRIDE 0
#define INDEXED_REPLAY 0
#define REPLAY_FIELDS 1
#define REPLAY_ELEMENTS 8
#define CAPACITY_LIMIT 128
typedef uint16_t word;
typedef uint16_t index_word;
static word input[128],output[130];
static index_word offsets[128];
static uint8_t mask[16];
static unsigned cap=64,store_case,expected_start;
static uintptr_t mapping,target,expected_address;
static long stride;
static word backing[4096];
''' + funcs + '''
int main(int argc,char **argv) {
  if(argc!=7)return 2;
  unsigned unmapped=(unsigned)atoi(argv[1]);
  store_case=(unsigned)atoi(argv[2]);
  unsigned boundary=(unsigned)atoi(argv[3]),mode=(unsigned)atoi(argv[4]);
  unsigned split=(unsigned)atoi(argv[5]),gap=(unsigned)atoi(argv[6]);
  (void)unmapped;
  mapping=(uintptr_t)backing;
''' + init + '''
  unsigned faults=expected_start<REPLAY_ELEMENTS;
  printf("C %u %ld %ld %ld\\n",expected_start,(long)(expected_address-mapping),(long)(target-mapping),stride);
  for(unsigned i=0;i<128;++i)printf("I %u %u %u\\n",i,input[i],offsets[i]);
  for(unsigned i=0;i<16;++i)printf("K %u %u\\n",i,mask[i]);
  for(unsigned i=0;i<130;++i)printf("B %u %u\\n",i,output[i]);
''' + checks + '\nreturn 0;\n}\n'


def helper_locations(elf, helpers):
    raw = elf.read_bytes()
    require(raw[:7] == b'\x7fELF\x02\x01\x01', 'ELF format')
    header = struct.unpack_from('<HHIQQQIHHHHHH', raw, 16)
    require(header[1] == 243 and header[8] == 56, 'RISC-V ELF headers')
    segments = []
    for i in range(header[9]):
        kind, flags, off, va, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', raw, header[4] + i * header[8])
        if kind == 1 and flags & 1:
            segments.append((va, raw[off:off + size]))
    result = {}
    for name, helper in helpers.items():
        values = [int(v, 16) for v in helper['encodings']]
        needle = b''.join(v.to_bytes(4 if v & 3 == 3 else 2, 'little') for v in values)
        matches = [va + m.start() for va, data in segments for m in re.finditer(re.escape(needle), data)]
        require(len(matches) == 1, 'Original helper bytes not unique: ' + name)
        result[name] = dict(pc=hex(matches[0]), instructions=len(values), encodings=helper['encodings'])
    return result


def load_cases():
    manifest = json.loads(MANIFEST.read_text())
    cases = manifest['cases']
    require(len(cases) == 40 and len({c['name'] for c in cases}) == 40, 'Exact archived40')
    require(ACCEPTED <= {c['name'] for c in cases}, 'Accepted membership')
    normalized = None
    pins = {str(MANIFEST): sha(MANIFEST)}
    proof_path = BASE / 'negative_stride_load_original01/software01/source_proof.json'
    pins[str(proof_path)] = sha(proof_path)
    helpers = json.loads(proof_path.read_text())['backend']['soc']['helpers']
    result = []
    for c in cases:
        folder = ARCHIVE / 'singles' / c['name']
        require(json.loads((folder / 'case.json').read_text()) == c, 'case.json vs manifest')
        require(sha(folder / 'scenario.elf') == c['sha256'], 'Archived ELF identity')
        for name, digest in c['scenario_sources'].items():
            require(sha(folder / name) == digest, 'Archived source identity')
        for name in ('case.json', 'scenario.c', 'scenario.S', 'scenario.elf'):
            pins[str(folder / name)] = sha(folder / name)
        t = c['selected_trial']
        g = geometry(t)
        source = (folder / 'scenario.c').read_text()
        matches = list(SELECT.finditer(source))
        require(len(matches) == 1 and dict(zip(KEYS, map(int, matches[0].groups()))) == t, 'Selected C tuple')
        norm = SELECT.sub('        /* selected single */', source)
        if normalized is None:
            normalized = norm
        require(norm == normalized, 'Unexpected C difference beyond tuple filter')
        require(c['sew'] == 16 and c['lmul'] == 'm1' and c['fields'] == 1, 'Shape drift')
        require(c['measured_trial']['completed'] and c['measured_trial']['errors'] > 0, 'Not measured failed single')
        locations = helper_locations(folder / 'scenario.elf', helpers)
        result.append(dict(name=c['name'], parameters=t, geometry=g, source=str(folder),
                           accepted_m6=c['name'] in ACCEPTED, original_case=c,
                           helper_proof=locations))
    return result, pins, normalized


def prepare(out):
    require(not out.exists(), 'Fresh output only')
    cases, pins, source = load_cases()
    out.mkdir()
    native = out / 'original_oracle_host.c'
    native.write_text(native_source(source))
    command = ['/usr/bin/cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(native), '-o', str(out / 'original_oracle_host')]
    started = time.monotonic()
    p = subprocess.run(command, capture_output=True, text=True, timeout=60)
    save(out / 'host_compile.json', dict(command=command, returncode=p.returncode,
                                       elapsed_s=time.monotonic()-started, stdout=p.stdout, stderr=p.stderr))
    require(p.returncode == 0, 'Native compile failed; receipt retained')
    host = []
    for c in cases:
        cmd = [str(out / 'original_oracle_host'), *[str(c['parameters'][k]) for k in KEYS]]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        require(p.returncode == 0, 'Native original oracle failed')
        compare_rows(c['parameters'], p.stdout)
        host.append(dict(name=c['name'], returncode=p.returncode, rows=len(p.stdout.splitlines()),
                         stdout_sha256=hashlib.sha256(p.stdout.encode()).hexdigest()))
    remaining = [c for c in cases if not c['accepted_m6']]
    require(len(remaining) == 38, 'Exact remaining38')
    groups = []
    for n in range(0, 38, 4):
        members = remaining[n:n+4]
        group = out / f'group{n//4:02d}'
        group.mkdir()
        rows = []
        for c in members:
            t, g = c['parameters'], c['geometry']
            rows.append('  {' + ','.join(str(x) for x in [t[k] for k in KEYS] +
                        [g['base_offset'], g['stride'], g['mask'], g['original_expected_start'], g['expected_faults']]) + '}')
        (group / 'cases.h').write_text('#ifndef NEGATIVE_STRIDE_CASES_H\n#define NEGATIVE_STRIDE_CASES_H\n'
            'struct ns_case { int unmapped,store,boundary,mode,split,gap,base,stride,mask,start,faults; };\n'
            'static const struct ns_case ns_cases[] = {\n' + ',\n'.join(rows) + '\n};\n#endif\n')
        groups.append(dict(group=n//4, cases=[c['name'] for c in members], count=len(members),
                           proposed_budget_s=7200 if len(members)==4 else 3600,
                           estimate_s=1111.6245557051152*len(members)*1.2,
                           estimate_is_not_measured=True))
    for kind in ('load', 'store'):
        for suffix in ('original01/reference01/status.json', 'vcs_m6_plan01/prepared01/complete.json'):
            path=BASE / ('negative_stride_' + kind + '_' + suffix)
            pins[str(path)] = sha(path)
    for path in HERE.glob('*.py'):
        pins[str(path)] = sha(path)
    require(all(sha(p)==h for p,h in pins.items()), 'Source pin drift')
    save(out / 'input_pins.json', pins)
    save(out / 'host.json', dict(status='ORIGINAL_C_NATIVE_ORACLE_MATCH_NOT_SV39_REFERENCE', cases=host,
                                 total_rows=sum(c['rows'] for c in host)))
    save(out / 'manifest.json', dict(status='PARAMETER_AND_HOST_READY_NOT_ELF_NOT_REFERENCE_NOT_DUT',
        original40=cases, remaining38=[c['name'] for c in remaining], accepted2=sorted(ACCEPTED),
        groups=groups, normalized_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        original_manifest_scope=json.loads(MANIFEST.read_text())['scope'],
        parent96_closed=False, linux_closed=False))
    save(out / 'artifact_pins.json', {str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(status='HOST_PARAMETER_READY', cases=40, remaining=38, groups=len(groups),
                         oracle_rows=sum(c['rows'] for c in host), output=str(out))))


if __name__ == '__main__':
    prepare(HERE / 'prepared01')
