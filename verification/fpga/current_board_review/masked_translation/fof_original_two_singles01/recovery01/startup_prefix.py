"""Read only the bounded startup prefix; require one full ordered BSS clear."""
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
import run as recovery
p=recovery.p

def main():
    result=[];pins={str(Path(__file__).resolve()):p.sha(Path(__file__))}
    for sew,folder in ((8,'audit_e8_01'),(64,'reference_e64_01')):
        status_path=recovery.HERE/folder/'status.json';status=p.read(status_path)
        raw=Path(status['raw_path']);s_path=recovery.ROOT/'software01'/f'e{sew}'/'spike.symbols.json';s=p.read(s_path)
        p.require(p.sha(raw)==status['raw_sha256'],'Retained raw drift')
        expected=list(range(s['__bss_start'],s['__bss_end'],8));actual=[];lines=0;commits=0
        reached=False
        with raw.open() as stream:
            for lines,line in enumerate(stream,1):
                p.require(lines<=100000,'Bounded startup prefix exceeded')
                m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
                if not m:continue
                mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4];commits+=1
                if pc==s['main']:reached=True;break
                for a,v in re.findall(r'\bmem 0x([0-9a-f]+) 0x([0-9a-f]+)',tail):
                    address,value=int(a,16),int(v,16)
                    p.require(mode==3 and pc==s['_start']+0x46 and insn==0x0002b023 and value==0,
                              'Noncanonical pre-main memory write')
                    actual.append(address)
        p.require(reached and actual==expected and actual.count(s['fx_completed'])==1,
                  'Missing/reordered/duplicate BSS initialization or completion clear')
        result.append(dict(sew=sew,lines_read=lines,commits_through_main=commits,
                           bss_writes=len(actual),completion_zero_writes=1,
                           completion_address=hex(s['fx_completed']),startup_pc=hex(s['_start']+0x46),
                           stopped_at_main=True,no_whole_raw_reparse=True))
        for f in (status_path,raw,s_path):pins[str(f)]=p.sha(f)
    p.save(recovery.HERE/'startup_prefix.json',dict(status='PASS_BOUNDED_STARTUP_IDENTITY',cases=result,pins=pins))
    print(result)

if __name__=='__main__':main()
