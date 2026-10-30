"""Functional/record check only: QEMU clocks are not performance evidence."""


def check(text):
    def require(ok, message):
        if not ok: raise ValueError(message)
    mode=None; graphs={}; expected_rows=0; seen_rows=0
    compares=[]; ends=[]; begins=[]
    for line in text.replace('\r','').splitlines():
        if line.startswith('GRAPH_CYCLES_MODEL_BEGIN '):
            require(mode is None, 'Nested mode')
            mode=int(line.split('enabled=')[1]); begins.append(mode)
        elif line.startswith('GRAPH_CYCLES_MODEL_END '):
            require(int(line.split('enabled=')[1])==mode, 'Mode end mismatch')
            ends.append(mode);mode=None
        elif line.startswith('GRAPH_CYCLES_MODEL_COMPARE '): compares.append(line)
        elif line.startswith('GGML_NODE_CYCLES '):
            require(mode==1, 'Probe emitted outside ON child')
            f=dict(x.split('=',1) for x in line.split()[1:])
            gid=int(f['graph']); require(gid not in graphs, 'Duplicate graph')
            require(f['valid']=='1' and f['threads']=='1' and f['clock']=='rdcycle', 'Invalid graph')
            count=int(f['records']); total=int(f['elapsed']); nodes=int(f['node_sum'])
            require(count>0 and total>=nodes>=0, 'Invalid graph totals')
            graphs[gid]=dict(count=count,sum=nodes,last=-1,seen=0,cycles=0)
            expected_rows+=count
        elif line.startswith('GGML_NODE_CYCLE '):
            require(mode==1, 'Node outside ON child')
            f=dict(x.split('=',1) for x in line.split()[1:]);gid=int(f['graph'])
            require(gid in graphs, 'Node without graph')
            g=graphs[gid];first=int(f['first']);last=int(f['last']);cycles=int(f['cycles'])
            require(first>g['last'] and last>=first and cycles>=0, 'Invalid node group')
            require(len(f['ne'].split(','))==4, 'Missing shape')
            g['last']=last;g['seen']+=1;g['cycles']+=cycles;seen_rows+=1
    require(begins==[0,1] and ends==[0,1] and mode is None, 'Incomplete paired modes')
    require(len(graphs)>=6 and seen_rows==expected_rows, 'Incomplete graph records')
    require(all(g['seen']==g['count'] and g['cycles']==g['sum'] for g in graphs.values()), 'Accounting mismatch')
    require(compares==[f'GRAPH_CYCLES_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
                      for k in range(2) for s in range(3)], 'Model comparison mismatch')
    require(text.count('GRAPH_CYCLES_MODEL_SUITE_PASS comparisons=6 performance=not_measured')==1 and
            text.count('GUEST_TEST_EXIT=0')==1 and 'GRAPH_CYCLES_MODEL_FAIL' not in text, 'Missing completion')
    return dict(state='FUNCTIONAL_RECORDS_PASS',graphs=len(graphs),records=seen_rows,
                logits_compared=911616,performance_measured=False,
                hardware_command_counts_verified=False,reuse_counts_verified=False)
