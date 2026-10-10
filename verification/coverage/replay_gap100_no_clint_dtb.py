"""Same ELF, native DTB minus exactly one CLINT node; strict replay, no RTL/admission."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

import replay_gap100_platform_matched as shared

runtime, runner, software = shared.runtime, shared.runner, shared.software
require, save, OUT = shared.require, shared.save, shared.OUT
DTC, FDTPUT = Path('/usr/bin/dtc'), Path('/usr/bin/fdtput')


def fdt_nodes(blob):
    require(len(blob) >= 40, 'Short FDT')
    h = struct.unpack_from('>10I', blob)
    magic, total, structure, strings, reserve, version, compat, cpu, slen, tlen = h
    require(magic == 0xd00dfeed and total == len(blob) and version == 17 and compat <= 17 and
            structure + tlen <= total and strings + slen <= total, 'Malformed FDT header')
    text, end, offset, stack, nodes = blob[strings:strings + slen], structure + tlen, structure, [], {}
    while offset + 4 <= end:
        token = struct.unpack_from('>I', blob, offset)[0]
        offset += 4
        if token == 1:
            stop = blob.find(b'\0', offset, end)
            require(stop >= offset, 'Unterminated FDT node')
            name = blob[offset:stop].decode('ascii')
            require('/' not in name and (stack or name == ''), 'Invalid FDT node name')
            stack.append(name)
            path = '/' + '/'.join(stack[1:])
            require(path not in nodes, 'Duplicate FDT node')
            nodes[path] = {}
            offset = (stop + 4) & ~3
        elif token == 2:
            require(stack, 'Unbalanced FDT')
            stack.pop()
        elif token == 3:
            require(stack and offset + 8 <= end, 'Invalid FDT property')
            length, nameoff = struct.unpack_from('>II', blob, offset)
            offset += 8
            require(offset + length <= end and nameoff < len(text) and b'\0' in text[nameoff:], 'Bad FDT property bounds')
            name = text[nameoff:text.index(b'\0', nameoff)].decode('ascii')
            props = nodes['/' + '/'.join(stack[1:])]
            require(name not in props, 'Duplicate FDT property')
            props[name] = blob[offset:offset + length].hex()
            offset = (offset + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            require(not stack, 'Incomplete FDT tree')
            return nodes
        else:
            raise ValueError('Unknown FDT token')
    raise ValueError('No FDT terminal')


def clint_path(nodes):
    paths = [path for path, props in nodes.items() if 'compatible' in props and
             set(bytes.fromhex(props['compatible']).split(b'\0')) & {b'riscv,clint0', b'sifive,clint0'}]
    require(len(paths) == 1, 'Not exactly one native CLINT node')
    return paths[0]


def validate_change(before, after, path):
    removed = {name for name in before if name == path or name.startswith(path + '/')}
    require(removed == {path}, 'Unexpected CLINT child topology')
    require(after == {name: props for name, props in before.items() if name not in removed},
            'DTB changes beyond exact CLINT node')


def command(out):
    return [str(software.shared.SPIKE), '--isa=' + software.SPIKE_ISA, '--priv=msu', '--pmpregions=0',
            '--dtb=' + str(out / 'no-clint.dtb'), '-l', '--log-commits', str(runner.PRE / 'input.elf')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    prefile = runner.PRE / 'preflight-manifest.json'
    pre = runner.life.read_bound(prefile, runner.PRE_SEAL)
    runner.validate(pre)
    manifest = runner.life.read_bound(runtime.RUN / 'manifest.json', runtime.RUN_SEAL)
    require(manifest['preflight'] == pre and manifest['command'] == runner.command(runtime.RUN), 'Original run identity differs')
    pins = runner.life.merge_pins(manifest['pins'], {str(prefile): runner.PRE_SEAL,
                                                  str(runtime.RUN / 'manifest.json'): runtime.RUN_SEAL})
    paths = [runtime.RUN / name for name in ('simulation-status.json', 'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log')]
    paths += [DTC, FDTPUT, Path(__file__).resolve(), Path(__file__).with_name('test_replay_gap100_no_clint_dtb.py'),
              Path(shared.__file__).resolve(), Path(runtime.__file__).resolve(), Path(shared.differences.__file__).resolve()]
    paths += [shared.SPIKE_SOURCE / name for name in ('riscv/sim.cc', 'riscv/processor.cc', 'riscv/clint.cc',
                                                  'riscv/csr_init.cc', 'spike_main/spike.cc')]
    for path in paths:
        pins = runner.life.merge_pins(pins, {str(path): runner.life.digest(path)})
    runner.life.check(pins)
    status = json.loads((runtime.RUN / 'simulation-status.json').read_bytes())
    require(status.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and status.get('returncode') == 0, 'RTL run not terminal-successful')
    dut = runtime.retired_commits(runtime.commit_rows(runtime.RUN / 'commit_trace.csv'))
    dut_scope = shared.state_scope(dut)
    out.mkdir()
    commands = []
    try:
        dump = [str(software.shared.SPIKE), '--isa=' + software.SPIKE_ISA, '--priv=msu', '--pmpregions=0',
                '--dump-dts', str(runner.PRE / 'input.elf')]
        commands.append(dump)
        with (out / 'native.dts').open('x') as dts, (out / 'configuration.log').open('x') as log:
            subprocess.run(dump, stdout=dts, stderr=log, timeout=30, check=True)
            compile_cmd = [str(DTC), '-I', 'dts', '-O', 'dtb', '-o', str(out / 'native.dtb'), str(out / 'native.dts')]
            commands.append(compile_cmd)
            subprocess.run(compile_cmd, stdout=log, stderr=log, timeout=30, check=True)
            original = (out / 'native.dtb').read_bytes()
            nodes = fdt_nodes(original)
            path = clint_path(nodes)
            # This fresh binary is a generated reference configuration, not source.
            (out / 'no-clint.dtb').write_bytes(original)
            remove = [str(FDTPUT), '-r', str(out / 'no-clint.dtb'), path]
            commands.append(remove)
            subprocess.run(remove, stdout=log, stderr=log, timeout=30, check=True)
        changed = fdt_nodes((out / 'no-clint.dtb').read_bytes())
        validate_change(nodes, changed, path)
        save(out / 'configuration-proof.json', dict(status='NATIVE_DTB_EXACT_CLINT_NODE_REMOVED',
             removed_node=path, before_nodes=nodes, after_nodes=changed,
             cpu_and_mmu_properties_unchanged=True, reset_ROM_enabled=True,
             ELF_unchanged_sha256=runner.ELF_SEAL, original_preflight=str(prefile),
             original_preflight_seal=runner.PRE_SEAL, dut_scope=dut_scope,
             source_references_not_binary_build_receipt=True, RTL_reexecuted=False))
        commands.append(command(out))
        save(out / 'commands.json', commands)
        with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
            subprocess.run(command(out), stdout=stdout, stderr=trace, timeout=120, check=True)
        commits = software.shared.parse_spike_commits(out / 'spike.trace')
        validation = software.validate(commits, pre['symbols'])
        validation['trap_distribution'] = software.trap_distribution((out / 'spike.trace').read_text())
        require(validation == pre['spike_validation'], 'Independent225/23trap oracle changed')
        clipped = shared.from_entry_to_terminal(commits, pre['symbols'])
        require(shared.state_scope(clipped) == dut_scope, 'SATP/MIE/MIP configuration trace differs')
        full_diff = shared.differences.differences(clipped, dut)
        save(out / 'all-instruction-differences.json', full_diff)
        scalar = runtime.common.compare_commit_prefix(out / 'spike.trace', runtime.RUN / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        save(out / 'scalar-comparison.json', scalar)
        require(not full_diff and runtime.scalar_qualified(scalar, runtime.commit_rows(runtime.RUN / 'commit_trace.csv')),
                'Full scalar/GPR/memory comparison not qualified')
        diagnostic = runtime.runtime(runtime.RUN, dict(pre, input_spike_trace=str(out / 'spike.trace')), scalar)
        save(out / 'runtime-diagnostic.json', diagnostic)
        save(out / 'spike-validation.json', validation)
        runner.life.check(pins)
        pins = runner.life.merge_pins(pins, {str(p): runner.life.digest(p) for p in out.iterdir() if p.is_file()})
        runner.life.check(pins)
        save(out / 'reference-result.json', dict(status='GAP100_NO_CLINT_DTB_FULL_SCALAR_DIAGNOSTIC_NOT_ADMISSION',
             original_preflight=str(prefile), original_preflight_seal=runner.PRE_SEAL,
             input_elf=str(runner.PRE / 'input.elf'), input_elf_sha256=runner.ELF_SEAL,
             original_RTL_run=str(runtime.RUN), new_spike_trace=str(out / 'spike.trace'),
             scalar=scalar, complete_nontrap_instructions=len(dut), full_instruction_differences=full_diff,
             independent_spike_oracle=validation, scalar_comparison_qualified=True,
             normalization_performed=False, coverage_admitted=False, RTL_reexecuted=False, pins=pins,
             limitation='Fresh713 admission chain and complete independent trap accounting remain separate gates.'))
        print(json.dumps(dict(output=str(out), seal=runner.life.digest(out / 'reference-result.json'), scalar=scalar['status'])))
    except Exception as error:
        save(out / 'failure.json', dict(status='GAP100_NO_CLINT_DTB_REFERENCE_FAILED_NOT_ADMITTED', reason=str(error), commands=commands))
        raise


if __name__ == '__main__':
    main()
