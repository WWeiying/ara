"""Short new-SoC marker/ABI/PC checks before any full constructed Host."""
import json
import checker as c
from host_records import Builder
spec=c.specification();state=c.Strict(spec);builder=Builder(spec)
abi=list(builder.abi())
for row in abi:state.consume(row)
c.require(state.main_entered and state.body_entered and state.csr_count==5,'Actual ABI/startup phase')
c.require(state.regs[2]==state.s['__stack_top']-304,'Actual frame304')
c.require(state.value(state.s['__stack_top']-8,8)==0x80000052,'Actual saved source ra')
c.console_gate(c.marker()+'\n'+c.common.SUCCESS+'\n$finish')
for bad in (c.marker().replace('4095','4094'),c.marker()+'\nFAIL',c.marker()+'\n'+c.marker()):
    try:c.console_gate(bad)
    except ValueError:continue
    raise AssertionError('Marker negative accepted')
contract=c.owner_contract()
c.require([contract[k] for k in ('compulsory_memory_owners','required_target_owners','optional_slideup_targets')]==
    [20475,2592,18],'Actual model owner scope')
c.require(all(c.memory_op(c.Strict(spec).code[pc])['size']==(4 if int(offset)==1024 else 8)
    for offset,pc in spec['comparator_paths'][0]['output'].items()),'Actual SoC read sites')
with (c.HERE/'preflight_result.json').open('x') as f:json.dump(dict(status='PASS_SHORT_NEW_SOC_PREFLIGHT',
    ABI_frame=304,ELF_sha256=c.ELF_SHA,owner_contract=contract,constructed_ABI_rows=len(abi),
    fullstream_runs=0,DUT_runs=0,reference_runs=0),f,indent=2)
print('SHORT_SOC_PREFLIGHT_PASS')
