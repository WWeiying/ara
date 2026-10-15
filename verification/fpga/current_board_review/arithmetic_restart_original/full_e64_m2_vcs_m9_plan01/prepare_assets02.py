"""Narrow static observer successor; preserve previous failure and proven profile."""
import json
import checker as c
p=c.read(c.HERE/'reset_profile.json')
c.validate_reset(c.specification())
contract=c.owner_contract()
c.require(contract['compulsory_memory_owners']==29925,'Five helper-memory owners per5985')
with (c.HERE/'owner_contract02.json').open('x') as f:json.dump(contract,f,indent=2);f.write('\n')
print(contract)
