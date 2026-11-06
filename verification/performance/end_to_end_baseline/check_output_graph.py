"""Independent ordered trace audit, not inference from the guest PASS marker."""
import re

from audit import require

PROFILES={'qwen25_q8':(12,2,128,1536,16,256),'qwen25_q4':(12,2,128,1536,16,256),
          'qwen3_q8':(16,8,20,2048,8,160),'qwen3_q4':(16,8,20,2048,8,160)}


def check(text):
    pending=None;rows=[];passed=[]
    order=list(PROFILES)
    for line in text.replace('\r','').splitlines():
        if line.startswith('OUTPUT_GRAPH_BEGIN '):
            require(pending is None,'Nested graph call')
            m=re.fullmatch(r'OUTPUT_GRAPH_BEGIN name=(\w+) candidate=([01]) repeat=([012])',line)
            require(m is not None,'Bad graph begin')
            name,candidate,trial=m[1],int(m[2]),int(m[3]);index=len(rows)
            require(index<12 and name==order[index//3] and trial==index%3 and candidate==int(trial!=0),'Graph order')
            pending=dict(name=name,candidate=candidate,trial=trial,records={})
        elif line.startswith('GGML_RISCV_QUANT_KV'):
            require(pending is not None,'Unexpected dispatch outside paired graph')
            tag=line.split()[0]
            require(tag not in pending['records'],'Duplicate graph diagnostic')
            fields={}
            for word in line.split()[1:]:
                k,sep,v=word.partition('=');require(sep and v.isdecimal() and k not in fields,'Bad dispatch field')
                fields[k]=int(v)
            pending['records'][tag]=fields
        elif line.startswith('OUTPUT_GRAPH_END '):
            require(pending is not None,'Unpaired graph end')
            m=re.fullmatch(r'OUTPUT_GRAPH_END name=(\w+) candidate=([01]) repeat=([012]) flags=(\d+) max_abs=([0-9.eE+-]+)',line)
            require(m is not None and (m[1],int(m[2]),int(m[3]))==
                    (pending['name'],pending['candidate'],pending['trial']),'Graph completion identity')
            name=pending['name'];heads,kv,visible,outputs,commands,values=PROFILES[name]
            records=pending['records'];candidate=pending['candidate']
            expected={'status':0,'mapping':0,'memory':1,'runtime_called':1,
                      'command_attempts':commands,'groups':kv,'value_decodes':values,'executor_status':0}
            require(records.get('GGML_RISCV_QUANT_KV')==expected,'Native activity mismatch')
            for tag,enabled in (('OUTPUT_TILE',candidate),('REGISTER_PV',1-candidate)):
                require(records.get('GGML_RISCV_QUANT_KV_'+tag)==dict(enabled=enabled,status=0,completed_groups=kv),'Wrong selected entry')
            flags=int(m[4]);error=float(m[5]);require(flags<=31 and flags&8 and 0<=error<=0.001,'Flags/error summary')
            if pending['trial']: require(flags==rows[-1]['flags'],'Paired flags changed')
            rows.append(dict(name=name,candidate=candidate,flags=flags,max_abs=error,commands=commands));pending=None
        elif line.startswith('OUTPUT_GRAPH_PROFILE_PASS '):
            require(pending is None and len(rows)==3*(len(passed)+1) and len(passed)<4,'Premature profile verdict')
            name=order[len(passed)];h,kv,t,n,_,_=PROFILES[name]
            require(line==f'OUTPUT_GRAPH_PROFILE_PASS name={name} heads={h} kv={kv} visible={t} outputs={n} native_calls=3 rejected=2 exact=1 inputs_unchanged=1','Profile verdict mismatch')
            passed.append(name)
    require(pending is None and len(rows)==12 and passed==order,'Incomplete graph matrix')
    lines=text.replace('\r','').splitlines()
    require(lines.count('OUTPUT_GRAPH_SUITE_PASS profiles=4 native_calls=12 fallback_calls=8')==1 and
            lines.count('GUEST_TEST_EXIT=0')==1 and 'Kernel panic' not in text,'Guest completion')
    return dict(state='ORDERED_GRAPH_TRACE_PASS',profiles=4,native_calls=12,
                native_commands=sum(r['commands'] for r in rows),fallback_calls=8,trials=rows,
                performance_measured=False)
