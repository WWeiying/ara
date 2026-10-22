"""Exact parent CSR-aware qualification, all2989 Toggle OR, and48 PTE owner replay."""
from pathlib import Path
from types import FunctionType
import admit_itlb_ppn_aba794 as old

life,require=old.life,old.require
QUAL=life.OUT/'itlb-ppn-aba-qualified-v2-parent-20261008-01'
Q_SHA='0e39eeac0b6a6335877c8232a7b54fe44f91a0e162cdc81b562d56547f7495f8'
OLD_SHA='eda9807e352f25590da1c69227d45c083fe8ba733b64d62ed57439868b3f7999'
COLLECTOR_SHA='959809fb5b34bfd3794c16d4fc4fabc807a89335c41ef0f0802d6283a4865e47'
TESTS_SHA='ebe6d0e69a95d478ef23058ccad4c4a9949ba6bf2e9a4c008e78b52961b5552c'


def owners(wave,native):
    accepted,updates=wave['accepted_full_PTEs'],wave['updates']
    old.case.accepted_gate(accepted)
    require(len(updates)==48,'Exactly48 native owner/update observations required')
    keys=('time_100fs','phase','asid','vpn','entry')
    require([tuple(r[k] for k in keys) for r in updates]==
            [tuple(r[k] for k in keys) for r in accepted],
            'Full native owner and packed-PTE observations must be identical, including time')
    times=[r['time_100fs'] for r in accepted]
    require(all(type(t) is int and t>=0 for t in times) and
            all(a<b for a,b in zip(times,times[1:])),'Unique strictly ordered actual accepted cycles required')
    vpns={old.case.pre.prior.shared.vpn(0,e):e for e in range(16)}
    records=[]
    for a,u in zip(accepted,updates):
        e=vpns[a['vpn']];pc=old.case.pre.address(a['phase'],e)
        require(int(u['lookup_vaddr'],16)==pc,'Source canonical thunk PC differs from observed update owner')
        records.append(dict(a,software_thunk=e,execute_PC=hex(pc)))
    traps=native['traps']
    require(len(traps)==48 and [(r['phase'],r['entry'],r['ecall_pc']) for r in traps]==
            [(p,e,hex(old.case.pre.address(p,e)+8)) for p in range(3) for e in range(16)],
            'All48 actual retired ECALL PCs must match source thunk order')
    return dict(status='EXACT48_NATIVE_TIME_SLOT_VPN_PTE_AND_EXECUTION_OWNERS_REPLAYED',
                accepted_records=records,actual_slots=16,actual_updates=48,
                entry_indices_observed_not_inferred=True,all_ASID_phases=True)


def qualification_gate(q,directory):
    old.qualification_gate(q,directory)
    require(directory==QUAL and q['original_failure_preserved'] is True and
            q['original_collector_sha256']=='1fd703e7df46fc5fd8bacfa903ffd81b5ec649bedd53a4f909d9752694c2bcd9',
            'Exact parent CSR-aware qualification with original failure preserved required')
    require(q['input_pins'].get(str(Path(old.case.__file__).with_name('collect_itlb_ppn_aba_v2.py')))==COLLECTOR_SHA and
            q['input_pins'].get(str(Path(old.case.__file__).with_name('test_collect_itlb_ppn_aba_v2.py')))==TESTS_SHA,
            'Exact successful CSR successor/helper test pins required')
    def doc(name):
        p=directory/name
        require(str(p) in q['output_pins'],'Missing qualified output: '+name)
        return life.read_bound(p,q['output_pins'][str(p)])
    receipt=doc('console-csr-contract.json');csr=doc('csr-lifecycle.json')
    require(receipt['status']=='SIX_READONLY_CSR_CONSOLE_CSV_MONITOR_EXACT_ZERO_VECTOR_WRITES' and
            receipt['summary']==dict(requests=6,responses=6,exceptions=0,mmu_request_cycles=0,
                protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0) and
            receipt['lifecycle']==csr and receipt['zero_vector_writes'] is True and
            receipt['UVM_final_summary_claimed'] is False,'Six CSR complete console/CSV contract required')
    owners(doc('itlb-axi-observations.json'),doc('native-oracle.json'))


def all_toggle_or(before,single,after):
    require(len(before)==2989 and set(before)==set(single)==set(after),
            'Exact2989 binary Toggle instance universe required')
    for scope,row in before.items():
        added,final=single[scope],after[scope]
        require((row['width'],row['checksum'])==(added['width'],added['checksum'])==
                (final['width'],final['checksum']),'Toggle compiled width/checksum differs')
        values=[int(r['bits'],16) for r in (row,added,final)]
        require(min(values)>=0 and max(values).bit_length()<=row['width'] and
                values[2]==values[0]|values[1],'Independent2989 Toggle OR/bounds differs')


def rebase(before,single):
    after,gain=old.rebase(before,single)
    all_toggle_or(before,single,after)
    gain=dict(gain,full_OR_Toggle_instances=2989,
              global_new_serialized_positions=sum(len(p) for p in old.toggle.gains(before,after).values()))
    return after,gain


def evaluate(directory,qsha):
    require(directory==QUAL and qsha==Q_SHA and life.digest(Path(old.__file__))==OLD_SHA,
            'Only exact parent successful qualification and frozen predecessor allowed')
    implementation=FunctionType(old.evaluate.__code__,dict(old.evaluate.__globals__,
        qualification_gate=qualification_gate,rebase=rebase))
    values,text=implementation(directory,qsha)
    q=life.read_bound(directory/'qualification.json',qsha)
    def doc(name):return life.read_bound(directory/name,q['output_pins'][str(directory/name)])
    values['native-PTE-owner-replay.json']=owners(doc('itlb-axi-observations.json'),doc('native-oracle.json'))
    pins=values['evidence-pins.json']
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_itlb_ppn_aba794_v2.py').resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins);values['evidence-pins.json']=pins
    values['status.json']=dict(values['status.json'],full_OR_Toggle_instances=2989,
        native48_PTE_owner_replayed=True,complete_CSR_console_receipt=True,
        global_new_binary_Toggle_positions=values['itlb-ppn-aba-toggle-gain.json']['global_new_serialized_positions'])
    return values,text


def main():
    implementation=FunctionType(old.main.__code__,dict(old.main.__globals__,evaluate=evaluate))
    implementation()


if __name__=='__main__':main()
