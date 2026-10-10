"""Prepare/verify explicit-parent admission of frozen771 + one scalar FPU PASS."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import collect_scalar_fpu_backpressure_gain771 as gain
import diagnose_scalar_fpu_backpressure_v2 as reviewed

p=gain.p
life,require=p.life,p.require
GAIN=life.OUT/'scalar-fpu-backpressure-gain771-agent-20261007-01'
GAIN_SHA='98351d56df2536fd4fe69f3a0676291c6c61a1db119166a56a2b688f0447e79b'


def union_gate(before,single,after):
    require(len(before['tests'])==len(set(before['tests']))==771 and
        single['tests']==[str(p.RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
        'Exact771 prefix plus unique actual singleton')
    actual=p.bitmap.combine(before,single)
    require(actual==after and after['tests'][:771]==before['tests'] and
        len(after['tests'])==len(set(after['tests']))==772 and
        sum(len(rows) for rows in after['metrics'].values())==6162, 'Full6162 OR/prefix')


def functional_gate(q):
    gain.contract(q)
    require(q['results']==[v for row in p.cases() for v in row['expected']] and
        q['csr']==[q['csr'][0],64,64,64,q['csr'][0]] and
        q['guards']==[0x539af02c168be47d,0xce71049af28635bd], 'Full numeric/NaNbox/FCSR/guard gold')


def native_member(pins):
    parent=p.RUN/'code.vdb/snps/coverage/db/testdata'
    folders=list(parent.iterdir())
    require(len(folders)==1 and folders[0].name=='scalar_fpu_backpressure' and folders[0].is_dir(),
        'One actual native candidate member')
    for name in ('siminfo.xml','vcmArguments.xml','line.verilog.data.xml','cond.verilog.data.xml',
                 'branch.verilog.data.xml','fsm.verilog.data.xml','tgl.verilog.data.xml'):
        file=folders[0]/name
        require(file.resolve()==file and not file.is_symlink() and file.stat().st_size>0 and
            pins.get(str(file))==life.digest(file), 'Complete sealed native metric/end record')
    info=gain.t.xml(folders[0]/'siminfo.xml').findall('srctest')
    require(len(info)==1 and shlex.split(info[0].get('cmdline',''))==p.command(p.PRE/'input.elf') and
        info[0].get('workdir')==str(p.RUN) and
        int(info[0].get('finishtime','0'))>int(info[0].get('starttime','0'))>0,
        'Native exact command/workdir/completion')
    return dict(info[0].attrib)


def elf_dedup(base,pins,ledger):
    # Reuse the admitted audit of the first770; do not re-search every old ELF.
    path=p.BASE/'elf-ledger-dedup.json'
    audit=life.read_bound(path,base['output_pins'][str(path)])
    require(audit['ledger_members']==770 and audit['duplicate'] is False and
        [r['vdb'] for r in audit['members']]==ledger[1:771], 'Sealed resolved first770 ELF audit')
    new_sha=pins[str(p.PRE/'input.elf')]
    previous=[]
    for row in audit['members']:
        require(row['ELF_candidates'], 'Missing resolved historical ELF')
        for file,sha in row['ELF_candidates'].items():
            require(pins.get(file)==sha and sha!=new_sha,'Duplicate/drifting historical ELF')
            previous.append(sha)
    # Bind the final771 member to its actual executed command, not a nearby app.
    command_path=Path(ledger[-1]).parent/'manifest.json'
    require(str(command_path) in pins,'Last771 actual command must be inherited')
    command=life.read_bound(command_path,pins[str(command_path)])['command']
    preload=[x.split('=',1)[1] for x in command if x.startswith('+PRELOAD=')]
    require(len(preload)==1 and preload[0] in pins and pins[preload[0]]!=new_sha,
        'Last771 actual ELF identity/dedup')
    previous.append(pins[preload[0]])
    return dict(ledger_members=771,duplicate=False,new_elf_sha256=new_sha,
        inherited_first770_audit=str(path),inherited_first770_audit_seal=base['output_pins'][str(path)],
        final771_command=str(command_path),final771_ELF=preload[0],
        all_previous_ELF_pins_checked=True)


def evaluate():
    seal_path=GAIN/'collection-seal.json';seal=life.read_bound(seal_path,GAIN_SHA)
    require(seal['schema']=='SCALAR_FPU_BACKPRESSURE_GAIN771_SEAL_V1' and
        seal['diagnostic_seal']==gain.DIAG_SHA and seal['consumer_seal']==gain.BINDING_SHA and
        seal['baseline_seal']==p.BASE_SHA and seal['coverage_admitted'] is False, 'Exact reviewed evidence chain')
    pins=life.merge_pins(seal['input_pins'],seal['output_pins'])
    pins=life.merge_pins(pins,{str(seal_path):GAIN_SHA})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_scalar_fpu_backpressure772.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    q=life.read_bound(gain.DIAG,gain.DIAG_SHA);functional_gate(q)
    scalar=p.old.architecture.spike_trace.compare_commit_prefix(p.PRE/'spike.trace',p.RUN/'commit_trace.csv',
        0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    p.old.architecture.scalar_exact(scalar,q['scalar_counts'])
    require(scalar==json.loads((reviewed.OUT/'scalar-comparison.json').read_bytes()),'Independent scalar recheck')
    require(reviewed.checked_wave_function()(reviewed.OUT/'probe.vcd')==q['backpressure'], 'Complete strict holding recheck')
    base=life.read_bound(p.BASE/'admission-manifest.json',p.BASE_SHA)
    before=life.read_bound(p.BASE/'combined-bits.json',pins[str(p.BASE/'combined-bits.json')])
    ledger=(p.BASE/'combined-inputs.txt').read_text().splitlines()
    require(base['coverage_admitted'] is True and base['output']==str(p.BASE) and
        ledger==[str(gain.DESIGN),*before['tests']] and len(ledger)==len(set(ledger))==772,
        'Formal771 full ordered population')
    single=life.read_bound(GAIN/'single-bits.json',pins[str(GAIN/'single-bits.json')])
    inputs=GAIN/'candidate-inputs.txt'
    require(inputs.read_text().splitlines()==[str(gain.DESIGN),str(p.RUN/'code.vdb')], 'Exact single native inputs')
    require(p.bitmap.collect(inputs)==single,'Independent complete singleton recollection')
    after=life.read_bound(GAIN/'combined-bits.json',pins[str(GAIN/'combined-bits.json')])
    union_gate(before,single,after)
    delta=p.bitmap.delta(before,after)
    require(delta==life.read_bound(GAIN/'raw-delta.json',pins[str(GAIN/'raw-delta.json')]), 'Exact all-metric delta')
    report=life.read_bound(GAIN/'gain.json',pins[str(GAIN/'gain.json')])
    require(report['schema']=='SCALAR_FPU_BACKPRESSURE_771_GAIN_V1' and report['baseline']==771 and
        report['proposed_population']==772 and report['raw_four_metrics']==delta['metrics'] and
        report['whole_design_new_serialized_toggle_positions']==report['system_new_serialized_toggle_positions']==148 and
        report['binary_toggle_instances']==2989 and report['positive_gain'] is True and
        report['coverage_admitted'] is False and report['official_percentage_claimed'] is False,
        'Exact measured positive raw gain, not DVE scoring')
    gain.positive(delta['metrics'],report['system_new_serialized_toggle_positions'])
    expected={'fpu_gen.operand_a_q':80,'fpu_gen.operand_b_q':62,'fpu_gen.fpu_op_q':2,
              'fpu_gen.fpu_srcfmt_q':1,'fpu_gen.fpu_dstfmt_q':1,'fpu_gen.fpu_tag_q':2}
    require({r['name']:len(r['positions']) for r in report['wrapper_typed_gains']}==expected and
        len(report['toggle_instances'])==1 and report['toggle_instances'][0]['scope']==p.SCOPE and
        report['toggle_instances'][0]['checksum']=='397086886', 'Exact typed holding gain identity')
    native=native_member(pins);dedup=elf_dedup(base,pins,ledger)
    life.check(pins)
    status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',coverage_admitted=True,aggregate_passed=772,
        baseline=771,new_passed=1,exact771_prefix=True,full_OR_instances=6162,unique_new_vdb=True,
        duplicate_ELF=False,full_scalar_ISA_verified=True,full_scalar_memory_verified=True,
        required_floating_results=16,NaN_box_verified=True,fflags_FCSR_restore_verified=True,
        checks=22,guards_verified=True,vector_status='UNOBSERVABLE_ZERO_DATA_REQUESTS',
        actual_capture_release_transactions=12,actual_STALL_preedge_samples=64,
        idle_ownerless_flushes=3,held_transaction_flushes=0,native_five_metrics_retained=True,
        raw_delta=delta['metrics'],new_system_serialized_toggle_positions=148,
        official_percentage_claimed=False,RTL_changed=False,new_simulation=False,
        diagnostic_seal=gain.DIAG_SHA,consumer_binding_seal=gain.BINDING_SHA)
    values={'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'scalar-fpu-toggle-gain.json':report,'elf-ledger-dedup.json':dedup,'native-member.json':native,
        'evidence-pins.json':pins,'status.json':status}
    return values,'\n'.join([str(gain.DESIGN),*after['tests']])+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','admit'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--parent-authorized',action='store_true')
    a=parser.parse_args();require(a.parent_authorized==(a.mode=='admit'),'Separate explicit parent admission authority')
    out=a.output.absolute();require(out.parent==life.OUT and out.resolve()==out and
        (not out.exists() or a.mode=='verify'), 'Fresh formal successor only')
    values,text=evaluate()
    outputs={str(out/name):hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest()
             for name,value in values.items()}
    outputs[str(out/'combined-inputs.txt')]=hashlib.sha256(text.encode()).hexdigest()
    record=out.with_name(out.name+'.prepared.json')
    proposal=dict(schema='SCALAR_FPU_BACKPRESSURE_HISTORICAL772_ADMISSION_V1',output=str(out),
        baseline=str(p.BASE),baseline_seal=p.BASE_SHA,qualification=str(gain.DIAG),
        qualification_seal=gain.DIAG_SHA,consumer_seal=gain.BINDING_SHA,gain_seal=GAIN_SHA,
        input_pins=values['evidence-pins.json'],output_pins=outputs,coverage_admitted=False)
    if a.mode=='prepare':
        life.save(record,proposal);print('PREPARED772',record,life.digest(record),flush=True);return
    require(a.seal,'Explicit prepared/admitted seal required')
    if a.mode=='verify' and out.exists():
        admitted=life.read_bound(out/'admission-manifest.json',a.seal)
        require(admitted==dict(proposal,coverage_admitted=True,prepared=str(record),
            prepared_seal=admitted['prepared_seal'],authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION'),
            'Complete admitted manifest equality')
        require(life.read_bound(record,admitted['prepared_seal'])==proposal,'Original prepared contract')
        life.check(outputs);print('FORMAL772_OFFLINE_REVERIFIED',flush=True);return
    require(life.read_bound(record,a.seal)==proposal,'Exact prepared contract')
    if a.mode=='verify':print('PREPARED772_VERIFIED_NO_ADMISSION',flush=True);return
    out.mkdir()
    for name,value in values.items():life.save(out/name,value)
    with (out/'combined-inputs.txt').open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(outputs)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(record),
        prepared_seal=a.seal,authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION'))
    print('ADMITTED772',out,life.digest(out/'admission-manifest.json'),flush=True)


if __name__=='__main__':main()
