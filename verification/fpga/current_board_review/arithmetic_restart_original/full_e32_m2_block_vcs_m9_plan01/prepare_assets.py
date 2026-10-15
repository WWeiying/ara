"""Own profile successor, no source/RTL/compiler/image mutation."""
import json
import checker as c
old=c.HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'
profile=c.read(old)
profile.update(allowed_shape=c.SHAPE,original_soc_elf_sha256=c.ELF_SHA,
    original_linux_elf_sha256='978310da20bf437709dae962164491c1f1e8bea6acb9b62ba7a0dbe01c621c3c',
    authority_sha256=c.sha(old),reference_bound_sha256=c.READY_SHA)
with (c.HERE/'reset_profile.json').open('x') as f:json.dump(profile,f,indent=2);f.write('\n')
print('OWN_M9_PROFILE_ONLY')
