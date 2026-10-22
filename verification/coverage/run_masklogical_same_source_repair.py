"""One build03 native matrix, bounded simulation and independent byte oracle."""
import argparse
import csv
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from types import FunctionType

from elftools.elf.elffile import ELFFile
from ara_verify.contract import check_contract_log, parse_contract_summary
from ara_verify.vector_commit import _parse_vector_trace, _architectural_bytes
from audit_qbs_canonical_repair import digest, check_pins, require
import audit_gap115_axi_v2 as wave
import collect_gap71_canonical_qbs_positive779 as canonical

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'verification/out/failed-repair-image-20261008-03'
PRE = ROOT / 'verification/out/masklogical-same-source-preflight-20261008-01'
PROBE = Path(__file__).with_name('masklogical_cold_source_probe.tcl')
ELF_SHA = 'b303202028b57c63ad29a9e3268fdbbd24f409cc2de4567c0757906380ac9930'
MASK_SHA = '38427ef23970b7c20b9ae73cdc42f3fe813e6d42dbe51d36d89e120365bd78dd'
FUNCTS = (0x1b, 0x18, 0x1f, 0x1c)
WINDOWS = ((1, 0), (63, 7), (257, 0), (511, 255), (1024, 257), (0, 0), (31, 31), (31, 40))


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')


def cases():
    return [(op, 64, 0, 2) for op in range(4)] + [
        (op, vl, start, mode) for op in range(4) for vl, start in WINDOWS for mode in (0, 1)]


def expected(case):
    op, vl, start, mode = case
    values = {}
    for byte in range(128):
        if mode == 2 and byte >= 8:
            continue
        # Independent packed-byte Boolean oracle with a bit-range update mask.
        low = min(8, max(0, start - byte * 8))
        high = min(8, max(0, vl - byte * 8))
        active = ((1 << high) - 1) & ~((1 << low) - 1) & 255
        old = (0xa5 ^ byte * 7) & 255
        if mode != 1:
            value = 255 if op >= 2 else 0
        else:
            a, b = (0x69 ^ byte * 13) & 255, (0xc3 ^ byte * 29) & 255
            value = (a ^ b, (~a) & b, ~(a ^ b), (~a) | b)[op] & 255
        values[byte] = (old & ~active) | (value & active)
    return values


def is_mask(word):
    return word & 127 == 0x57 and (word >> 12) & 7 == 2 and word >> 26 in FUNCTS


def cold_wave(path):
    scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku'
    parse = FunctionType(wave.vcd.__code__, dict(wave.vcd.__globals__, ROOT=scope,
        WIDTHS={'clk_i': 1, 'rst_ni': 1}))
    iterator = iter(parse(path))
    _, decl = next(iterator)
    names = {n[len(scope)+1:]: d for n, d in decl.items() if n.startswith(scope + '.')}
    seen = {}
    def bits(state, name):
        require(name in names, 'Missing cold probe: ' + name)
        return state.get(names[name]['code'], 'x')
    for stamp, before, after in iterator:
        if bits(before, 'clk_i') != '0' or bits(after, 'clk_i') != '1': continue
        if bits(before, 'rst_ni') != '1' or bits(before, 'vinsn_issue_valid') != '1': continue
        src = bits(before, 'vinsn_issue.vs1')
        if set(src) - set('01') or not 24 <= int(src, 2) <= 27: continue
        if bits(before, 'vinsn_issue.vs2') != src: continue
        if any(set(bits(before, n)) != {'1'} for n in
               ('masku_operand_alu_valid', 'masku_operand_m_valid', 'masku_operand_alu_ready')): continue
        op = int(src, 2) - 24
        left, right = bits(before, 'masku_operand_m_seq'), bits(before, 'masku_operand_alu_seq')
        result = bits(before, 'alu_result_vm_m')
        require(set(result) == ({'1'} if op >= 2 else {'0'}), 'Cold-source identity result not known constant')
        if set(left + right) & set('xz'):
            seen[op] = dict(time_100fs=stamp, vs1=24+op, vs2=24+op,
                           left_unknown=bool(set(left) & set('xz')),
                           right_unknown=bool(set(right) & set('xz')))
    require(set(seen) == set(range(4)), 'Missing actual unknown-source handshake for one of four identities')
    return seen


def audit(out):
    console = (out / 'console.log').read_text()
    require(console.count('PASSED: masklogical_same_source cases=68 checks=65860 errors=0') == 1,
            'Complete 68-case software self-check missing')
    for name in ('console.log', 'run.vcs.log'):
        log = (out / name).read_text()
        require(not check_contract_log(out / name), 'Protocol/RTL failure in ' + name)
        require('FAILED:' not in log and '$finish called from file' in log and
                'V C S   S i m u l a t i o n   R e p o r t' in log, 'Abnormal simulator completion')
        contracts = [parse_contract_summary(line) for line in log.splitlines() if line.startswith('[ARA_CONTRACT]')]
        require(len(contracts) == 1 and contracts[0]['exceptions'] == 0, 'Unexpected exception')
    require('MASKLOGICAL_COLD_PROBE_READY' in console and 'MASKLOGICAL_COLD_PROBE_CLOSED' in console
            and not re.search(r'^MASKLOGICAL_PROBE_REJECT', console, re.M), 'Incomplete bounded cold probe')
    elf = ELFFile(BytesIO((out / 'input.elf').read_bytes()))
    sym = elf.get_section_by_name('.symtab')
    got = sym.get_symbol_by_name('got')[0]['st_value']
    eoc = sym.get_symbol_by_name('_eoc')[0]['st_value']
    starts, retired, reads = [], [], [set() for _ in cases()]
    retires = 0
    exit_stores = 0
    tail = []
    current = -1
    with (out / 'commit_trace.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            word = int(row['insn'], 16)
            if row['event'] == 'arch_start' and is_mask(word): starts.append((int(row['order']), word))
            if row['event'] != 'retire': continue
            require(int(row['order']) == retires and row['trap'] == '0', 'Retire order/trap differs')
            retires += 1
            pc = int(row['pc'], 16)
            if pc == eoc or tail: tail.append(row)
            if is_mask(word):
                current += 1
                require(current < 68, 'Extra mask instruction')
                retired.append(word)
            address = int(row['mem_addr'], 16)
            if int(row['mem_wmask'], 16) and address == 0xd0000000:
                require(int(row['mem_wdata'], 16) == 0 and int(row['mem_wmask'], 16) == 255,
                        'MMIO completion failure')
                exit_stores += 1
            if int(row['mem_rmask'], 16) and got <= address < got + 128:
                require(current >= 0 and word & 127 == 3 and (word >> 12) & 7 == 4,
                        'Expected unsigned-byte result readback')
                offset = address - got
                want = expected(cases()[current])
                require(offset in want and int(row['rd_wdata'], 16) == want[offset],
                        f'Independent readback mismatch case={current} byte={offset}')
                reads[current].add(offset)
    require(len(retired) == len(starts) == 68 and [w for _, w in starts] == retired,
            'Exact complete ordered 68 mask requests/retirements required')
    require(exit_stores == 1 and len(tail) >= 3 and all(
        int(r['pc'], 16) == eoc + 4 * (i % 4) for i, r in enumerate(tail)), 'Invalid native MMIO exit loop')
    lanes, vlen, acts = _parse_vector_trace(out / 'vector_trace.csv')
    require((lanes, vlen) == (4, 1024), 'Wrong geometry')
    for index, ((seq, word), case) in enumerate(zip(starts, cases())):
        op, vl, start, mode = case
        vs1, vs2 = ((24+op, 24+op) if mode == 2 else (8, 9 if mode else 8))
        require(word >> 26 == FUNCTS[op] and (word >> 15) & 31 == vs1 and
                (word >> 20) & 31 == vs2 and (word >> 7) & 31 == 16 and word & (1 << 25),
                'Wrong operation/source/destination/masking in matrix')
        want = expected(case)
        require(reads[index] == set(want), f'Missing full software readback case={index}')
        activity = acts.get(seq)
        if start >= vl:
            require(activity is None or not activity.writes, 'Empty/restart-complete operation wrote VRF')
            continue
        require(activity is not None and activity.allocations == activity.completions == 1,
                'Missing mask operation allocation/completion')
        values = _architectural_bytes(activity.writes, lanes, vlen)
        for (reg, byte), (value, _) in values.items():
            require(reg == 16, 'Mask wrote wrong destination')
            if byte in want: require(value == want[byte], f'VRF result mismatch case={index} byte={byte}')
        for bit in range(start, vl):
            require((16, bit // 8) in values, 'Missing active VRF byte')
    vcd = out / 'masklogical-cold.vcd'
    with (out / 'conversion.log').open('x') as log:
        subprocess.run([str(canonical.CONVERTER), '+splitpacked', str(out / 'masklogical-cold.vpd'), str(vcd)],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    cold = cold_wave(vcd)
    return dict(status='PASS', cases=68, checks=65860, independent_readback_bytes=sum(map(len, reads)),
                vrf_checked=True, cold_source_handshakes=cold, retired_instructions=retires,
                coverage_admitted=False, original_FOF_replaced=False)


def execute(out):
    require(not out.exists(), 'Fresh independent run directory required')
    status = json.loads((BUILD / 'build-status.json').read_text())
    require(status['status'] == 'PASS', 'Build not PASS')
    terminal = subprocess.check_output(['systemctl', '--user', 'show', status['unit'],
        '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus'], text=True)
    require(all(s in terminal.splitlines() for s in ('MainPID=0', 'ActiveState=inactive',
            'Result=success', 'ExecMainStatus=0')), 'Build service not successfully terminal')
    pins = json.loads((BUILD / 'build-image.json').read_text())
    pins.update(json.loads((BUILD / 'build-source-pins.json').read_text()))
    pre = json.loads((PRE / 'manifest.json').read_text())
    pins.update(pre['source_pins']); pins.update(pre['tool_pins']); pins.update(pre['binary_pins'])
    pins[str(ROOT / 'hardware/src/masku/masku.sv')] = MASK_SHA
    for path in (Path(__file__), PROBE, BUILD / 'build-status.json', BUILD / 'build-image.json',
                 BUILD / 'build-source-pins.json', Path(wave.__file__), Path(canonical.__file__), canonical.CONVERTER):
        pins[str(path)] = digest(path)
    check_pins(pins)
    require(digest(PRE / 'input.elf') == ELF_SHA, 'Original full matrix ELF differs')
    out.mkdir(parents=True)
    shutil.copyfile(PRE / 'input.elf', out / 'input.elf')
    save(out / 'source-pins.json', pins)
    save(out / 'build-terminal.json', dict(show=terminal))
    image = BUILD / 'sim/simv'
    command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(out / 'input.elf'), '+TESTCASE=masklogical_same_source_repair',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
        '-cm_name', 'masklogical_same_source_repair', '-ucli', '-do', str(PROBE)]
    save(out / 'command.json', dict(command=command, cwd=str(out), timeout_s=1800))
    started = time.monotonic()
    result = dict(status='RUNNING', coverage_admitted=False)
    save(out / 'status.json', result)
    try:
        with (out / 'console.log').open('x') as log:
            with subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, start_new_session=True) as proc:
                save(out / 'started.json', dict(pid=proc.pid, image=str(image), image_sha256=digest(image),
                    elf_sha256=ELF_SHA, epoch=time.time(), command=command))
                try:
                    code = proc.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try: proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                    save(out / 'simulation-status.json', dict(status='TIMEOUT', returncode=proc.returncode,
                         elapsed_s=time.monotonic()-started, pid=proc.pid))
                    raise
                save(out / 'simulation-status.json', dict(status='EXITED', returncode=code,
                     elapsed_s=time.monotonic()-started, pid=proc.pid))
                require(code == 0, f'Simulator exited {code}')
        check_pins(pins)
        require(digest(out / 'input.elf') == ELF_SHA, 'Runtime ELF changed')
        result = audit(out)
        check_pins(pins)
        result['artifacts'] = {str(p): digest(p) for p in out.iterdir() if p.is_file()}
    except Exception as error:
        result = dict(status='TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'FAIL',
                      reason=f'{type(error).__name__}: {error}', coverage_admitted=False)
    result['elapsed_s'] = time.monotonic() - started
    save(out / 'status.json', result)
    if result['status'] != 'PASS': raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    execute(args.output.resolve())
