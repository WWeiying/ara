"""Fresh --disable-dtb Spike reference for frozen GAP100 ELF; no RTL or admission."""
import argparse
import json
from pathlib import Path
import subprocess

import audit_gap100_scalar_differences as differences
import check_gap100_runtime as runtime

runner, software = runtime.runner, runtime.software
require, save, OUT = runtime.require, runtime.save, runtime.OUT
SPIKE_SOURCE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart')


def command(output):
    return [str(software.shared.SPIKE), '--isa=' + software.SPIKE_ISA, '--priv=msu', '--pmpregions=0',
            '--disable-dtb', '-l', '--log-commits', str(runner.PRE / 'input.elf')]


def state_scope(commits):
    regs, satp, mie = {0: 0}, 0, 0
    writes, reads = [], []
    for index, c in enumerate(commits):
        for address, value in c.memory_accesses:
            require(0x80000000 <= address < 0xc0000000, 'MMIO/outside DRAM invalidates no-DTB scope')
        insn = c.instruction
        if insn & 127 == 0x73 and insn >> 20 in (0x180, 0x304, 0x344):
            csr, f, rs, rd = insn >> 20, (insn >> 12) & 7, (insn >> 15) & 31, (insn >> 7) & 31
            require(f in (1, 2, 3, 5, 6, 7), 'Invalid CSR operation')
            operand = rs if f >= 5 else regs.get(rs)
            require(operand is not None, 'Unknown CSR operand')
            if rd:
                require(rd in c.gpr_writes, 'Missing CSR readback')
                value = c.gpr_writes[rd]
                if csr == 0x180:
                    require(value == 0, 'SATP not Bare')
                if csr == 0x304:
                    require(value == mie and value in (0, 2), 'MIE readback differs')
                if csr == 0x344:
                    require(value in (0, 2), 'Unexpected MTIP/external pending bit')
                reads.append(dict(index=index, pc=hex(c.pc), csr=hex(csr), value=value))
            if f in (1, 5) or rs != 0:
                old = satp if csr == 0x180 else mie if csr == 0x304 else None
                if csr != 0x344:
                    new = operand if f in (1, 5) else old | operand if f in (2, 6) else old & ~operand
                    if csr == 0x180:
                        require(new == 0, 'Non-Bare SATP write')
                        satp = new
                    else:
                        require(new in (0, 2), 'MTIE/other interrupt source enabled')
                        mie = new
                    writes.append(dict(index=index, pc=hex(c.pc), csr=hex(csr), value=new))
        regs.update(c.gpr_writes)
    require(sum(r['csr'] == '0x180' for r in reads) == 1 and
            sum(r['csr'] == '0x180' for r in writes) == 2 and
            sum(r['csr'] == '0x304' for r in writes) == 33, 'Missing/reordered configuration population')
    return dict(status='GAP100_BARE_PMP0_NO_EXTERNAL_IRQ_CASE_SCOPE', reads=reads, writes=writes,
                satp_always_bare=True, mie_mtie_always_zero=True, mip_mtip_observed_zero=True,
                memory_accesses_in_dram_only=True, generic_mmu_equivalence_claimed=False)


def from_entry_to_terminal(commits, symbols):
    start = next(i for i, c in enumerate(commits) if c.pc == 0x80000000)
    commits = commits[start:]
    ends = [i for i, c in enumerate(commits) if (symbols['tohost'], 1) in c.memory_accesses]
    require(len(ends) == 1, 'Ambiguous successful terminal')
    return commits[:ends[0] + 1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct reference output required')
    prefile = runner.PRE / 'preflight-manifest.json'
    pre = runner.life.read_bound(prefile, runner.PRE_SEAL)
    runner.validate(pre)
    manifest = runner.life.read_bound(runtime.RUN / 'manifest.json', runtime.RUN_SEAL)
    require(manifest['preflight'] == pre and manifest['command'] == runner.command(runtime.RUN),
            'Original simulation/ELF identity differs')
    pins = runner.life.merge_pins(manifest['pins'], {str(prefile): runner.PRE_SEAL,
                                                   str(runtime.RUN / 'manifest.json'): runtime.RUN_SEAL})
    paths = [runtime.RUN / name for name in ('simulation-status.json', 'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log')]
    paths += [Path(__file__).resolve(), Path(__file__).with_name('test_replay_gap100_platform_matched.py'),
              Path(runtime.__file__).resolve(), Path(differences.__file__).resolve()]
    source_paths = [SPIKE_SOURCE / name for name in ('riscv/sim.cc', 'riscv/processor.cc', 'riscv/csr_init.cc',
                                                   'riscv/csrs.cc', 'spike_main/spike.cc')]
    paths += source_paths
    for path in paths:
        pins = runner.life.merge_pins(pins, {str(path): runner.life.digest(path)})
    runner.life.check(pins)
    state = json.loads((runtime.RUN / 'simulation-status.json').read_bytes())
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and state.get('returncode') == 0,
            'Original RTL run not terminal-successful')
    sim = (SPIKE_SOURCE / 'riscv/sim.cc').read_text()
    require('if (!dtb_enabled)' in sim and sim.index('if (!dtb_enabled)') < sim.index('device_factories =') and
            'return;\n  } // otherwise, generate the procs by parsing the DTS' in sim,
            'No-DTB peripheral skip path differs')
    processor = (SPIKE_SOURCE / 'riscv/processor.cc').read_text()
    require('set_pmp_num(cfg->pmpregions);' in processor and 'isa(isa_str, priv_str)' in processor and
            'set_mmu_capability(IMPL_MMU_SV57);' in processor, 'CPU construction assumptions differ')
    rows = runtime.commit_rows(runtime.RUN / 'commit_trace.csv')
    dut = runtime.retired_commits(rows)
    dut_scope = state_scope(dut)
    out.mkdir()
    save(out / 'spike-command.json', command(out))
    save(out / 'configuration-proof.json', dict(option='--disable-dtb', unchanged_elf_sha256=runner.ELF_SEAL,
        original_preflight=str(prefile), original_preflight_seal=runner.PRE_SEAL, pmp_regions=0, privilege='msu',
        isa=software.SPIKE_ISA, original_RTL_run=str(runtime.RUN), source_reference_pins={str(p): pins[str(p)] for p in source_paths},
        scope='Only GAP100: SATP always Bare, no MMIO, software SSIP through CSR.',
        mmu_difference='No-DTB CPU defaults to SV57 capability; not claimed equivalent outside Bare.',
        source_references_are_not_a_binary_build_receipt=True, dut_scope=dut_scope,
        RTL_reexecuted=False, historical_receipts_modified=False, coverage_admitted=False))
    try:
        with (out / 'spike.stdout').open('x') as stdout, (out / 'spike.trace').open('x') as trace:
            subprocess.run(command(out), stdout=stdout, stderr=trace, timeout=120, check=True)
        commits = software.shared.parse_spike_commits(out / 'spike.trace')
        validation = software.validate(commits, pre['symbols'])
        validation['trap_distribution'] = software.trap_distribution((out / 'spike.trace').read_text())
        require(validation == pre['spike_validation'], 'Original independent oracle contract differs')
        clipped = from_entry_to_terminal(commits, pre['symbols'])
        reference_scope = state_scope(clipped)
        require(reference_scope == dut_scope, 'Configuration trace differs between new reference and DUT')
        full_differences = differences.differences(clipped, dut)
        require(not full_differences, 'Unnormalized instruction/GPR/memory difference remains')
        scalar = runtime.common.compare_commit_prefix(out / 'spike.trace', runtime.RUN / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        save(out / 'scalar-comparison.json', scalar)
        require(runtime.scalar_qualified(scalar, rows), 'Not a full terminal scalar match')
        context = dict(pre, input_spike_trace=str(out / 'spike.trace'))
        diagnostic = runtime.runtime(runtime.RUN, context, scalar)
        runner.life.check(pins)
        save(out / 'runtime-diagnostic.json', diagnostic)
        save(out / 'spike-validation.json', validation)
        pins = runner.life.merge_pins(pins, {str(p): runner.life.digest(p) for p in out.iterdir() if p.is_file()})
        runner.life.check(pins)
        result = dict(status='GAP100_PLATFORM_MATCHED_REFERENCE_FULL_SCALAR_DIAGNOSTIC_NOT_ADMISSION',
            original_preflight=str(prefile), original_preflight_seal=runner.PRE_SEAL,
            input_elf=str(runner.PRE / 'input.elf'), new_reference=str(out / 'spike.trace'),
            reference_command=command(out), reference_scope=reference_scope,
            independent_spike_oracle=validation, original_RTL_run=str(runtime.RUN),
            scalar_comparison=scalar, full_instruction_gpr_memory_differences=[],
            normalization_performed=False, scalar_comparison_qualified=True,
            aggregate_admission_performed=False, coverage_admitted=False, RTL_reexecuted=False, pins=pins,
            limitation='Fresh713 chain/bitmap union and complete independent trap accounting remain separate admission gates.')
        save(out / 'reference-result.json', result)
        print(json.dumps(dict(output=str(out), seal=runner.life.digest(out / 'reference-result.json'),
                             scalar=scalar['status'], coverage_admitted=False)))
    except Exception as error:
        save(out / 'failure.json', dict(status='GAP100_PLATFORM_REFERENCE_FAILED_NOT_ADMITTED', reason=str(error)))
        raise


if __name__ == '__main__':
    main()
