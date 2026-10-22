"""Complete standard-RVV differential plus scoped RVC memory audit; no admission."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import run_operand_index_snapshot_simulation as old
import scoped_rv64c_memory as rv64c
from inventory_operand_debug import Design

life, require = old.life, old.require
RUN = life.OUT/'operand-index-snapshot-old-image-parent-20261006-01'
RUN_SEAL = 'ef058d9caa19267d2594ecd0a9503caca4716c5dffca9945c9ec3e96b2dd87c5'
BUILD = life.OUT/'repaired-aligned-build-20260930-01'
GPR_SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands.gen_asic_regfile.i_ariane_regfile'
MASK64 = (1<<64)-1


def source_contract(pins):
    path = BUILD/'build-source-pins.json'
    require(str(path) in pins,'Missing original build source inventory pin')
    sources = life.read_bound(path,pins[str(path)])
    anchors = {
        'hardware/deps/cva6/core/compressed_decoder.sv':
            ('riscv::OpcodeC0Lw:','riscv::OpcodeC0Ld:','riscv::OpcodeC0Sw:',
             'riscv::OpcodeC0Sd:','riscv::OpcodeC2Lwsp:','riscv::OpcodeC2Ldsp:',
             'riscv::OpcodeC2Swsp:','riscv::OpcodeC2Sdsp:','CVA6Cfg.IS_XLEN64'),
        'hardware/deps/cva6/core/ariane_regfile_ff.sv':
            ("if (~rst_ni) begin mem <= '{default: '0};",),
        'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv':
            ('localparam CVA6ConfigXlen = 64;',"FpgaEn: bit'(0)"),
    }
    for relative,tokens in anchors.items():
        source = life.ROOT/relative
        pins = life.merge_pins(pins,{str(source):sources[str(source)]})
        require(life.digest(source) == sources[str(source)],'Frozen decoder/reset source drift')
        text = ''.join(source.read_text().split())
        require(all(''.join(t.split()) in text for t in tokens),'Missing decoder/reset anchor')
    require(sources[str(life.ROOT/'hardware/deps/cva6/core/compressed_decoder.sv')] ==
            'ad4938c65987a636f127b692c4a00f5116948d11153dba740fe01006c2de67fb',
            'Wrong frozen decompressor')
    design = Design(BUILD/'sim/simv.vdb')
    require(design.hierarchy[GPR_SCOPE].get('chksum') == '1875497202' and
            design.source(GPR_SCOPE)['resolved_path'] ==
            str(life.ROOT/'hardware/deps/cva6/core/ariane_regfile_ff.sv') and
            not any(s.endswith('.i_ariane_regfile_fpga') for s in design.hierarchy),
            'Wrong elaborated integer register file/reset selection')
    return pins,dict(status='FROZEN_RV64C_WIRING_AND_ELABORATED_FF_ZERO_RESET_BOUND',
                     GPR_scope=GPR_SCOPE,GPR_checksum='1875497202',initial_GPRs='all zero',XLEN=64)


def compressed_memory(rows, commits, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    prefix = []
    for c in commits:
        if not prefix and c.pc != 0x80000000:
            continue
        prefix.append(c)
        if (symbols['tohost'],1) in c.memory_accesses:
            break
    require(prefix and prefix[-1].memory_accesses == ((symbols['tohost'],1),) and
            len(prefix) == len(retired),'Incomplete scalar/reference terminal alignment')
    registers = {r:0 for r in range(32)}
    records, normalized, counts = [], [], Counter()
    for order,(row,c) in enumerate(zip(retired,prefix)):
        require(int(row['order']) == order and int(row['pc'],16) == c.pc and
                int(row['insn'],16) == c.instruction and int(row['trap']) == 0,
                'Compressed audit PC/opcode/order/trap alignment mismatch')
        clone = dict(row)
        readmask,writemask = int(row['mem_rmask'],16),int(row['mem_wmask'],16)
        if c.instruction & 3 != 3:
            access = rv64c.decode(c.instruction)
            if access is None:
                require(not c.memory_accesses and readmask == writemask == 0,
                        'Unsupported compressed memory instruction/side effect')
            else:
                size,reg = access['size'],access['register']
                address = (registers[access['base']]+access['offset'])&MASK64
                require(address % size == 0,'Misaligned compressed memory address')
                mask = ((1<<size)-1)<<(address&7)
                require(int(row['mem_addr'],16) == address,'Compressed memory address mismatch')
                if access['kind'] == 'write':
                    expected = registers[reg]&((1<<(8*size))-1)
                    require(c.memory_accesses == ((address,expected),) and not c.gpr_writes,
                            'Independent Spike compressed store semantics differ')
                    require(readmask == 0 and writemask == mask and
                            int(row['mem_wdata'],16)&((1<<(8*size))-1) == expected and int(row['rd']) == 0,
                            'Compressed store mask/data/rd mismatch')
                else:
                    require(c.memory_accesses == ((address,None),) and set(c.gpr_writes) == {reg},
                            'Independent Spike compressed load semantics differ')
                    expected = c.gpr_writes[reg]
                    if size == 4:
                        low = expected&0xffffffff
                        require(expected == (low | (0xffffffff00000000 if low&0x80000000 else 0)),
                                'Reference C.LW sign extension differs')
                    require(readmask == mask and writemask == 0 and int(row['rd']) == reg and
                            int(row['rd_wdata'],16) == expected,'Compressed load mask/rd/data mismatch')
                counts[access['kind']] += 1
                records.append(dict(order=order,pc=hex(c.pc),instruction=hex(c.instruction),
                    decode=access,address=hex(address),mask=hex(mask),expected_data=hex(expected),
                    expected_from='Spike prior GPRs/reference commit, never DUT feedback'))
                # Only signature store-width decoding uses this canonical expansion.
                # Differential alignment above always uses the original C opcode.
                clone['insn'] = hex(access['expanded'])
        normalized.append(clone)
        for register,value in c.gpr_writes.items():
            require(0 <= register < 32 and 0 <= value <= MASK64,'Invalid reference GPR state')
            if register:
                registers[register] = value
        registers[0] = 0
    return dict(status='ALL_COMPRESSED_INTEGER_MEMORY_EXACT_NO_SKIP',matched_retirements=len(prefix),
        compressed_loads=counts['read'],compressed_stores=counts['write'],
        compressed_memory_accesses=len(records),skipped_memory_events=0,records=records),normalized


def evaluate():
    manifest = life.read_bound(RUN/'manifest.json',RUN_SEAL)
    require(life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL) == manifest and
            manifest['command'] == old.command(RUN) and manifest['timeout_s'] == 1200 and
            manifest['old_image_files_checked'] == 66,'Exact parent run/prepared identity differs')
    pre = life.read_bound(old.PRE/'preflight-manifest.json',old.PRE_SEAL)
    old.validate(pre)
    require(pre == manifest['preflight'],'Executed preflight differs')
    state = json.loads((RUN/'simulation-status.json').read_bytes())
    require(state == dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,case=old.NAME,
        coverage_admitted=False,admission_performed=False),'Failed/nonterminal run')
    pins = dict(manifest['pins'])
    files = [RUN/'manifest.json',RUN.with_name(RUN.name+'.prepared.json'),RUN/'simulation-status.json',
             RUN/'console.log',RUN/'run.vcs.log',RUN/'commit_trace.csv',RUN/'vector_trace.csv',
             Path(__file__).resolve(),Path(__file__).with_name('test_check_operand_index_snapshot_offline_v2.py'),
             Path(rv64c.__file__).resolve(),Path(rv64c.__file__).with_name('test_scoped_rv64c_memory.py')]
    vdb = RUN/'code.vdb'
    members = sorted(p for p in vdb.rglob('*') if p.is_file())
    require(members and not any(p.is_symlink() for p in vdb.rglob('*')),'Missing/aliased VDB')
    files += members
    pins = life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    pins,proof = source_contract(pins)
    life.check(pins)
    reference = old.reference_contract(pre)
    require(reference == manifest['reference_contract'],'Reference population drift')
    with (RUN/'commit_trace.csv').open() as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == old.FIELDS,'Wrong commit schema')
        rows = list(reader)
    require(all(set(r) == set(old.FIELDS) and all(v is not None and v != '' for v in r.values()) and
                r['event'] in ('retire','arch_start','cvx_req','cvx_resp','uop_alloc','uop_done') for r in rows),
            'Malformed/unknown commit event')
    commits = old.software.s.parse_spike_commits(old.PRE/'spike.trace')
    compressed,normalized = compressed_memory(rows,commits,pre['symbols'])
    old.exact(compressed,dict(matched_retirements=7395,compressed_loads=324,compressed_stores=321,
        compressed_memory_accesses=645,skipped_memory_events=0),'Exact sealed RVC memory population differs')
    architecture = old.signature(normalized,pre['symbols'])
    scalar = old.spike_trace.compare_commit_prefix(old.PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    old.validate_scalar(scalar,reference)
    vector = old.vector_commit.compare_vector_commits(old.PRE/'spike.trace',RUN/'commit_trace.csv',
        RUN/'vector_trace.csv',0x80000000)
    old.validate_vector(vector,reference)
    require(not old.contract.check_contract_log(RUN/'run.vcs.log'),'DUT contract/log diagnostic')
    require((RUN/'console.log').read_text().count('Core Test *** SUCCESS ***') ==
            (RUN/'run.vcs.log').read_text().count('Core Test *** SUCCESS ***') == 1,
            'Missing/duplicate SUCCESS')
    summaries = [old.contract.parse_contract_summary(l) for l in (RUN/'run.vcs.log').read_text().splitlines()
                 if '[ARA_CONTRACT]' in l]
    require(len(summaries) == 1 and summaries[0] is not None and summaries[0]['requests'] ==
            summaries[0]['responses'] == sum(r['event'] == 'cvx_req' for r in rows) ==
            sum(r['event'] == 'cvx_resp' for r in rows) == sum(r['event'] == 'arch_start' for r in rows) and
            summaries[0]['exceptions'] == summaries[0]['mmu_request_cycles'] == 0,
            'Incomplete exception-free native interface contract')
    require(members == sorted(p for p in vdb.rglob('*') if p.is_file()),'VDB membership drift')
    life.check(pins)
    return pins,dict(status='FULL_SCALAR_RVC_VECTOR_CSR_SIGNATURE_QUALIFIED_NOT_ADMITTED',
        run=str(RUN),run_seal=RUN_SEAL,full_scalar_differential_qualified=True,
        all_scalar_memory_differential_qualified=True,scalar_uncompressed_memory_accesses=726,
        scalar_compressed_memory_accesses=645,total_scalar_memory_accesses=1371,
        skipped_scalar_memory=0,target_bitmap_checked=False,coverage_admitted=False,
        simulations_started=False,rtl_changed=False),{
        'scalar-comparison.json':scalar,'compressed-memory-audit.json':compressed,
        'vector-comparison.json':vector,'architecture-audit.json':architecture,
        'source-contract.json':proof,'contract-summary.json':summaries[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output = parser.parse_args().output.absolute()
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(),'Fresh direct output required')
    output.mkdir()
    try:
        pins,state,artifacts = evaluate()
        for name,value in dict(artifacts,**{'status.json':state}).items():
            life.save(output/name,value)
        life.check(pins)
        life.save(output/'qualification-seal.json',dict(input_pins=pins,
            output_pins={str(p):life.digest(p) for p in output.iterdir()},result=state,
            coverage_admitted=False,new_RTL_signoff=False))
        print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification-seal.json'),result=state)))
    except Exception as error:
        life.save(output/'failure.json',dict(status='OFFLINE_QUALIFICATION_FAILED_NOT_ADMITTED',reason=str(error)))
        raise


if __name__ == '__main__':
    main()
