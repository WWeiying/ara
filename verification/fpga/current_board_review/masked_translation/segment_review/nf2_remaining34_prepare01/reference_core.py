"""Shared parameterized reference observer, derived from the accepted four-case observer."""
import re
import model
def configure(cases):
    model.configure(cases)
    globals().update({k:getattr(model,k) for k in
        ('base','CASES','N','NAMES','OFF','SITE','VA','G','DONE','COUNTS','TOTAL',
         'readint','compare','phases','active','seed','record_count','orig')})

def validate(trace,s):
    memory,regs,points,exits={}, {0:0}, [], []
    actions=[[] for _ in range(N)]
    events=[[] for _ in range(N)]
    commits=0
    for line in trace.splitlines():
        m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not m: continue
        mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4]
        commits+=1
        base.require(pc!=s['trap_entry'],'Default trap handler executed')
        c=readint(memory,s['mx_current'])
        access=[(int(a,16),int(v,16) if v else None)
                for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc in (s['mx_segment_load'],s['mx_segment_store']):
            base.require(c<N and pc==s[SITE[c]] and mode==1,'Wrong target or privilege')
            base.require(insn==(0x20055c27 if CASES[c]['store'] else 0x20055c07),'Original NF2 masked opcode differs')
            actions[c].append('target')
            events[c].append(dict(opcode=hex(insn),access=access))
        if pc==s['mx_younger_store']:
            base.require(mode==1,'Younger store not S-mode'); actions[c].append('younger')
        if pc==s['mx_repair_sfence']:
            base.require(mode==3 and regs.get((insn>>15)&31)==VA+4096,'Wrong repair SFENCE')
            actions[c].append('repair_sfence')
        if pc==s['mx_trap_mret'] and readint(memory,s['mx_marker']+8*c)==0:
            actions[c].append('retry_mret')
        if pc==s['mx_refill_page']: actions[c].append('refill')
        if pc==s['mx_cleanup_sfence']:
            base.require(mode==3 and regs.get((insn>>15)&31)==VA+4096,'Wrong cleanup SFENCE')
            actions[c].append('cleanup_sfence')
        if pc==s['mx_checkpoint']:
            phase=readint(memory,s['mx_phase'])
            checked=compare(memory,s,c,phase)
            points.append(dict(id=c,name=NAMES[c],phase=phase,checked_bytes=checked,commit=commits))
            actions[c].append({1:'fault_checkpoint',2:'final_checkpoint',3:'precleanup_checkpoint'}[phase])
        for a,v in access:
            if v is None: continue
            opcode,funct=insn&127,(insn>>12)&7
            if insn&3!=3:
                d=base.compressed_memory(insn)
                base.require(d is not None and d['kind']=='write','Unknown compressed store')
                width=d['size']
                base.require(a==(regs.get(d['base'],-1)+d['offset'])&((1<<64)-1),'Compressed address differs')
            else:
                base.require(opcode in (0x23,0x27),'Unknown store opcode')
                width=(1<<funct) if opcode==0x23 else {0:1,5:2,6:4,7:8}[funct]
            physical=s['mx_pages']+a-VA if VA<=a<VA+8192 else a
            for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')): memory[physical+i]=b
            if a==s['tohost']: exits.append(v)
        regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    traps=re.findall(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)
    wanted_traps=[]
    for c in range(N):
        if CASES[c]['fault']:
            wanted_traps.append(('trap_store_page_fault' if CASES[c]['store'] else 'trap_load_page_fault','%016x'%s[SITE[c]]))
        wanted_traps.append(('trap_supervisor_ecall','%016x'%s['mx_ecall']))
        if CASES[c]['fault']:
            order=['target','fault_checkpoint','repair_sfence']
            if CASES[c]['unmapped']:order+=['refill']
            order+=['retry_mret','target','younger','final_checkpoint']
        else:
            order=['target','younger','precleanup_checkpoint','cleanup_sfence']
            if CASES[c]['unmapped']:order+=['refill']
            order+=['final_checkpoint']
        base.require(actions[c]==order,'Exact fault/nofault/cleanup order differs: '+str((c,actions[c])))
        base.require(len(events[c])==1+int(CASES[c]['fault']),'Attempt/retry count differs')
        def accesses(indices):
            return [(VA+OFF[c]+4*i+2*f,seed(c,f+1,i) if CASES[c]['store'] else None)
                    for i in indices for f in (0,1)]
        if CASES[c]['fault']:
            before=[i for i in range(CASES[c]['start']) if active(c,i)]
            after=[i for i in range(CASES[c]['start'],8) if active(c,i)]
            base.require(events[c][0]['access']==accesses(before),'Fault-attempt access list differs')
            base.require(events[c][1]['access']==accesses(after),'Restart access list differs')
        else:base.require(events[c][0]['access']==[],'Alloff target performed memory access')
    base.require(traps==wanted_traps,'Exception ledger differs '+str(traps))
    base.require([(x['id'],x['phase']) for x in points]==[(c,p) for c in range(N) for p in phases(c)],'Checkpoint coverage differs')
    base.require(exits==[1] and readint(memory,s['mx_errors'])==0 and readint(memory,s['mx_unexpected'])==0,'Software failure')
    base.require(readint(memory,s['mx_completed'])==DONE,'Missing completion magic')
    base.require(commits<3000000,'Reference instruction bound exceeded')
    base.require(readint(memory,s['mx_checks'])==TOTAL,'Complete firmware check count differs')
    base.require([readint(memory,s['mx_case_checks']+8*c) for c in range(N)]==list(COUNTS),
                 'Per-case oracle count differs')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',cases=list(NAMES),checkpoints=points,
                checks=readint(memory,s['mx_checks']),case_checks=[readint(memory,s['mx_case_checks']+8*c) for c in range(N)],
                commits=commits,traps=traps,actions=actions,target_events=events,
                VCS_launched=False,Linux_launched=False)
