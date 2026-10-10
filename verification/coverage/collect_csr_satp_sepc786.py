"""Full scalar/gold/native CSR-owner terminal qualification; no EDA/admission."""
import argparse
from collections import deque
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
from types import FunctionType, SimpleNamespace

import run_csr_satp_sepc786 as runner
import qualify_csr_frozen_counter_terminal as memory
import qualify_ptw_sfence_boundary_terminal as primitive
import collect_c910_float_edge_initialized777 as coverage
import audit_gap115_axi_v2 as wave
import coverage_bitmap_delta as bitmap
from ara_verify import spike_trace, vector_commit

life, require, oracle = runner.life, runner.require, runner.oracle
CORE = oracle.SCOPE
CSR, BUFFER = CORE + '.csr_regfile_i', CORE + '.ex_stage_i.csr_buffer_i'
MONITOR = 'ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q'
WIDTHS = {'ara_tb.clk': 1, 'ara_tb.rst_n': 1, MONITOR: 64, CORE + '.csr_commit_commit_ex': 1}
WIDTHS.update({CSR + '.' + n: w for n, w in {
    'commit_ack_i': 2, 'pc_i': 64, 'commit_instr_i.trans_id': 3, 'csr_op_i': 8,
    'csr_addr_i': 12, 'csr_wdata_i': 64, 'csr_rdata_o': 64, 'priv_lvl_o': 2,
    'mstatus_q.mprv': 1, 'mstatus_q.mie': 1}.items()})
WIDTHS.update({BUFFER + '.' + n: w for n, w in {
    'csr_valid_i': 1, 'csr_ready_o': 1, 'csr_commit_i': 1, 'csr_reg_q.valid': 1, 'fu_data_i.trans_id': 3,
    'fu_data_i.operand_a': 64, 'fu_data_i.operand_b': 64, 'flush_i': 1}.items()})


def terminal_gate(state, started, identity, record):
    runner.exact_fields(state, dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0,
        timeout=False, case=runner.NAME, coverage_admitted=False, admission_performed=False,
        dut_self_check_verified=False, terminal_oracle_verified=False), 'Failed/incomplete terminal')
    require(type(state['wall_seconds']) in (int, float) and math.isfinite(state['wall_seconds'])
            and 0 <= state['wall_seconds'] <= 180, 'Elapsed/budget receipt')
    runner.exact_fields(started, dict(budget_s=180, input_elf=str(runner.ELF), elf_sha256=runner.ELF_SHA,
        image=str(life.IMAGE), image_sha256=runner.IMAGE_SHA, command=record['command'],
        foreground_lifetime=True, coverage_admitted=False), 'Startup receipt')
    require(type(state['pid']) is type(started['pid']) is type(started['process_group']) is int
        and state['pid'] == started['pid'] == started['process_group'] > 0
        and not Path('/proc/%d' % state['pid']).exists(), 'Live/foreign process')
    runner.exact_fields(identity, dict(pid=state['pid'], executable=str(life.IMAGE.resolve()),
        cwd=record['output'], command=record['command'], process_group=state['pid'], service=record['service'], verified=True),
        'Actual executable/cwd/argv/PGID receipt')
    require(type(identity['cgroup']) is str and any(line.rsplit('/', 1)[-1] == record['service']
        for line in identity['cgroup'].splitlines()), 'Owning cgroup receipt')


def scalar_gate(result):
    runner.exact_fields(result, dict(status='TERMINAL_TOHOST_MATCH', matched_instructions=673,
        matched_scalar_writes=388, matched_floating_writes=0, matched_scalar_memory_accesses=168,
        ara_committed_instructions=673, ara_retired_instructions=673, ara_trap_events=0,
        skipped_unobservable_register_values=0, stopped_at_unobservable=None, mismatch=None,
        terminal_ecall=None, aligned_vector_faults=[]), 'Full scalar prefix/differential required')
    require(result['terminal_tohost']['address'] == '0x0000000080001000' and
        result['terminal_tohost']['write_value'] == '0x1', 'Precise terminal')


def csr_expected(reference, rows, ops):
    registers, values, result = {i: 0 for i in range(32)}, {0x180: 0, 0x141: 0}, []
    for row, c in zip(rows, reference):
        insn = c.instruction; address = insn >> 20; fun = insn >> 12 & 7
        if insn & 127 == 0x73 and address in values:
            rs, rd = insn >> 15 & 31, insn >> 7 & 31
            require(fun in (1, 2) and (fun == 1 or rs == 0), 'Exact matrix CSR opcode')
            operand, old = registers[rs], values[address]
            require(not rd or c.gpr_writes == {rd: old}, 'Independent CSR old-value sequencing')
            write = fun == 1
            operation = ops['CSR_WRITE' if write else 'CSR_READ']
            if write: values[address] = operand if address == 0x180 else operand & ~1
            result.append(dict(order=row['order'], cycle=row['cycle'], pc=c.pc, insn=insn, csr=address,
                operand=operand, old=old, new=values[address], operation=operation))
        registers.update(c.gpr_writes); registers[0] = 0
    require(len(result) == 30 and values == {0x180: 0, 0x141: 0}, 'All30 CSR owners/restored state')
    return result


def architecture(rows, reference, symbols, elf):
    require(len(rows) == len(reference) == 673 and all(r['event'] == 'retire' and r['trap'] == 0 for r in rows)
        and [r['order'] for r in rows] == list(range(673)), 'All scalar retirement owners')
    guard = memory.elf_file_bytes(elf, symbols['matrix_guards'], 16)
    require(guard == struct.pack('<QQ', *oracle.GUARDS), 'ELF file-backed independent guard values')
    regs, observed, counts, guard_reads = {i: 0 for i in range(32)}, [], {'read': 0, 'write': 0}, []
    for row, c in zip(rows, reference):
        require(c.instruction & 3 == 3 and row['pc'] == c.pc and row['insn'] == c.instruction
            and not c.vector_writes and not c.fpr_writes, 'Exact ordinary scalar PC/opcode')
        expected = {r: v for r, v in c.gpr_writes.items() if r}
        actual = {row['rd']: row['rd_wdata']} if row['rd'] else {}
        require(actual == expected, 'Scalar GPR/CSR result')
        d = primitive.memory_decode(c.instruction); accesses = []
        if d is None:
            require(not c.memory_accesses and row['mem_rmask'] == row['mem_wmask'] == 0, 'Unknown memory effect')
        else:
            size = d['size']; address = (regs[d['base']] + d['offset']) & memory.MASK64
            mask = ((1 << size) - 1) << (address & 7)
            require(address % size == 0 and row['mem_addr'] == address, 'Exact scalar memory address')
            if d['kind'] == 'write':
                value = regs[d['register']] & ((1 << (8 * size)) - 1)
                require(c.memory_accesses == ((address, value),) and not expected and row['mem_rmask'] == 0
                    and row['mem_wmask'] == mask and row['mem_wdata'] & ((1 << (8 * size)) - 1) == value,
                    'Full scalar store source/mask/data')
                require(address + size <= symbols['matrix_guards'] or address >= symbols['matrix_guards'] + 16,
                    'Guard-byte overwrite')
                accesses = [(address, value)]
            else:
                require(c.memory_accesses == ((address, None),) and set(expected) == {d['register']}
                    and row['mem_rmask'] == mask and row['mem_wmask'] == 0, 'Full scalar load mask/owner')
                low = expected[d['register']] & ((1 << (8 * size)) - 1)
                extension = primitive.signed(low, 8 * size) if d['signed'] else low
                require(expected[d['register']] == extension & memory.MASK64, 'Load signedness')
                accesses = [(address, None)]
                if symbols['matrix_guards'] <= address < symbols['matrix_guards'] + 16:
                    index = (address - symbols['matrix_guards']) // 8
                    require(address == symbols['matrix_guards'] + 8 * index and size == 8
                        and actual[d['register']] == oracle.GUARDS[index], 'Independent initialized guard LD')
                    guard_reads.append(index)
            counts[d['kind']] += 1
        observed.append(SimpleNamespace(pc=c.pc, instruction=c.instruction, vector_writes={},
            gpr_writes=actual, memory_accesses=accesses)); regs.update(expected); regs[0] = 0
    require(sum(counts.values()) == 168 and guard_reads == [0, 1], 'All168 memory events and guard readbacks')
    gold = oracle.validate(observed, symbols)
    proof, _ = runner.source_contract()
    expected_csr = csr_expected(reference, rows, proof['ops'])
    return dict(status='FULL_SCALAR_MEMORY_GOLD_EXACT_NOT_ADMITTED', instructions=673,
        memory_accesses=168, memory_counts=counts, guards=oracle.GUARDS, checks=gold['checks'],
        observed_bytes=336, expected_CSR=expected_csr)


def owner_gate(edges, expected):
    pending, actual, canceled = deque(), [], []
    for edge in edges:
        require(edge['commit'] == edge['buffer_commit'], 'Commit/buffer handshake')
        expected_ready = int(not ((edge['buffer_valid'] or edge['issue']) and not edge['buffer_commit']))
        require(edge['ready'] == expected_ready, 'Native CSR future-capacity ready formula')
        if edge['commit']:
            if edge['address'] in (0x180, 0x141):
                require(pending and len(actual) < len(expected), 'Missing/extra native CSR owner')
                issue = pending.popleft(); want = expected[len(actual)]
                require(edge['ack'] & 1 and edge['pc'] == want['pc'] and edge['cycle'] == want['cycle']
                    and edge['address'] == issue['address'] == want['csr']
                    and edge['tid'] == issue['tid'] and 0 <= edge['tid'] < 8
                    and issue['cycle'] <= edge['cycle']
                    and edge['wdata'] == issue['operand'] == want['operand']
                    and edge['rdata'] == want['old'] and edge['operation'] == want['operation'],
                    'Native CSR word/TID/PC/retire-cycle owner differs')
                actual.append(dict(want, tid=edge['tid'], issued_cycle=issue['cycle']))
        if edge['issue'] and edge['issue_address'] in (0x180, 0x141):
            require(not pending and (not edge['buffer_valid'] or edge['buffer_commit']),
                    'CSR single-entry issued pulse overwrites occupied owner')
            pending.append(dict(address=edge['issue_address'], operand=edge['issue_operand'],
                tid=edge['issue_tid'], cycle=edge['cycle']))
        if edge['flush']:
            canceled.extend(dict(p, canceled_cycle=edge['cycle']) for p in pending); pending.clear()
    require(not pending and len(actual) == len(expected) == 30, 'Incomplete native CSR owner ledger')
    return dict(status='ALL30_NATIVE_CSR_OWNER_WORD_TID_EXACT', committed=actual,
                canceled_uncommitted_issues=canceled, same_edge_old_commit_first=True)


def wave_audit(path, expected):
    parse = FunctionType(wave.vcd.__code__, dict(wave.vcd.__globals__, ROOT='ara_tb', WIDTHS={'clk': 1, 'rst_n': 1}))
    iterator = iter(parse(path)); _, decl = next(iterator)
    require(all(decl.get(n, {}).get('width') == w for n, w in WIDTHS.items()), 'Exact CSR probe declarations')
    def value(state, name):
        bits = state.get(decl[name]['code'], 'x'); require(set(bits) <= {'0', '1'}, 'Unknown active CSR signal: ' + name)
        return int(bits, 2)
    def edges():
        active = False
        for _, before, after in iterator:
            if before.get(decl['ara_tb.clk']['code']) != '0' or after.get(decl['ara_tb.clk']['code']) != '1': continue
            if before.get(decl['ara_tb.rst_n']['code']) != '1':
                require(not active, 'Unexpected reset during native CSR run')
                continue
            active = True
            require(value(before, CSR + '.priv_lvl_o') == 3 and value(before, CSR + '.mstatus_q.mprv') == 0
                and value(before, CSR + '.mstatus_q.mie') == 0, 'Native privilege/MPRV/MIE changed')
            commit = value(before, CORE + '.csr_commit_commit_ex'); issue = value(before, BUFFER + '.csr_valid_i')
            e = dict(cycle=value(before, MONITOR), commit=commit, buffer_commit=value(before, BUFFER + '.csr_commit_i'),
                issue=issue, flush=value(before, BUFFER + '.flush_i'),
                buffer_valid=value(before, BUFFER + '.csr_reg_q.valid'), ready=value(before, BUFFER + '.csr_ready_o'))
            e.update(address=value(before, CSR + '.csr_addr_i') if commit else -1,
                issue_address=value(before, BUFFER + '.fu_data_i.operand_b') & 4095 if issue else -1)
            if commit and e['address'] in (0x180, 0x141):
                e.update(ack=value(before, CSR + '.commit_ack_i'), pc=value(before, CSR + '.pc_i'),
                    tid=value(before, CSR + '.commit_instr_i.trans_id'), wdata=value(before, CSR + '.csr_wdata_i'),
                    rdata=value(before, CSR + '.csr_rdata_o'), operation=value(before, CSR + '.csr_op_i'))
            if issue and e['issue_address'] in (0x180, 0x141):
                e.update(issue_tid=value(before, BUFFER + '.fu_data_i.trans_id'),
                    issue_operand=value(before, BUFFER + '.fu_data_i.operand_a'))
            yield e
    return owner_gate(edges(), expected)


def raw_gain(run, out, record, pins):
    base = life.read_bound(runner.BASE / 'admission-manifest.json', runner.BASE_SHA)
    life.check(base['input_pins']); life.check(base['output_pins'])
    before = life.read_bound(runner.BASE / 'combined-bits.json', base['output_pins'][str(runner.BASE / 'combined-bits.json')])
    ledger = (runner.BASE / 'combined-inputs.txt').read_text().splitlines()
    require(ledger == [str(oracle.inventory.BUILD / 'sim/simv.vdb'), *before['tests']]
        and len(before['tests']) == len(set(before['tests'])) == 786 and str(run / 'code.vdb') not in before['tests'],
        'Formal786 exact prefix / distinct singleton')
    inputs = out / 'single-inputs.txt'
    with inputs.open('x') as stream: stream.write(ledger[0] + '\n' + str(run / 'code.vdb') + '\n')
    single = bitmap.collect(inputs)
    require(single['design'] == before['design'] and all(pins.get(p) == h for p, h in single['input_hashes'].items()),
        'Same frozen design/full metric input pins')
    after = bitmap.combine(before, single)
    require(after['tests'] == before['tests'] + single['tests'] and sum(len(x) for x in after['metrics'].values()) == 6162,
        'Full6162 OR exact786 prefix')
    target = life.read_bound(runner.PRE / 'target-before.json', record['pins'][str(runner.PRE / 'target-before.json')])
    scopes = [CORE, CSR]
    paths = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(paths) == 1 and base['input_pins'].get(str(paths[0])) == life.digest(paths[0]), '786 Toggle suffix binding')
    suffix, _ = oracle.toggle.rows(paths[0], scopes)
    paths = list((run / 'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(paths) == 1, 'One current Toggle test')
    sample, _ = oracle.toggle.rows(paths[0], scopes); fields = []
    for field in target['fields']:
        scope = field['scope']; old, new = suffix[scope], sample[scope]
        require(old['width'] == new['width'] and old['checksum'] == new['checksum'] == field['checksum'], 'Typed Toggle shape')
        remaining = [i for i in field['missing_coordinates'] if not int(old['bits'], 16) >> (old['width'] - 1 - i) & 1]
        gained = [i for i in remaining if int(new['bits'], 16) >> (new['width'] - 1 - i) & 1]
        fields.append(dict(scope=scope, checksum=field['checksum'], name=field['name'], before_missing=remaining, gained=gained))
    delta = bitmap.delta(before, after)
    for name, value in (('single-bits.json', single), ('combined-bits.json', after), ('raw-delta.json', delta), ('typed-target-toggle-gain.json', fields)):
        life.save(out / name, value)
    pins = life.merge_pins(life.merge_pins(pins, base['input_pins']), base['output_pins'])
    return dict(baseline=786, four_metrics=delta['metrics'], typed_target_new_directions=sum(len(f['gained']) for f in fields),
        official_percentage_claimed=False, diagnostic_not_admission=True), pins


def collect(run, seal, out):
    require(run.parent == out.parent == life.OUT and run.resolve() == run and out.resolve() == out and not out.exists(), 'Canonical fresh qualification')
    prepared = run.with_name(run.name + '.prepared.json'); record = life.read_bound(prepared, seal)
    require(life.read_bound(run / 'manifest.json', seal) == record, 'Executed manifest seal')
    runner.verify_prepared(run, record, terminal=True)
    terminal_gate(json.loads((run / 'simulation-status.json').read_bytes()), json.loads((run / 'started.json').read_bytes()),
        json.loads((run / 'live-identity.json').read_bytes()), record)
    pins = dict(record['pins']); files = [prepared, *[run / n for n in ('manifest.json', 'simulation-status.json', 'started.json',
        'live-identity.json', 'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log', 'console.log', 'csr-owner.vpd')],
        Path(__file__), Path(__file__).with_name('test_collect_csr_satp_sepc786.py')]
    vdb = run / 'code.vdb'; members = sorted(p for p in vdb.rglob('*') if p.is_file())
    require(members and not any(p.is_symlink() for p in vdb.rglob('*')), 'Complete nonaliased VDB')
    files += members
    for mod in tuple(sys.modules.values()):
        name = getattr(mod, '__file__', None)
        if name and name.endswith('.py') and Path(name).resolve().is_relative_to(life.ROOT / 'verification'): files.append(Path(name).resolve())
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files}); life.check(pins)
    out.mkdir()
    try:
        pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL); reference = runner.reference(pre)
        scalar = spike_trace.compare_commit_prefix(runner.PRE / 'spike.trace', run / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        life.save(out / 'scalar-comparison.json', scalar); scalar_gate(scalar)
        rows = primitive.parse_rows(run / 'commit_trace.csv'); arch = architecture(rows, reference, pre['symbols'], runner.ELF.read_bytes())
        primitive.zero.vector_zero(run / 'vector_trace.csv')
        vector = vector_commit.compare_vector_commits(runner.PRE / 'spike.trace', run / 'commit_trace.csv', run / 'vector_trace.csv', 0x80000000)
        life.save(out / 'vector-comparison.json', vector); primitive.vector_gate(vector)
        for name in ('run.vcs.log', 'console.log'):
            text = (run / name).read_text(); primitive.log_gate(text)
        console = (run / 'console.log').read_text().splitlines()
        require(console.count('CSR_OWNER_PROBE_READY') == 1 and
            not any(re.match(r'^CSR_OWNER_PROBE_ERROR(?:\s|$)', line) for line in console), 'Actual readonly probe markers')
        converter = runner.converter
        with (out / 'vpd2vcd.log').open('x') as log:
            subprocess.run([str(converter.CONVERTER), '-splitpacked', str(run / 'csr-owner.vpd'), str(out / 'csr-owner.vcd')],
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        owners = wave_audit(out / 'csr-owner.vcd', arch['expected_CSR'])
        folder = vdb / 'snps/coverage/db/testdata' / runner.NAME
        native = coverage.coverage_identity(folder, run, record, oracle.inventory.BUILD / 'sim/simv.vdb')
        require(all(pins.get(p) == h for p, h in native.items()), 'Five-metric native identity pins')
        gain, pins = raw_gain(run, out, record, pins)
        life.save(out / 'architecture-audit.json', arch); life.save(out / 'native-csr-owner-audit.json', owners)
        require(members == sorted(p for p in vdb.rglob('*') if p.is_file()), 'VDB membership drift'); life.check(pins)
        outputs = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        result = dict(status='CSR_SATP_SEPC786_FULL_SCALAR_NATIVE_OWNER_QUALIFIED_NOT_ADMITTED', run=str(run), run_seal=seal,
            input_pins=pins, output_pins=outputs, checks=44, observed_bytes=336, scalar_retirements=673,
            scalar_memory_accesses=168, native_CSR_owners=30, vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',
            raw_gain=gain, full_scalar_differential_qualified=True, coverage_admitted=False, RTL_changed=False, EDA_launched=False)
        life.save(out / 'qualification.json', result)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification.json'), gain=gain)))
    except BaseException as error:
        life.save(out / 'failure.json', dict(status='QUALIFICATION_HOLD_NOT_ADMITTED', reason=str(error))); raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--run', type=Path, required=True)
    p.add_argument('--run-seal', required=True); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    collect(a.run.absolute(), a.run_seal, a.output.absolute())
