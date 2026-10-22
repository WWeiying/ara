"""Successor to initial inventory: case-specific native evidence, no mandatory ISA rebuild."""
import csv
import json
from pathlib import Path

import audit_akv_budget_qualification_gaps as audit


def descriptor_architecture(rows, layout, core):
    require = audit.old.require
    starts, pending, rejected, allocations = {}, {}, [], []
    for row in rows:
        event, seq, tid = row['event'],int(row['order']),int(row['trans_id'])
        if event == 'arch_start':
            require(seq not in starts, 'Duplicate architecture sequence')
            starts[seq] = int(row['insn'],16)
            require(tid not in pending,'Live transaction reused')
            pending[tid] = seq
        elif event == 'cvx_resp':
            require(tid in pending,'Orphan response')
            owner = pending.pop(tid)
            if int(row['trap']): rejected.append(owner)
        elif event == 'uop_alloc': allocations.append(seq)
    require(not pending and len(rejected) == 23,
            'Incomplete rejection')
    require([starts[seq] for seq in rejected] == audit.old.DESCRIPTOR_WORDS[:23], 'Rejected encodings differ')
    blob = (audit.RUNS[audit.old.DESCRIPTOR]/'input.elf').read_bytes()
    _,code = audit.old.elf_layout(blob,2097152)
    symbols = layout['symbols']
    handler = symbols['mtvec_handler']
    retires = [r for r in rows if r['event'] == 'retire']
    require([int(r['order']) for r in retires] == list(range(len(retires))), 'Incomplete scalar order')
    csr_reads = {address:[] for address in (0x341,0x342,0x343)}
    for r in retires:
        pc,word = int(r['pc'],16),int(r['insn'],16)
        size = 4 if word&3 == 3 else 2
        require(int.from_bytes(code(pc,size),'little') == word,'Retirement not exact ELF')
        if handler['value'] <= pc < handler['value']+handler['size']:
            require(int(r['rd']) in (0,2,5,6),'Unexpected handler GPR side effect')
            if word&127 == 0x73 and word>>12&7:
                address,fn,rs = word>>20,word>>12&7,word>>15&31
                writes = fn in (1,5) or fn in (2,3,6,7) and rs != 0
                require(not writes or address == 0x341,'Unexpected handler CSR mutation')
                if address in csr_reads and fn == 2 and rs == 0:
                    csr_reads[address].append(int(r['rd_wdata'],16))
    import re
    exceptions = re.findall(r'Exception @[^\n]*PC: ([0-9a-f]+), Cause: ([^,\n]+),\s*\n\s*tval: ([0-9a-f]+)',core)
    require(len(exceptions) == 23 and csr_reads[0x341] == [int(e[0],16) for e in exceptions] and
            csr_reads[0x342] == [2]*23 and csr_reads[0x343] == [int(e[2],16) for e in exceptions],
            'Actual trap CSR reads differ from precise tracer')
    return dict(status='DESCRIPTOR_NATIVE_ARCHITECTURAL_SUBCONTRACT_PASS_NOT_ADMISSION',
        rejected_arch_sequences=rejected,
        rejected_backend_allocation_owners=sorted(set(rejected)&set(allocations)),
        rejection_semantics='AKV engine validation after backend allocation; not RVV front-end illegal. No zero-backend gate imposed.',
        precise_trap_CSR_reads=69,handler_protected_GPRs=True,handler_only_CSR_write='mepc',
        exact_ELF_retirements=len(retires),trace_pc_source='retire.pc and core exception PC; never arch_start.pc',
        full_scalar_semantics_independent=False,
        unobserved_CSRs=['vl','vtype','vstart','fflags command-boundary readbacks absent'],
        unobserved_scope='No claim about all32 VRF or native vector write-port bytes')


def main():
    source = audit.OUT/'akv-budget-pass-qualification-gap-review-20261006-01.json'
    out = audit.OUT/'akv-budget-pass-native-evidence-review-20261006-02.json'
    audit.old.require(not out.exists(),'Fresh successor report required')
    old = json.loads(source.read_text())
    run = audit.RUNS[audit.old.DESCRIPTOR]
    with (run/'commit_trace.csv').open() as stream: rows = list(csv.DictReader(stream))
    oracle = json.loads((run/'oracle-result.json').read_text())
    arch = descriptor_architecture(rows,oracle['elf_layout'],(run/'trace_hart_0.log').read_text())
    gaps = {
        audit.old.DESCRIPTOR: ['26 complete512-byte group readbacks and69 actual trap CSR reads independently checked; rejected AKV commands do allocate backend validation work.',
            'No command-boundary vl/vtype/vstart/fflags CSR reads in actual CSV. Do not assert whole-CSR preservation from PASS.',
            'Original generic trace validates lifecycle, not ordinary ALU/load/store result semantics. No standalone scalar independent comparison artifact found in this run.',
            'No vector port CSV; architectural v8..v11 reconstruction is available and can be scoped instead of demanding an unavailable full32VRF observation.'],
        audit.old.SKEW: ['Existing gap46 trace_audit checks24 exact real fflags/vstart readbacks, all12 custom outcomes/ELF PCs; PERF parser bare translation fix has frozen source proof.',
            'Existing native_runtime checks compiled line/branch bits only; it is coverage binding, not independent architectural data qualification.',
            '3237 software checks exist, but independent12-phase got640-byte/guard reconstruction has not yet been produced; source/golden formulas can be reused.',
            'No vl/vtype boundary reads or scalar semantic comparison artifact in this run; do not relabel validate_trace as no-skip full scalar match.']}
    pins = dict(old['pins'])
    for path in (source,Path(__file__).resolve(),Path(audit.old.skew.__file__).resolve()):
        pins[str(path)] = audit.digest(path)
    for p,h in pins.items(): audit.old.require(audit.digest(p) == h,'Evidence pin drift')
    value = dict(status='CASE_SCOPED_NATIVE_REVIEW_HOLD_NOT_ADMITTED',pins=pins,
        supersedes_initial_mandatory_interpreter_and_zero_backend_recommendations=True,
        descriptor_native_architecture=arch,descriptor_group_readback=old['cases'][0]['independent_destination_readback'],
        actual_gaps=gaps, preferred_case=audit.old.DESCRIPTOR,
        shortest_next_step=['Reuse original exact command/ELF/image66/terminal/full software oracle and existing native protocol qualifier.',
            'Combine newly checked26 destination group frames with precise69CSR trap reads and actual AKV backend validation lifecycle; parent reviews explicitly bounded architecture scope.',
            'Search/reuse ordinary scalar independent evidence first. If absent, implement only an independently checked executed scalar/CSR contract needed by this ELF, with no skips or falseSpike claims; not a new generalized per-ELF interpreter requirement.',
            'Absent boundary CSR reads stay absent; scope approval or frozen source preservation proof must be explicit, never fabricate observations.',
            'After architectural qualification, fresh latest-base raw positive gain/dedup remains a separate candidate step.'],
        whole_native_vector_qualified=False,full_scalar_independent_qualified=False,
        native_Spike_comparison=False,coverage_admitted=False,rtl_changed=False,simulations_started=False)
    with out.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(output=str(out),seal=audit.digest(out),pins=len(pins),architecture=arch)))


if __name__ == '__main__': main()
