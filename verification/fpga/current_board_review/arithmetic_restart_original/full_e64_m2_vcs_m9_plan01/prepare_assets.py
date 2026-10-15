"""Create own proven M9 profile/owner contract; no old material is edited."""
import json
import checker as c
old=c.HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'
profile=c.read(old)
profile.update(allowed_shape=c.SHAPE,original_soc_elf_sha256=c.ELF_SHA,
    original_linux_elf_sha256='1ac38feec918ada897841aef50bc5edc0b1d713f39b2193d89157f7d31a2e436',
    authority_sha256=c.sha(old),reference_bound_sha256=c.READY_SHA)
with (c.HERE/'reset_profile.json').open('x') as f:json.dump(profile,f,indent=2);f.write('\n')
with (c.HERE/'owner_contract.json').open('x') as f:json.dump(c.owner_contract(),f,indent=2);f.write('\n')
print('OWN_PROFILE_NO_IMAGE_CHANGE',c.owner_contract())
