"""Publish only accepted software/reference evidence; does not launch a DUT."""
import prepare as p

def main():
    pins={};cases=[]
    p.require(p.read(p.HERE/'host01.json')['actual_wait_returncode']==0,'Host failure')
    for n in (0,3):
        root=p.HERE/f'reference_scenario{n}_01';r=p.read(root/'status.json');e=p.read(root/'execution.json')
        p.require(r['status']=='REFERENCE_CHECKER_PASS_NOT_DUT' and r['pins_unchanged'] is True,
                  'Reference not accepted')
        p.require(type(e['actual_wait_returncode']) is int and e['actual_wait_returncode']==0 and not e['timeout'],
                  'Actual reference outcome')
        p.require(r['scenario']==n and r['scalar_checks']==(5477 if n==0 else 5481)
                  and r['original_helper_instructions']==11 and r['target_attempts']==1
                  and len(r['checkpoints'])==2 and r['htif']==[1], 'Full original reference scope')
        p.require(r['allowed_undefined_output_indices']==([5,6,7,8] if n==0 else []),'Original tail policy')
        q=p.read(root/'input_pins.json');p.verify(q);pins.update(q)
        spec=p.read(p.HERE/'software01'/f'scenario{n}'/'soc.spec.json')
        cases.append(dict(scenario=n,sew=64,original=p.CASES[n],soc_elf=spec['elf'],
            soc_sha256=spec['elf_sha256'],reference=str(root/'status.json'),reference_sha256=p.sha(root/'status.json'),
            actual_reference_rc=e['actual_wait_returncode'],firmware_commits=r['firmware_commits'],
            checks=r['scalar_checks'],reference_elapsed_s=e['elapsed_s'],
            target_returned_vl=4 if n==0 else 8,post_helper_vl=8,
            defined_original_results=4 if n==0 else 8,undefined_output_indices=r['allowed_undefined_output_indices']))
        for f in root.iterdir():
            if f.is_file():pins[str(f)]=p.sha(f)
    pins.update(p.read(p.HERE/'M9_BINDING.json')['pins'])
    for f in p.HERE.iterdir():
        if f.is_file():pins[str(f)]=p.sha(f)
    p.verify(pins);p.save(p.HERE/'input_pins.json',pins)
    p.save(p.HERE/'READY.json',dict(status='HOST_SPIKE_TWO_ORIGINAL_E64_SINGLES_PASS_NOT_DUT',
        cases=cases,input_pins=str(p.HERE/'input_pins.json'),input_pins_sha256=p.sha(p.HERE/'input_pins.json'),
        pin_count=len(pins),DUT_launched=False,independent_review_pending=True,
        memory_owner_contract='four nonempty owners including three nontarget helpers; deletion-pair negatives',
        limitations=['Source-derived real Sv39, not Linux fork/wait/signal replay',
                    'sc0 original undefined tail four outputs not constrained after FOF',
                    'Architectural no-fault does not prove zero internal MMU/AXI activity']))
    print('READY_TWO_ORIGINAL_E64_SINGLES_NOT_DUT',flush=True)

if __name__=='__main__':main()
