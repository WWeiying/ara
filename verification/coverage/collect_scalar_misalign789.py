"""Six source-owned LSU faults, full scalar/gold and cancellation; no admission."""
import argparse
from collections import deque
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from types import FunctionType, SimpleNamespace

import run_scalar_misalign789 as runner
import collect_csr_satp_sepc786 as shared
import csr_satp_sepc_packed_adapter as packed
import csr_satp_sepc_cycle_adapter as sampling
from ara_verify import spike_trace, vector_commit

life, require, oracle = runner.life, runner.require, runner.oracle
CORE = shared.CORE
LSU = CORE + '.ex_stage_i.lsu_i'
CSR = CORE + '.csr_regfile_i'
MONITOR = shared.MONITOR


def source_proof():
    proof = packed.source_proof()
    cycle = sampling.source_contract()
    pins = life.merge_pins(proof['pins'], cycle['pins'])
    root = life.ROOT / 'hardware/deps/cva6/core'
    bookpath = shared.oracle.inventory.BUILD / 'build-source-pins.json'
    require(life.digest(bookpath) == packed.BOOK_SHA, 'Frozen source book')
    book = json.loads(bookpath.read_bytes()); texts = {}
    for name in ('cva6.sv', 'load_store_unit.sv', 'load_unit.sv', 'store_unit.sv', 'store_buffer.sv',
                 'cache_subsystem/wt_dcache_ctrl.sv', 'cva6_rvfi.sv',
                 'include/ariane_pkg.sv', 'include/build_config_pkg.sv',
                 'include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        p = root / name
        require(str(p) in book and life.digest(p) == book[str(p)], 'Frozen fault source: ' + name)
        pins[str(p)] = book[str(p)]; texts[name] = packed.clean(p.read_text())
    core, cfg, build = (texts[n] for n in ('cva6.sv', 'include/cv64a6_imafdcv_sv39_config_pkg.sv', 'include/build_config_pkg.sv'))
    params = dict(proof['parameters'])
    require("cfg.PLEN = (CVA6Cfg.XLEN == 32) ? 34 : 56;" in build, 'Physical address width producer')
    require('cfg.DCACHE_TAG_WIDTH = cfg.PLEN - DCACHE_INDEX_WIDTH;' in build
        and 'cfg.DCACHE_USER_WIDTH = CVA6Cfg.AxiUserWidth;' in build
        and 'int unsigned DCACHE_INDEX_WIDTH = $clog2(CVA6Cfg.DcacheByteSize / CVA6Cfg.DcacheSetAssoc);' in build,
        'Dcache packed width producers')
    def constant(name):
        return int(packed.unique(r'localparam\s+' + name + r'\s*=\s*(\d+)\s*;', cfg))
    size, ways, did = [constant(n) for n in ('CVA6ConfigDcacheByteSize', 'CVA6ConfigDcacheSetAssoc', 'CVA6ConfigDcacheIdWidth')]
    require(size == 8192 and ways == 4 and did == 1
        and 'localparam CVA6ConfigDataUserWidth = CVA6ConfigXlen;' in cfg,
        'Frozen actual cache configuration')
    for name in ('DcacheByteSize', 'DcacheSetAssoc', 'DcacheIdWidth'):
        require(re.search(name + r":\s*(?:unsigned|int)'\(CVA6Config" + name + r'\)', cfg) is not None,
            'Config instance producer')
    index = (size // ways).bit_length() - 1
    params.update({'CVA6Cfg.DCACHE_INDEX_WIDTH': index, 'CVA6Cfg.DCACHE_TAG_WIDTH': 56-index,
        'CVA6Cfg.DCACHE_USER_WIDTH': 64, 'CVA6Cfg.DcacheIdWidth': did})
    layouts = dict(proof['layouts'])
    for name in ('lsu_ctrl_t', 'dcache_req_i_t'):
        body = packed.unique(r'localparam\s+type\s+' + name + r'\s*=\s*struct\s+packed\s*\{([^{}]*)\}', core)
        require(body.count('(CVA6Cfg.XLEN/8)-1') == 1, 'Exact byte-enable arithmetic bound')
        body = body.replace('(CVA6Cfg.XLEN/8)-1', str(params['CVA6Cfg.XLEN']//8-1))
        layouts[name] = packed.packed(body, proof['enum_widths'], params)
    require(layouts['exception_t']['width'] == 203 and layouts['scoreboard_entry_t']['width'] == 438,
        'Exact exception/commit layouts')
    anchors = {
        'load_store_unit.sv': ['LD, SD, FLD, FSD,', "if (lsu_ctrl.vaddr[2:0] != 3'b000)",
            'cva6_misaligned_exception.cause = riscv::LD_ADDR_MISALIGNED;',
            'cva6_misaligned_exception.cause = riscv::ST_ADDR_MISALIGNED;'],
        'load_unit.sv': ["req_port_o.data_req = 1'b1;", "req_port_o.tag_valid = 1'b1;",
            "req_port_o.kill_req = 1'b1;", 'if (ex_i.valid) begin'],
        'store_unit.sv': ['if (ex_i.valid && (state_q != IDLE)) begin', "st_valid = 1'b0;"],
        'store_buffer.sv': ['if (valid_i) begin'],
        'cache_subsystem/wt_dcache_ctrl.sv': ["miss_req_o             = 1'b0;", 'READ, REPLAY_READ: begin',
            'if (req_port_i.kill_req) begin', 'end else if (req_port_i.tag_valid | state_q == REPLAY_READ) begin'],
        'cva6_rvfi.sv': ['(commit_ack[i] && !ex_commit_valid && !commit_drop[i])',
            'ex_commit_cause == riscv::ENV_CALL_MMODE', 'ex_commit_cause == riscv::ENV_CALL_SMODE',
            'ex_commit_cause == riscv::ENV_CALL_UMODE', 'rvfi_instr_o[i].valid <= valid;',
            'rvfi_instr_o[i].pc_rdata <= commit_instr_pc[i];']}
    # Frozen bytes, declarations and explicit producer anchors are all bound.
    for name, tokens in anchors.items():
        for token in tokens: require(token in texts[name], 'Fault/cancellation/RVFI source anchor: ' + token)
    require(re.search(r'\.valid_i\s*\(\s*store_buffer_valid\s*\)', texts['store_unit.sv']) is not None
        and 'assign store_buffer_valid = st_valid & (!CVA6Cfg.RVA || (amo_op_q == AMO_NONE));' in texts['store_unit.sv'],
        'Fault store suppression bound to actual buffer input')
    return dict(pins=pins, layouts=layouts, parameters=params,
        RVFI_non_ecall_fault_not_valid=True,
        fault_accounting='Six native CSR exception owners plus exact Spike/handler frames; not six invented RVFI retire rows',
        load_policy='Speculative cache index request allowed; fault tag killed before downstream completion',
        store_policy='Fault st_valid must remain zero, prohibiting store-buffer allocation',
        external_AXI_directly_probed=False,
        AXI_nonissue_claim_scope='Source-bound LSU cancellation/no store enqueue, not direct external AXI waveform observation')


def terminal_gate(state, started, identity, record):
    runner.exact_fields(state, dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, timeout=False,
        case=runner.NAME, coverage_admitted=False, admission_performed=False,
        dut_self_check_verified=False, terminal_oracle_verified=False), 'Exact successful terminal')
    require(type(state['wall_seconds']) in (int, float) and math.isfinite(state['wall_seconds'])
        and 0 <= state['wall_seconds'] <= runner.BUDGET, 'Bounded wall time')
    runner.exact_fields(started, dict(budget_s=runner.BUDGET, input_elf=str(runner.ELF), elf_sha256=runner.ELF_SHA,
        image=str(life.IMAGE), image_sha256=runner.IMAGE_SHA, command=record['command'],
        foreground_lifetime=True, coverage_admitted=False), 'Exact startup')
    require(type(state['pid']) is type(started['pid']) is type(started['process_group']) is int
        and state['pid'] == started['pid'] == started['process_group'] > 0
        and not Path('/proc/%d' % state['pid']).exists(), 'Terminal PID/group')
    runner.exact_fields(identity, dict(pid=state['pid'], executable=str(life.IMAGE.resolve()), cwd=record['output'],
        command=record['command'], process_group=state['pid'], service=record['service'], verified=True), 'Executed identity')
    require(type(identity['cgroup']) is str and any(x.rsplit('/', 1)[-1] == record['service']
        for x in identity['cgroup'].splitlines()), 'Exact owning cgroup')


def architecture(rows, reference, symbols, elf, ledger):
    require(len(rows) == len(reference) == 866 and all(r['trap'] == 0 for r in rows),
        'RVFI valid source excludes non-ECALL faults; exact866 normal owners')
    require(shared.memory.elf_file_bytes(elf, symbols['mis_guards'], 16)
        == __import__('struct').pack('<QQ', *oracle.GUARDS), 'ELF independent initialized guards')
    regs = {i: 0 for i in range(32)}; observed = []; memcount = 0; handlers = []
    for r, c in zip(rows, reference):
        require(r['pc'] == c.pc and r['insn'] == c.instruction and c.instruction & 3 == 3
            and not c.vector_writes and not c.fpr_writes, 'Full no-C scalar PC/opcode')
        want = {k: v for k, v in c.gpr_writes.items() if k}
        got = {r['rd']: r['rd_wdata']} if r['rd'] else {}
        require(want == got, 'Full GPR/CSR differential')
        d = shared.primitive.memory_decode(c.instruction)
        if d is None:
            require(not c.memory_accesses and r['mem_rmask'] == r['mem_wmask'] == 0, 'Unexpected memory effect')
        else:
            n = d['size']; address = (regs[d['base']] + d['offset']) & ((1 << 64) - 1)
            mask = ((1 << n) - 1) << (address & 7)
            require(address % n == 0 and r['mem_addr'] == address, 'Full scalar memory address/alignment')
            if d['kind'] == 'write':
                value = regs[d['register']] & ((1 << (8*n)) - 1)
                require(c.memory_accesses == ((address, value),) and r['mem_wmask'] == mask
                    and r['mem_rmask'] == 0 and r['mem_wdata'] & ((1 << (8*n)) - 1) == value,
                    'Full scalar store source/mask/data')
            else:
                require(c.memory_accesses == ((address, None),) and r['mem_rmask'] == mask
                    and r['mem_wmask'] == 0 and d['register'] in want, 'Full scalar load owner/mask')
                low = want[d['register']] & ((1 << (8*n)) - 1)
                value = shared.primitive.signed(low, 8*n) if d['signed'] else low
                require(want[d['register']] == value & ((1 << 64) - 1), 'Load extension')
            memcount += 1
        observed.append(SimpleNamespace(pc=c.pc, instruction=c.instruction, vector_writes={}, fpr_writes={},
            gpr_writes=got, memory_accesses=c.memory_accesses))
        if c.pc == symbols['mis_handler']: handlers.append(r['cycle'])
        regs.update(want); regs[0] = 0
    require(memcount == 226 and len(handlers) == 6, 'All memory effects and six handler entries')
    gold = oracle.validate(observed, symbols, ledger)
    return dict(status='FULL_SCALAR_AND_SIX_TRAP_GOLD_EXACT', instructions=866, memory_accesses=226,
        gold=gold, handlers=handlers, expected_traps=ledger)


def owner_gate(edges, expected, handler_cycles):
    detected = {}; responses = deque(); commits = []; returned = []; speculative_kills = 0
    last = None
    for e in edges:
        require(type(e['cycle']) is int and (last is None or e['cycle'] == last + 1), 'Native contiguous cycle epoch')
        last = e['cycle']
        if e['detector'] is not None:
            d = e['detector']; require(d['cause'] in (4, 6) and d['tval'] & 7 == 3
                and 0 <= d['tid'] < 8, 'Detector legality/TID')
            detected[(d['tid'], d['cause'], d['tval'])] = e['cycle']
        for r in e['responses']:
            key = (r['tid'], r['cause'], r['tval'])
            require(key in detected and detected[key] <= e['cycle'], 'Return without owned LSU detection')
            require(len(returned) < 6 and {k: r[k] for k in ('cause', 'tval')}
                == {k: expected[len(returned)][k] for k in ('cause', 'tval')}, 'Exact ordered fault return')
            responses.append(dict(r, returned_cycle=e['cycle'])); returned.append(dict(r))
        if e['load_fault']:
            require(not e['tag_valid'] or e['kill_req'], 'Fault load tag reached cache without cancellation')
            speculative_kills += int(e['tag_valid'] and e['kill_req'])
        if e['store_fault']: require(e['st_valid'] == 0, 'Fault store entered store buffer')
        if e['commit'] is not None:
            require(responses and len(commits) < 6, 'Unowned/extra CSR exception')
            actual = e['commit']; response = responses.popleft(); want = expected[len(commits)]
            require({k: actual[k] for k in ('pc', 'cause', 'tval')} == want
                and actual['tid'] == response['tid'] and actual['cause'] == response['cause']
                and actual['tval'] == response['tval'] and e['ack'] == 0
                and response['returned_cycle'] <= e['cycle'] < handler_cycles[len(commits)],
                'Precise PC/TID/exception/no-ack/handler owner')
            commits.append(dict(actual, cycle=e['cycle'], returned_cycle=response['returned_cycle']))
    require(len(returned) == len(commits) == 6 and not responses, 'All six fault owners complete')
    return dict(status='SIX_LSU_RETURN_AND_CSR_FAULT_OWNERS_EXACT', owners=commits,
        killed_speculative_tags=speculative_kills, no_fault_store_enqueue=True,
        external_AXI_directly_observed=False, no_external_side_effect_basis='Source-bound killed load tag and no fault store enqueue plus full memory/gold')


def wave_audit(path, expected, handler_cycles, terminal_cycle):
    proof = source_proof(); layouts = proof['layouts']
    parse = FunctionType(shared.wave.vcd.__code__, dict(shared.wave.vcd.__globals__, ROOT='ara_tb', WIDTHS={'clk': 1, 'rst_n': 1}))
    stream = iter(parse(path)); _, decl = next(stream)
    parents = {LSU + '.lsu_ctrl': ('lsu_ctrl_t', 1), LSU + '.cva6_misaligned_exception': ('exception_t', 1),
        LSU + '.load_exception_o': ('exception_t', 1), LSU + '.store_exception_o': ('exception_t', 1),
        LSU + '.i_load_unit.ex_i': ('exception_t', 1), LSU + '.i_store_unit.ex_i': ('exception_t', 1),
        LSU + '.i_load_unit.req_port_o': ('dcache_req_i_t', 1),
        CORE + '.commit_instr_id_commit': ('scoreboard_entry_t', 2), CSR + '.ex_i': ('exception_t', 1),
        CSR + '.mstatus_q': ('mstatus_rv_t', 1)}
    widths = {'ara_tb.clk': 1, 'ara_tb.rst_n': 1, MONITOR: 64, LSU + '.data_misaligned': 1,
        LSU + '.load_valid_o': 1, LSU + '.store_valid_o': 1, LSU + '.load_trans_id_o': 3,
        LSU + '.store_trans_id_o': 3, LSU + '.i_store_unit.st_valid': 1,
        CORE + '.commit_ack': 2, CSR + '.pc_i': 64, CSR + '.priv_lvl_o': 2}
    widths.update({p: layouts[t]['width'] * count for p, (t, count) in parents.items()})
    require(all(decl.get(n, {}).get('width') == w for n, w in widths.items()), 'Exact source-derived packed probe widths')
    def number(state, name):
        bits = state.get(decl[name]['code'], 'x')
        require(set(bits) <= {'0', '1'}, 'Unknown active signal: ' + name)
        return int(bits, 2)
    def fields(state, parent, element=0):
        kind, count = parents[parent]; layout = layouts[kind]
        value = number(state, parent) >> (element * layout['width'])
        return {n: value >> r & ((1 << (l-r+1)) - 1) for n, (l, r) in layout['fields'].items()}
    def edges():
        active = False
        for _, before, after in stream:
            if before.get(decl['ara_tb.clk']['code']) != '0' or after.get(decl['ara_tb.clk']['code']) != '1': continue
            if number(before, 'ara_tb.rst_n') != 1:
                require(not active, 'Unexpected reset'); continue
            active = True
            cycle = number(before, MONITOR)
            post = number(after, MONITOR)
            require(post == cycle+1 or (cycle == terminal_cycle and post == cycle),
                'Measured pre/post counter; only independently bound $finish edge may omit NBA')
            ms = fields(before, CSR + '.mstatus_q')
            require(number(before, CSR + '.priv_lvl_o') == 3 and ms['mie'] == ms['mprv'] == 0,
                'Native M-mode/MIE/MPRV invariant')
            e = dict(cycle=cycle, detector=None, responses=[], load_fault=False, store_fault=False,
                tag_valid=0, kill_req=0, st_valid=number(before, LSU + '.i_store_unit.st_valid'),
                commit=None, ack=number(before, CORE + '.commit_ack'))
            ctrl = fields(before, LSU + '.lsu_ctrl')
            if ctrl['valid'] and number(before, LSU + '.data_misaligned'):
                ex = fields(before, LSU + '.cva6_misaligned_exception')
                require(ex['valid'] and ex['tval'] == ctrl['vaddr'] and ex['tval2'] == ex['tinst'] == ex['gva'] == 0,
                    'Detector full64 effective address / no guest metadata')
                e['detector'] = dict(tid=ctrl['trans_id'], cause=ex['cause'], tval=ex['tval'])
            for unit, cause in (('load', 4), ('store', 6)):
                ex = fields(before, LSU + '.' + unit + '_exception_o')
                if number(before, LSU + '.' + unit + '_valid_o') and ex['valid']:
                    require(ex['cause'] == cause and ex['tval2'] == ex['tinst'] == ex['gva'] == 0, 'Exact load/store return cause')
                    e['responses'].append(dict(tid=number(before, LSU + '.' + unit + '_trans_id_o'), cause=cause, tval=ex['tval']))
                incoming = fields(before, LSU + '.i_' + unit + '_unit.ex_i')
                e[unit + '_fault'] = bool(incoming['valid'])
            if e['load_fault']:
                req = fields(before, LSU + '.i_load_unit.req_port_o')
                e.update(tag_valid=req['tag_valid'], kill_req=req['kill_req'])
            ex = fields(before, CSR + '.ex_i')
            if ex['valid']:
                slot = fields(before, CORE + '.commit_instr_id_commit', 0)
                require(ex['tval2'] == ex['tinst'] == ex['gva'] == 0 and slot['pc'] == number(before, CSR + '.pc_i'),
                    'Commit slot0 PC/guest metadata')
                e['commit'] = dict(pc=slot['pc'], tid=slot['trans_id'], cause=ex['cause'], tval=ex['tval'])
            yield e
    return owner_gate(edges(), expected, handler_cycles)


def collect(run, seal, out):
    run, out = Path(run).absolute(), Path(out).absolute()
    require(run.parent == out.parent == life.OUT and run.resolve() == run and out.resolve() == out and not out.exists(), 'Canonical exclusive output')
    sidecar = run.with_name(run.name + '.prepared.json'); record = life.read_bound(sidecar, seal)
    require(life.read_bound(run / 'manifest.json', seal) == record, 'Executed manifest exactly prepared')
    runner.verify_prepared(run, record, terminal=True)
    terminal_gate(*[json.loads((run / n).read_bytes()) for n in ('simulation-status.json', 'started.json', 'live-identity.json')], record)
    vdb = run / 'code.vdb'; members = sorted(p for p in vdb.rglob('*') if p.is_file())
    require(members and not any(p.is_symlink() for p in vdb.rglob('*')), 'Complete nonaliased VDB')
    files = [sidecar, *[run / n for n in ('manifest.json', 'simulation-status.json', 'started.json', 'live-identity.json',
        'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log', 'console.log', 'scalar-misalign.vpd')],
        Path(__file__).resolve(), Path(__file__).with_name('test_collect_scalar_misalign789.py'),
        Path(shared.__file__), Path(shared.primitive.__file__), Path(shared.memory.__file__),
        Path(shared.coverage.__file__), Path(shared.wave.__file__), Path(packed.__file__), Path(sampling.__file__)] + members
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and name.endswith('.py') and Path(name).resolve().is_relative_to(life.ROOT / 'verification'):
            files.append(Path(name).resolve())
    pins = life.merge_pins(record['pins'], {str(p): life.digest(p) for p in files}); life.check(pins)
    out.mkdir()
    try:
        pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL); ref = runner.reference(pre)
        scalar = spike_trace.compare_commit_prefix(runner.PRE / 'spike.trace', run / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        life.save(out / 'scalar-comparison.json', scalar)
        runner.exact_fields(scalar, dict(status='TERMINAL_TOHOST_MATCH', **record['scalar_reference_counts'],
            matched_floating_writes=0,
            ara_committed_instructions=866, ara_retired_instructions=866, ara_trap_events=0,
            skipped_unobservable_register_values=0, stopped_at_unobservable=None, mismatch=None,
            terminal_ecall=None, aligned_vector_faults=[]), 'Full scalar terminal differential')
        require(scalar['terminal_tohost']['address'] == '0x0000000080001000'
            and scalar['terminal_tohost']['write_value'] == '0x1', 'Exact terminal tohost')
        rows = shared.primitive.parse_rows(run / 'commit_trace.csv')
        arch = architecture(rows, ref, pre['symbols'], runner.ELF.read_bytes(), record['expected_traps'])
        shared.primitive.zero.vector_zero(run / 'vector_trace.csv')
        vector = vector_commit.compare_vector_commits(runner.PRE / 'spike.trace', run / 'commit_trace.csv', run / 'vector_trace.csv', 0x80000000)
        shared.primitive.vector_gate(vector); life.save(out / 'vector-comparison.json', vector)
        for n in ('run.vcs.log', 'console.log'): shared.primitive.log_gate((run / n).read_text())
        lines = (run / 'console.log').read_text().splitlines()
        require(lines.count('SCALAR_MISALIGN_PROBE_READY') == 1 and not any(re.match(r'^SCALAR_MISALIGN_PROBE_ERROR(?:\s|$)', x) for x in lines), 'Anchored actual probe markers')
        with (out / 'vpd2vcd.log').open('x') as log:
            subprocess.run([str(runner.converter.CONVERTER), '-splitpacked', str(run / 'scalar-misalign.vpd'), str(out / 'scalar-misalign.vcd')],
                stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        owners = wave_audit(out / 'scalar-misalign.vcd', record['expected_traps'], arch['handlers'], rows[-1]['cycle'])
        native = shared.coverage.coverage_identity(vdb / 'snps/coverage/db/testdata' / runner.NAME, run, record, shared.oracle.inventory.BUILD / 'sim/simv.vdb')
        require(all(pins.get(p) == h for p, h in native.items()), 'Five-metric native executed identity')
        life.save(out / 'architecture-audit.json', arch); life.save(out / 'native-fault-audit.json', owners)
        require(members == sorted(p for p in vdb.rglob('*') if p.is_file()), 'VDB membership unchanged'); life.check(pins)
        result = dict(status='SCALAR_MISALIGN789_FULL_SCALAR_SIX_NATIVE_FAULTS_QUALIFIED_NOT_ADMITTED',
            run=str(run), run_seal=seal, input_pins=pins, output_pins={str(p): life.digest(p) for p in out.iterdir() if p.is_file()},
            scalar_retirements=866, scalar_memory_accesses=226, checks=56, native_faults=6,
            vector_status='UNOBSERVABLE_ZERO_DESTINATIONS', full_scalar_differential_qualified=True,
            external_AXI_directly_observed=False, coverage_admitted=False, RTL_changed=False, EDA_launched=False)
        life.save(out / 'qualification.json', result)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification.json'))))
    except BaseException as error:
        life.save(out / 'failure.json', dict(status='QUALIFICATION_HOLD_NOT_ADMITTED', reason=str(error))); raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--run', type=Path, required=True)
    p.add_argument('--run-seal', required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); collect(a.run, a.run_seal, a.output)
