"""Sealed standard-RVV snapshot restart: prepare/run/audit, never admission."""
import argparse
import csv
import json
from pathlib import Path
import struct
import subprocess
import sys

import build_operand_index_snapshot_preflight as software
import bind_operand_index_snapshot_branch_targets as binding
import run_gap95_simulation as life

sys.path.insert(0,str(life.ROOT/'verification'))
from ara_verify import spike_trace, vector_commit, contract

PRE = binding.PRE
PRE_SEAL = binding.SEAL
TARGETS = life.OUT/'operand-index-snapshot-targets-724-20261006-01.json'
TARGET_SEAL = 'ca9484a506f243b8041b40e639178ade2b447fecebbb1623b5b5b8e68c8cc7b5'
ELF = PRE/'input.elf'
ELF_SEAL = 'db4810a7ba41327dac9b9959aa8446dc7ac6b15c5e67ee77c9f3b94b70a58201'
LIFE_SEAL = '1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8'
IMAGE_SEAL = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
NAME = 'voperand_index_snapshot_restart'
TIMEOUT = 1200
FIELDS = ('cycle','event','order','port','trans_id','pc','insn','rd','rd_wdata',
          'mem_addr','mem_rmask','mem_wmask','mem_wdata','trap')
require = software.require


def exact(record, expected, message):
    require(all(k in record and type(record[k]) is type(v) and record[k] == v
                for k,v in expected.items()),message)


def validate(pre):
    exact(pre,dict(status='OPERAND_INDEX_SNAPSHOT_SPIKE_PREFLIGHT_PASS_NOT_DUT',
        baseline_tests=724,input_elf=str(ELF),vcs_started=False,coverage_admitted=False),
        'Exact software preflight differs')
    exact(pre['validation'],dict(status='SPIKE_SOFTWARE_ORACLE_PASS_NOT_DUT',checks=457,
        active_destination_bytes=96,destination_image_bytes=256,protected_neighbor_bytes=256,
        unchanged_input_bytes=1280,csr_words=6,traps=0,scalar_comparison_qualified=False,
        measured_coverage_gain=None,coverage_admitted=False),'Software oracle differs')
    require(pre['output_pins'].get(str(ELF)) == ELF_SEAL and
            pre['symbols']['tohost'] == 0x80001000 and
            pre['symbols']['replay_indexed_load'] == 0x800020cc,'Exact ELF/PC differs')
    for name in ('spike.trace','spike.stdout','spike-validation.json','compile-command.json',
                 'spike-command.json','target-before.json'):
        require(str(PRE/name) in pre['output_pins'],'Missing preflight output pin: '+name)
    for path in (software.APP,Path(software.__file__).resolve(),
                 Path(software.__file__).with_name('test_build_operand_index_snapshot_preflight.py')):
        require(str(path) in pre['pins'],'Missing software input pin: '+str(path))


def validate_targets(targets):
    exact(targets,dict(status='RAW724_EXACT16_REACHABLE_TARGET_HYPOTHESIS_NOT_DUT',
        software_preflight=str(PRE),software_seal=PRE_SEAL,counts=dict(cond=12,branch=4),
        runtime_hit_required=True,native_GUI_ID_qualification=False,coverage_admitted=False,
        vcs_started=False),'Exact target binding differs')
    expected = set()
    for lane in range(4):
        scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_requester' % lane
        expected.update((scope,'cond',i) for i in (786,799,1200))
        expected.add((scope,'branch',526))
    rows = targets.get('targets',[])
    require(len(rows) == 16 and {(r['scope'],r['metric'],r['point']['raw_index']) for r in rows} == expected,
            'Missing/duplicate/extra target')
    for row in rows:
        point = row['point']
        require(row['hit_before'] is False and point['file_id'] == '552','Wrong owner/nonzero target')
        if row['metric'] == 'cond':
            require(row['width'] == 1256 and row['checksum'] == '1592560956','Condition shape differs')
            index = point['raw_index']
            require((point['native_id'],point['line'],point['vector']) ==
                    {786:('298','427','1'),799:('303','535','01'),1200:('453','359','01')}[index],
                    'Compiled condition coordinate differs')
        else:
            require(row['width'] == 752 and row['checksum'] == '1229254119' and
                    (point['native_id'],point['vector'],point['attributes']['chksum']) ==
                    ('104','7','3186254472'),'Compiled branch coordinate differs')
            leaves = [e for e in point['expressions'] if e['id'] == '518' and
                      e['exprstr'] == 'requester_metadata_q[6].source_snapshot_replay']
            require(len(leaves) == 1 and point['native_vector']['vector'][-int(leaves[0]['index'])] == '1',
                    'Not replay branch true arm')


def reference_contract(pre):
    commits = software.s.parse_spike_commits(PRE/'spike.trace')
    require(software.validate(commits,pre['symbols'],(PRE/'spike.trace').read_text()) == pre['validation'],
            'Fresh independent software replay audit differs')
    prefix = []
    for c in commits:
        if not prefix and c.pc != 0x80000000:
            continue
        prefix.append(c)
        if (pre['symbols']['tohost'],1) in c.memory_accesses:
            break
    require(prefix and prefix[0].pc == 0x80000000 and
            prefix[-1].memory_accesses == ((pre['symbols']['tohost'],1),),'Reference scalar terminal missing')
    destinations = [c for c in prefix if c.vector_writes]
    require(len(destinations) == 4,'Reference vector destination population differs')
    return dict(matched_instructions=len(prefix),
        matched_scalar_writes=sum(len({r:v for r,v in c.gpr_writes.items() if r}) for c in prefix),
        matched_floating_writes=sum(len(c.fpr_writes) for c in prefix),
        matched_scalar_memory_accesses=sum(bool(c.memory_accesses) and
            spike_trace._scalar_memory_access(c.instruction) is not None for c in prefix),
        vector_destination_instructions=4,minimum_compared_vector_bytes=608,
        exact_known_written_vectors_only=True,unknown_active_bytes_allowed=False)


def command(output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'),'+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME]


def prepare(output, allow_existing=False):
    output = Path(output).absolute()
    require(output.parent == life.OUT and output.resolve() == output and not output.is_symlink() and
            (allow_existing or not output.exists()),'Independent direct runtime output required')
    helper = Path(life.__file__).resolve()
    require(life.digest(helper) == LIFE_SEAL,'Frozen lifecycle drift')
    pre = life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL)
    targets = life.read_bound(TARGETS,TARGET_SEAL)
    validate(pre)
    validate_targets(targets)
    plan = life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and
            plan['image'].get(str(life.IMAGE)) == IMAGE_SEAL,'Not exact old 66-file image')
    pins = life.merge_pins(pre['pins'],pre['output_pins'])
    pins = life.merge_pins(pins,targets['pins'])
    pins = life.merge_pins(pins,plan['image'])
    pins = life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):PRE_SEAL,
        str(TARGETS):TARGET_SEAL,str(helper):LIFE_SEAL,str(life.PLAN):life.PLAN_SEAL})
    paths = [Path(__file__).resolve(),Path(__file__).with_name('test_run_operand_index_snapshot_simulation.py')]
    paths += sorted((life.ROOT/'verification/ara_verify').rglob('*.py'))
    for path in paths:
        require(not path.is_symlink(),'Aliased checker source')
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    reference = reference_contract(pre)
    require(struct.unpack_from('<Q',ELF.read_bytes(),24)[0] == 0x80000000,'Wrong ELF entry')
    life.check(pins)
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=TIMEOUT,
        input_elf=str(ELF),input_spike_trace=str(PRE/'spike.trace'),target_before=str(TARGETS),
        old_image_files_checked=66,baseline_tests=724,reference_contract=reference,
        expected_checks=457,expected_traps=0,expected_active_destination_bytes=96,
        expected_destination_and_neighbor_image_bytes=512,expected_unchanged_input_bytes=1280,
        expected_csr_words=6,expected_replay_pc='0x800020cc',expected_replay_vl=37,expected_replay_vstart=13,
        expected_target_cond=12,expected_target_branch=4,
        required_offline_checks=['full_scalar_terminal','full_vector_exact','csr_signature_independent_oracle',
                                 'complete_contract_zero_exceptions','exact_target_bitmap'],
        automatic_retry=False,recompile_allowed=False,FSDB_enabled=False,target_hit_verified=False,
        full_architecture_comparison_verified=False,dut_self_check_verified=False,
        coverage_admitted=False,admission_performed=False,rtl_changed=False,new_RTL_signoff=False)


def run(output, manifest):
    require(manifest['timeout_s'] == TIMEOUT and manifest['command'] == command(output),
            'One-shot command/budget differs')
    life.check(manifest['pins'])
    output.mkdir()
    life.save(output/'manifest.json',manifest)
    try:
        life.check(manifest['pins'])
        with (output/'console.log').open('x') as log:
            subprocess.run(manifest['command'],cwd=output,stdout=log,stderr=subprocess.STDOUT,
                           timeout=TIMEOUT,check=True)
        life.check(manifest['pins'])
        life.save(output/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=0,case=NAME,coverage_admitted=False,admission_performed=False))
    except Exception as error:
        drift = None
        try:
            life.check(manifest['pins'])
        except Exception as pin_error:
            drift = str(pin_error)
        life.save(output/'simulation-status.json',dict(status='SIMULATION_NOT_ADMITTED',
            reason='%s: %s' % (type(error).__name__,error),post_failure_pin_error=drift,
            case=NAME,coverage_admitted=False,admission_performed=False))
        raise


def validate_scalar(result, reference):
    expected = {k:reference[k] for k in ('matched_instructions','matched_scalar_writes',
        'matched_floating_writes','matched_scalar_memory_accesses')}
    expected.update(status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted',skipped_unobservable_register_values=0,
        stopped_at_unobservable=None,aligned_vector_faults=[],ara_trap_events=0,
        mismatch=None,terminal_ecall=None,vector_state_compared=False,
        ara_retired_instructions=reference['matched_instructions'],
        ara_committed_instructions=reference['matched_instructions'])
    exact(result,expected,'Incomplete/nonexact full scalar comparison')
    exact(result.get('terminal_tohost',{}),dict(address='0x0000000080001000',write_value='0x1'),
          'Wrong terminal comparison')


def validate_vector(result, reference):
    exact(result,dict(status='PASS',nr_lanes=4,vlen_bits=1024,vector_destination_requests=4,
        prefix_vector_destination_requests=4,compared_instructions=4,skipped_unknown_bytes=0,
        non_bit_exact_instructions=0,unobservable_instructions=0,incomplete_requests=[],
        unretired_requests=[],trapped_requests=[],first_mismatch=None,stopped_at_spike_index=None),
        'Incomplete/nonexact known-vector comparison')
    require(type(result['compared_bytes']) is int and
            result['compared_bytes'] >= reference['minimum_compared_vector_bytes'],
            'Missing expected active vector bytes')


def signature(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))),
            'Partial scalar retirement trace')
    memory, terminals, operation = {}, [], []
    for row in retired:
        require(int(row['trap']) == 0 and int(row['pc'],16) != symbols['trap_fail'],'Unexpected trap')
        if int(row['pc'],16) == symbols['replay_indexed_load']:
            require(int(row['insn'],16)&~(31<<15) == software.WORD,'Indexed instruction differs')
            operation.append(row)
        mask = int(row['mem_wmask'],16)
        if mask:
            access = spike_trace._scalar_memory_access(int(row['insn'],16))
            require(access is not None and access[0] == 'write','Unknown scalar store')
            size, address = access[1],int(row['mem_addr'],16)
            require(size in (1,2,4,8) and address % size == 0 and
                    mask == ((1<<size)-1) << (address&7),'Wrong unshifted scalar store mask')
            data = int(row['mem_wdata'],16)&((1<<(8*size))-1)
            memory.update({address+i:(data>>(8*i))&255 for i in range(size)})
            if address == symbols['tohost']:
                require(size == 8,'Partial terminal')
                terminals.append((int(row['order']),data))
    require(len(operation) == 1 and terminals == [(len(retired)-1,1)],'Missing/duplicate operation/terminal')
    indices,data,after = software.images()
    expected = {'replay_dump':([0x07070707]*32+after+[0x0a0a0a0a]*32,4),
        'indices':(indices,4),'source':(data,4),'replay_csr':([37,17,13,0,37,0],8),
        'g75_result':([457,0],4),'num_failed':([0],4),'g75_trap':([0,0,0],8)}
    for name,(values,size) in expected.items():
        for i,value in enumerate(values):
            address = symbols[name]+i*size
            require(all(memory.get(address+b) == (value>>(8*b))&255 for b in range(size)),
                    'Independent DUT signature differs: %s[%d]' % (name,i))
    return dict(status='DUT_SIGNATURE_CSR_PREFIX_TAIL_NEIGHBORS_EXACT',checks=457,failures=0,
        traps=0,scalar_retirements=len(retired),observed_bytes=512+1280+48+8+4+24)


def audit(output, manifest, audit_output):
    require(audit_output.parent == life.OUT and audit_output.resolve() == audit_output and
            not audit_output.exists(),'Fresh independent audit output required')
    require(json.loads((output/'simulation-status.json').read_bytes()) ==
            dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,case=NAME,
                 coverage_admitted=False,admission_performed=False),'Failed/nonterminal simulation')
    pins = dict(manifest['pins'])
    files = [output/'manifest.json',output/'simulation-status.json',output/'console.log',
             output/'run.vcs.log',output/'commit_trace.csv',output/'vector_trace.csv']
    files += sorted(p for p in (output/'code.vdb').rglob('*') if p.is_file())
    require(any(str(p).endswith('.xml') for p in files) and not any(p.is_symlink() for p in files),
            'Missing/aliased VDB evidence')
    pins = life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    life.check(pins)
    require(not contract.check_contract_log(output/'run.vcs.log'),'DUT contract/log failure')
    require((output/'run.vcs.log').read_text().count('Core Test *** SUCCESS ***') ==
            (output/'console.log').read_text().count('Core Test *** SUCCESS ***') == 1,
            'Missing/duplicate SUCCESS')
    summaries = [contract.parse_contract_summary(l) for l in (output/'run.vcs.log').read_text().splitlines()
                 if '[ARA_CONTRACT]' in l]
    require(len(summaries) == 1 and summaries[0] is not None and summaries[0]['exceptions'] ==
            summaries[0]['mmu_request_cycles'] == 0,'Unexpected exception/MMU contract')
    with (output/'commit_trace.csv').open() as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == FIELDS,'Wrong commit schema')
        rows = list(reader)
    require(all(set(r) == set(FIELDS) and all(v is not None and v != '' for v in r.values()) for r in rows),
            'Malformed commit rows')
    architecture = signature(rows,manifest['preflight']['symbols'])
    scalar = spike_trace.compare_commit_prefix(PRE/'spike.trace',output/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    validate_scalar(scalar,manifest['reference_contract'])
    vector = vector_commit.compare_vector_commits(PRE/'spike.trace',output/'commit_trace.csv',
                                                   output/'vector_trace.csv',0x80000000)
    validate_vector(vector,manifest['reference_contract'])
    life.check(pins)
    audit_output.mkdir()
    for name,value in (('scalar-comparison.json',scalar),('vector-comparison.json',vector),
                       ('architecture-audit.json',architecture),('contract-summary.json',summaries[0])):
        life.save(audit_output/name,value)
    outputs = {str(p):life.digest(p) for p in audit_output.iterdir()}
    life.save(audit_output/'audit-manifest.json',dict(status='FULL_ARCHITECTURE_DIAGNOSTIC_PASS_NOT_ADMITTED',
        pins=pins,output_pins=outputs,target_bitmap_checked=False,coverage_admitted=False,
        new_RTL_signoff=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','run','audit'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared-seal')
    parser.add_argument('--audit-output',type=Path)
    args = parser.parse_args(argv)
    if (args.mode != 'prepare') != bool(args.prepared_seal) or (args.mode == 'audit') != bool(args.audit_output):
        parser.error('run/audit require reviewed seal; only audit requires independent --audit-output')
    output,manifest = prepare(args.output,allow_existing=args.mode == 'audit')
    record = output.with_name(output.name+'.prepared.json')
    if args.mode == 'prepare':
        life.save(record,manifest)
        print(json.dumps(dict(status='SNAPSHOT_RESTART_RUN_PREPARED_NO_VCS',prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest['pins']))))
    else:
        require(life.read_bound(record,args.prepared_seal) == manifest,'Reviewed prepared contract differs')
        if args.mode == 'run':
            run(output,manifest)
        else:
            require(life.read_bound(output/'manifest.json',args.prepared_seal) == manifest,
                    'Executed manifest differs')
            audit(output,manifest,args.audit_output.absolute())


if __name__ == '__main__':
    main()
