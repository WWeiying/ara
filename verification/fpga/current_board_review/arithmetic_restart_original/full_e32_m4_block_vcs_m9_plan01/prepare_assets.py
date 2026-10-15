"""Own profile successor, no source/RTL/compiler/image mutation."""
import json
import checker as c
old=c.HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'
profile=c.read(old)
profile.update(allowed_shape=c.SHAPE,original_soc_elf_sha256=c.ELF_SHA,
    original_linux_elf_sha256='4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9',
    authority_sha256=c.sha(old),reference_bound_sha256=c.READY_SHA)
with (c.HERE/'reset_profile.json').open('x') as f:json.dump(profile,f,indent=2);f.write('\n')
print('OWN_M9_PROFILE_ONLY')
