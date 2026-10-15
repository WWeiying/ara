"""Metadata-only successor: retain original READY, correct scope output count."""
import prepare as p
from newscope import CAP,LMUL,CHECKS,TARGET_REGISTERS

def main():
    r=p.read(p.HERE/'READY.json');s=p.read(p.HERE/'reference01/status.json')
    p.require(s['output_elements']==16*CAP and s['scalar_checks']==CHECKS,'Measured full scope')
    pins=p.read(r['evidence_pins'])
    log=p.HERE/'seal.log'
    p.require(pins[str(log)]=='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855','Original seal stdout was captured empty')
    expected=dict(status=r['status'],pins=r['pin_count'],ready_sha256=p.sha(p.HERE/'READY.json'),
      reference_status_sha256=r['reference_status_sha256'],soc_elf_sha256=r['soc_elf_sha256'])
    p.require(log.read_text()==str(expected)+'\n','Only exact deterministic post-seal stdout accepted')
    p.save(p.HERE/'seal_stdout_recovery02.json',dict(old_pin=pins[str(log)],actual_closed_sha256=p.sha(log),
      cause='seal.py hashed its open redirected stdout before printing final metadata',reference_rerun=False,raw_reparsed=False))
    pins[str(log)]=p.sha(log)
    pins[str(p.HERE/'seal_stdout_recovery02.json')]=p.sha(p.HERE/'seal_stdout_recovery02.json')
    p.pinscheck(pins)
    for f in (p.HERE/'READY.json',p.HERE/'evidence_pins.json',p.HERE/'seal_metadata02.py'):pins[str(f)]=p.sha(f)
    p.save(p.HERE/'evidence_pins02.json',pins)
    r.update(scope=dict(r['scope'],output_elements=16*CAP,target_registers=list(TARGET_REGISTERS),
      neighbor_register_guards=False,snapshot_guards='eight uint64 memory words before/after each complete legal target group'),
      supersedes_metadata_only=str(p.HERE/'READY.json'),original_ready_sha256=p.sha(p.HERE/'READY.json'),
      evidence_pins=str(p.HERE/'evidence_pins02.json'),evidence_pins_sha256=p.sha(p.HERE/'evidence_pins02.json'),pin_count=len(pins))
    p.save(p.HERE/'READY02.json',r);print(p.sha(p.HERE/'READY02.json'))
if __name__=='__main__':main()

