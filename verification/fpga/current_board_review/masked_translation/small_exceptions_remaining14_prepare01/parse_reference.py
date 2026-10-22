"""One independent raw traversal per final Spike ELF; separate numeric receipt."""
import argparse
import time
import prepare as p
ap=argparse.ArgumentParser();ap.add_argument('--sew',type=int,required=True);ap.add_argument('--scenario',type=int,required=True)
a=ap.parse_args();d=p.HERE/'software01'/p.key(a.sew,a.scenario);r=p.HERE/'reference01'/p.key(a.sew,a.scenario)
start=time.monotonic()
try:
    result=p.o.analyze(r/'spike.trace',p.read(d/'spike.symbols.json'),p.o.disassemble((d/'spike.dis').read_text()),d/'spike.elf',a.sew,a.scenario)
except BaseException as error:
    import diagnostics
    p.save(r/'first_failure.json',diagnostics.context(error,'reference_full_oracle',dict(p.o.LAST_CONTEXT),p.key(a.sew,a.scenario)))
    raise
result.update(raw_sha256=p.sha(r/'spike.trace'),elf_sha256=p.sha(d/'spike.elf'),isa=p.ISA,parser_elapsed_s=time.monotonic()-start)
p.save(r/'status.json',result)
print(result['status'],result['commits'],result['scalar_checks'])
