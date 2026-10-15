"""Pre-reference bound from the compiled fixed-loop adapter; no reference tuning."""
import prepare as p
from newscope import CAP,ALLOC,MASK_BYTES

def main():
    code=p.obs.disassemble((p.OUT/'spike.dis').read_text())
    s=p.read(p.OUT/'spike.symbols.json')
    p.require(s['main'] in code and s['check'] in code,'Actual compiled main/check')
    # Same successful-path allowances as immutable M4 fixture; sizes follow source.
    parts=dict(memory_oracle=16*1024*220,
      setup=16*(1024+ALLOC+(ALLOC+2)+CAP+MASK_BYTES+2*(CAP+16))*16,
      refills=8*512*16,output_oracle=16*CAP*120,traps=28*4000,initial_final=300000)
    upper=sum(parts.values())+400000
    p.require(upper<p.obs.LIMIT,'Static bound exceeds one-reference cap')
    p.save(p.OUT/'bound.json',dict(admit_once=True,instruction_limit=p.obs.LIMIT,
      static_upper_instructions=upper,parts=parts,timeout_s=120,raw_bytes=1024**3,isa=p.ISA,
      soc_elf_sha256=p.sha(p.OUT/'soc.elf'),spike_elf_sha256=p.sha(p.OUT/'spike.elf'),
      disassembly_sha256=p.sha(p.OUT/'spike.dis'),reference_only=True,automatic_retry=False))
    print(parts,upper)
if __name__=='__main__':main()

