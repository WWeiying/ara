"""CSR commit epoch to registered RVFI CSV epoch, using measured VCD counters."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import csr_satp_sepc_packed_adapter as packed

original, life, require = packed.original, packed.life, packed.require
PACKED_SHA = '7e0f4c503ee3d988eff41d5c8e13f31dd30d73547424d0114346ba192ff72d23'


def source_contract():
    require(life.digest(Path(packed.__file__)) == PACKED_SHA, 'Frozen packed adapter')
    proof = packed.source_proof(); pins = proof['pins']
    book = json.loads((original.oracle.inventory.BUILD / 'build-source-pins.json').read_bytes())
    names = dict(monitor='hardware/tb/ara_commit_monitor.sv', system='hardware/src/ara_system.sv',
        rvfi='hardware/deps/cva6/core/cva6_rvfi.sv', probes='hardware/deps/cva6/core/cva6_rvfi_probes.sv')
    sources = {}
    for key, relative in names.items():
        path = life.ROOT / relative
        require(str(path) in book and life.digest(path) == book[str(path)], 'Frozen RVFI clock source: ' + key)
        pins[str(path)] = book[str(path)]; sources[key] = path.read_text()
    cycle_semantics(sources)
    pins[str(Path(packed.__file__).resolve())] = PACKED_SHA
    return dict(pins=pins, packed_layout=proof['layouts'], cycle_binding=
        'Native CSR pre-edge operands; measured post-edge monitor counter equals next-edge pre-counter at registered RVFI CSV observation',
        arithmetic_cycle_offset_applied=False)


def cycle_semantics(sources):
    s = {name: packed.clean(text) for name, text in sources.items()}
    def anchors(name, tokens):
        for token in tokens: require(token in s[name], 'Missing cycle source anchor: ' + name + ':' + token)
    anchors('monitor', ('always_ff @(posedge clk_i or negedge rst_ni)', "cycle_q <= '0;",
        'cycle_q <= cycle_q + 1;', 'if (rvfi_instr_i[port].valid)', 'cycle_q, next_order, port,',
        'rvfi_instr_i[port].pc_rdata,', 'if (rvfi_instr_i[port].mem_wdata[31:0] == 32\x27d1)', '$finish;'))
    anchors('rvfi', ('always_ff @(posedge clk_i) begin', 'assign commit_ack = instr.commit_ack;',
        'assign commit_instr_pc = instr.commit_instr_pc;',
        'valid     = (commit_ack[i] && !ex_commit_valid && !commit_drop[i])',
        'rvfi_instr_o[i].valid <= valid;', 'rvfi_instr_o[i].pc_rdata <= commit_instr_pc[i];'))
    anchors('probes', ('instr.commit_ack = commit_ack_i;', 'instr.commit_instr_pc[i] = commit_instr_i[i].pc;',
                       'rvfi_probes_o.instr = instr;'))
    # Both named consumers share the same clock and the same RVFI wire, with no adapter register.
    for module, instance, ports in (
        ('cva6_rvfi', 'i_cva6_rvfi', (('clk_i', 'clk_i'), ('rvfi_probes_i', 'rvfi_probes'), ('rvfi_instr_o', 'rvfi_instr'))),
        ('ara_commit_monitor', 'i_ara_commit_monitor', (('clk_i', 'clk_i'), ('rvfi_instr_i', 'rvfi_instr')))):
        import re
        _, body = packed.unique(module + r'\s*#\((.*?)\)\s*' + instance + r'\s*\((.*?)\);', s['system'])
        for port, signal in ports:
            require(re.search(r'\.' + port + r'\s*\(\s*' + signal + r'\s*\)', body) is not None, 'RVFI clock/wire binding')


def counter(state, decl):
    bits = state.get(decl[original.MONITOR]['code'], 'x')
    require(bits and set(bits) <= {'0', '1'} and len(bits) <= 64, 'Unknown measured monitor counter')
    return int(bits, 2)


def rebind(stream, terminal_cycle=None):
    stream = iter(stream); tag, decl = next(stream); yield tag, decl
    previous_post, pending_commit, finish_time = None, False, None
    clk, reset, code = decl['ara_tb.clk']['code'], decl['ara_tb.rst_n']['code'], decl[original.MONITOR]['code']
    for time, before, after in stream:
        require(finish_time is None or time == finish_time, 'VCD continues after terminal finish edge')
        if before.get(clk) == '0' and after.get(clk) == '1' and before.get(reset) == '1':
            pre, post = counter(before, decl), counter(after, decl)
            if post != pre + 1:
                require(type(terminal_cycle) is int and pre == post == terminal_cycle and
                        before.get(decl[original.CORE + '.csr_commit_commit_ex']['code']) == '0' and
                        before.get(decl[original.BUFFER + '.csr_valid_i']['code']) == '0',
                        'Measured monitor NBA increment differs')
                finish_time = time
            require(previous_post is None or pre == previous_post, 'Next RVFI observation epoch discontinuity')
            previous_post = post; pending_commit = False
            commit = before.get(decl[original.CORE + '.csr_commit_commit_ex']['code']) == '1'
            if commit:
                bits = before.get(decl[original.CSR + '.csr_addr_i']['code'], 'x')
                require(set(bits) <= {'0', '1'}, 'Unknown committed CSR address')
                pending_commit = int(bits, 2) in (0x180, 0x141)
            before = dict(before)
            # Only the observation epoch changes; all CSR transaction fields remain pre-edge.
            before[code] = after[code]
        yield time, before, after
    require(not pending_commit, 'CSR has no subsequent RVFI observation edge')


def vcd(path):
    source_contract()
    rows = original.primitive.parse_rows(packed.RUN / 'commit_trace.csv')
    terminal = rows[-1]
    require(len(rows) == 673 and terminal['event'] == 'retire' and terminal['trap'] == 0 and
            terminal['mem_addr'] == 0x80001000 and terminal['mem_wmask'] != 0 and
            terminal['mem_wdata'] == 1, 'Exact CSV tohost terminal for finish/NBA exception')
    yield from rebind(packed.vcd(path), terminal['cycle'])


def wave_audit(path, expected):
    audit = FunctionType(original.wave_audit.__code__, dict(original.wave_audit.__globals__, wave=SimpleNamespace(vcd=vcd)))
    return audit(path, expected)


def measured_epochs(path, expected):
    stream = iter(packed.vcd(path)); _, decl = next(stream)
    samples, pending = [], None
    for time, before, after in stream:
        if before.get(decl['ara_tb.clk']['code']) != '0' or after.get(decl['ara_tb.clk']['code']) != '1': continue
        if before.get(decl['ara_tb.rst_n']['code']) != '1': continue
        if pending is not None:
            pending['next_edge_time'] = time; pending['next_edge_pre_counter'] = counter(before, decl)
            require(pending['post_counter'] == pending['next_edge_pre_counter'] == expected[len(samples)]['cycle'],
                    'Actual next-edge CSV epoch differs')
            samples.append(pending); pending = None
        if before.get(decl[original.CORE + '.csr_commit_commit_ex']['code']) == '1':
            bits = before.get(decl[original.CSR + '.csr_addr_i']['code'], 'x')
            require(set(bits) <= {'0', '1'}, 'Unknown epoch CSR address')
            if int(bits, 2) in (0x180, 0x141):
                pending = dict(commit_edge_time=time, pre_counter=counter(before, decl), post_counter=counter(after, decl))
    require(pending is None and len(samples) == 30, 'Incomplete exact-next-edge epoch samples')
    return samples


def evidence():
    proof = source_contract()
    pre = life.read_bound(original.runner.PRE / 'preflight-manifest.json', original.runner.PRE_SEAL)
    rows = original.primitive.parse_rows(packed.RUN / 'commit_trace.csv')
    reference = original.runner.reference(pre)
    expected = original.csr_expected(reference, rows, original.runner.source_contract()[0]['ops'])
    # This is the native-owner component only, not a replacement for complete terminal qualification.
    owners = wave_audit(packed.HOLD / 'csr-owner.vcd', expected)
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_csr_satp_sepc_cycle_adapter.py'),
             Path(packed.__file__).with_name('test_csr_satp_sepc_packed_adapter.py'),
             packed.RUN / 'commit_trace.csv', packed.HOLD / 'csr-owner.vcd', packed.HOLD / 'failure.json',
             packed.RUN / 'manifest.json', original.runner.PRE / 'spike.trace',
             original.runner.PRE / 'preflight-manifest.json']
    proof['pins'].update({str(path): life.digest(path) for path in paths})
    return dict(status='SOURCE_BOUND_PACKED_AND_RVFI_EPOCH_OWNER_COMPONENT_VERIFIED_NOT_QUALIFICATION',
        source_contract=proof, owners=owners, measured_epochs=measured_epochs(packed.HOLD / 'csr-owner.vcd', expected),
        qualification_performed=False, admission_performed=False,
        original_HOLD_preserved=True, simulation_performed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = evidence(); life.save(args.output, result)
    print(json.dumps(dict(status=result['status'], output=str(args.output), sha256=life.digest(args.output))))
