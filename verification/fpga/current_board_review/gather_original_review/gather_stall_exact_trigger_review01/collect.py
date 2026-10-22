"""Read archived metadata/ELFs/UART only; never run or query a simulator."""
import hashlib
import json
import re
import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent
G = OUT.parents[1]
H = OUT.parent
C = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
P = C / 'rvv_permute_partitions01'
A = Path('/home/wangwy/openproject/ara_dsa')
M6 = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware/src')
pins = {}


def read(path):
    path = Path(path)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert str(path) not in pins or pins[str(path)] == digest
    pins[str(path)] = digest
    return data


def obj(path):
    return json.loads(read(path))


def instruction(data, pc):
    assert data[:6] == b'\x7fELF\x02\x01'
    phoff = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    for i in range(count):
        kind, _, off, va, _, filesz, _, _ = struct.unpack_from('<IIQQQQQQ', data, phoff + size * i)
        if kind == 1 and va <= pc and pc + 4 <= va + filesz:
            return f'{struct.unpack_from("<I", data, off + pc - va)[0]:08x}'
    raise ValueError(f'No file-backed instruction at {pc:x}')


triage = obj(C / 'stall_family_triage02/triage.json')
selected = [x for x in triage['cases'] if x['group'] == 'gather_operand_stream']
assert len(selected) == 11
records = []
detail = re.compile(r'RVV_PERMUTE_DETAIL op=\d+ seed=\d+ scalar=\d+ vl=\d+ mask=\d+ element=\d+ vstart=\d+ expected=\d+ actual=\d+$')
for x in sorted(selected, key=lambda x: x['report']):
    report_path = Path(x['report'])
    scene = report_path.parent
    report = obj(report_path)
    assert pins[str(report_path)] == x['report_sha256']
    binary = read(x['binary'])
    archived = read(scene / x['name'])
    assert binary == archived and hashlib.sha256(binary).hexdigest() == x['elf_sha256']
    for insn in x['instructions']:
        assert instruction(binary, insn['pc']) == insn['opcode']
    assert x['head_pc'] == x['last_pc'] + 4
    assert instruction(binary, x['head_pc']) == '00802573'
    for name in ('operations.S', 'operations.h'):
        read(P / x['name'] / name)
    raw = read(scene / 'batch_uart.bin').decode(errors='replace')
    console = read(scene / 'console.log')
    snapshots = report['progress_diagnosis']['snapshots']
    assert len(snapshots) == 2
    first, last = [s['core'] for s in snapshots]
    for key in ('retired', 'last_pc', 'head_pc', 'trap_count'):
        assert first[key] == last[key]
    assert last['cycles'] - first['cycles'] == x['cycle_delta'] > 0
    assert first['last_pc'] == x['last_pc'] and first['head_pc'] == x['head_pc']
    assert x['last_trial'] is None
    target_index = next(i for i, row in enumerate(report['results']) if row['name'] == x['name'])
    lines = raw.splitlines()
    records.append({
        'name': x['name'], 'report': str(report_path), 'binary': x['binary'],
        'elf_sha256': x['elf_sha256'], 'instructions': x['instructions'],
        'snapshots': snapshots, 'cycle_delta': x['cycle_delta'],
        'sample_interval_seconds': x['cycle_delta'] / snapshots[0]['identity']['frequency_hz'],
        'raw_uart': str(scene / 'batch_uart.bin'), 'console_bytes': len(console),
        'complete_newline_detail_rows': [line for line in raw.split('\n')[:-1] if detail.fullmatch(line.rstrip('\r'))],
        'unterminated_uart_tail': lines[-1] if lines and not raw.endswith('\n') else None,
        'report_detail_rows': [line for line in report['results'][target_index].get('output', '').splitlines() if 'RVV_PERMUTE_DETAIL' in line],
        'recorded_preceding_processes': report['results'][:target_index],
        'exact_unreturned_tuple': None, 'backend_valid_ready_vid_evidence': False,
        'classification': 'user_gather_no_scalar_retirement_backend_cause_unresolved',
    })

source = C / 'rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c'
read(source)
assert pins[str(source)] == 'b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca'
for path in [P / 'manifest.json', P / 'parent_mapping.json', G / 'CURRENT_SCOPE.md',
             A / 'hardware/fpga/vcu118/host_debug_fpga.py',
             A / 'hardware/fpga/ara_dsa_vcu118/rtl/board/ara_fpga_debug.sv']:
    read(path)
for name in ('STALL_TRIAGE.md', 'ALL_FAILURE_REVIEW.md'):
    read(A / 'hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro' / name)
for name in ('lane/lane_sequencer.sv', 'masku/masku.sv', 'ara_dispatcher.sv', 'ara_sequencer.sv'):
    read(M6 / name)
for name in ('lane_sequencer.sv', 'masku.sv'):
    read(C / 'rvv_verification_handoff02/deployed_rtl' / name)
for name in (
    'gather_repair05/m5_successor01/prefix_terminal_audit01/TERMINAL.md',
    'e16_m8_ops1_prefix98_terminal_audit01/REVIEW.md',
    'e16_m8_ops20_prefix98_terminal_audit01/REPORT.md',
    'e16_m8_ops3_prefix98_terminal_audit01/REPORT.md',
    'e8_m8_ops1_prefix66_terminal_audit01/REPORT.md',
    'e8_m8_ops3_prefix66_terminal_audit01/REPORT.md',
    'extra_helper_terminal_gate01/terminal01/REVIEW.md',
    'event_recovery_review01/TERMINAL_REVIEW03.md',
):
    read(H / name)
kernel = [{k: x.get(k) for k in ('name', 'group', 'report', 'last_pc', 'head_pc', 'last_trial')}
          for x in triage['cases'] if x['group'] == 'kernel_vector_state_wait']
for path, digest in pins.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
result = {'scope': 'STATIC_ARCHIVED_EVIDENCE_ONLY_NOT_DUT_ACCEPTANCE',
          'exact_stalled_tuples_recovered': 0, 'cases': records,
          'separate_kernel_wait_inventory': kernel, 'inputs_sha256': pins,
          'input_pins_unchanged': True,
          'probe_semantics_limitation': 'Current debug source read; exact original deployed debug build identity not established.'}
with (OUT / 'evidence.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps({'cases': len(records), 'pins': len(pins), 'exact_stalled_tuples': 0,
                  'preceding_process_records': sum(bool(x['recorded_preceding_processes']) for x in records),
                  'input_pins_unchanged': True}))
