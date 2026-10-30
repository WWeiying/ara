"""Strict acceptance of paired cache-hint trials before reporting cycles."""
import re


def check_log(text,golden):
    def require(ok,message):
        if not ok:raise ValueError(message)
    require(len(golden)==7008,'Wrong archived first-group golden')
    require(not re.search(r'UVM_(?:ERROR|FATAL)\s+(?!:\s*0\b)|Fatal:',text),'Simulation error')
    require(text.count('CACHE_HINT_REFERENCE groups=3 errors=0')==1,'Reference check failed')
    require(text.count('CACHE_HINT_RESULT trials=4 errors=0')==1,'No unique completion')
    fields='id hint total producers hits misses stores compare_bytes copied_bytes fcsr vcsr errors signature'.split()
    rows=[]
    for line in text.splitlines():
        if not line.startswith('CACHE_HINT_TRIAL '):continue
        pairs=[token.split('=',1) for token in line.split()[1:]]
        require([p[0] for p in pairs]==fields,'Trial fields')
        rows.append({k:int(v,16 if k=='signature' else 10) for k,v in pairs})
    require(len(rows)==4,'Trial count')
    for index,row in enumerate(rows):
        hint=int(index in (1,2))
        expected=dict(id=index,hint=hint,producers=3,hits=6,misses=3,stores=3,
                      compare_bytes=294912 if hint else 442368,copied_bytes=136800,
                      fcsr=17,vcsr=5,errors=0)
        require(all(row[k]==v for k,v in expected.items()),'Data/state/counter mismatch')
        require(row['total']>0,'Invalid cycle count')
    require(len({row['signature'] for row in rows})==1,'Output signatures disagree')
    baseline=sum(rows[i]['total'] for i in (0,3))/2
    hinted=sum(rows[i]['total'] for i in (1,2))/2
    return dict(state='PASS',trials=rows,baseline_mean=baseline,hinted_mean=hinted,
                speedup=baseline/hinted,cycle_reduction=1-hinted/baseline,
                whole_model=False,matrix_execution=False,
                reference='target generic quantizer, plus archived group-0 golden')
