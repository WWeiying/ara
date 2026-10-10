"""Small strict retirement/counter oracles; no simulator, tracing or admission runner."""
import inspect
import re
import fence_rvfi_audit as frozen

require = frozen.require
PAD = 65536


def counter(rows, software_ceil):
    """All rows are continuous pre-edge samples of the same native controller instance."""
    require(len(rows) > 3, 'Missing native window')
    fields={'cycle','rst_n','priv_q','priv','sel','pad','q','load','state','drain','ceil'}
    q=0;loads=0;ceiling=0;pad_busy=False;reset_seen=False
    previous=None
    for row in rows:
        require(set(row)==fields and all(type(v) is int for v in row.values()), 'Unknown/X/incomplete sample')
        require(row['rst_n']==1 and row['sel']==1 and row['pad']==PAD and
                row['priv'] in (0,3) and row['priv_q'] in (0,3) and
                row['state'] in range(5) and 0<=row['drain']<=15, 'Native configuration/window changed')
        if previous is None:
            require(row['priv_q']==3 and row['priv']==3 and row['state']==0, 'Missing pre-entry baseline')
        else:
            require(row['cycle']==previous['cycle']+1 and row['priv_q']==previous['priv'], 'Discontinuous cycle/privilege window')
            if previous['state']==3:
                require(row['state']==(4 if previous['q']==0 else 3), 'PAD exit/stall differs')
        require(row['q']==q, 'Independent counter recurrence differs')
        load=int(row['priv_q']==0 and row['priv']!=0)
        require(row['load']==load, 'Native load does not match U exit')
        expected_ceil=PAD-q if row['state']==2 and row['drain']==15 and q else 0
        require(row['ceil']==expected_ceil, 'Independent drain ceiling differs')
        ceiling=max(ceiling,expected_ceil)
        pad_busy |= row['state']==3 and q>0
        reset_seen |= row['state']==4
        loads+=load
        # Frozen delta_counter: clear=0, load priority over en, down=1, delta=1.
        q=PAD if load else max(0,q-1)
        previous=row
    require(loads==1 and q==0 and rows[-1]['state']==0 and pad_busy and reset_seen and
            0<ceiling<PAD and software_ceil==ceiling, 'No complete nonzero-padding witness/ceiling parity')
    return dict(counter_parity=True, samples=len(rows), loads=loads, ceiling=ceiling,
                native_observer_verified=False,cyclequalified=False,
                input_authentication_required=True,application_approval=False)


def parse_padding_trace(text, ecall):
    source=inspect.getsource(frozen.parse_trace)
    before="row['event'] == 'retire' and row['trap'] == 0"
    require(source.count(before)==1, 'Frozen RVFI parser boundary differs')
    source=source.replace(before,"row['event'] == 'retire' and row['trap'] in (0, 1)")
    parser_namespace=dict(frozen.parse_trace.__globals__)
    exec(compile(source,__file__+':exact-ecall','exec'),parser_namespace)
    rows=parser_namespace['parse_trace'](text)
    traps=[r for r in rows if r['trap']]
    require(len(traps)==1 and traps[0]['pc']==ecall and traps[0]['insn']==0x73 and
            traps[0]['rd']==traps[0]['mem_rmask']==traps[0]['mem_wmask']==0,
            'Not the unique precise ECALL trap row')
    require(sum(r['pc']==ecall for r in rows)==1, 'Duplicate ECALL event')
    return rows


def retirement(text, metadata, blob, sites, software_ceil):
    syms={s['Symbol']['Name']['Name']:s['Symbol'] for s in metadata['Symbols']}
    enter=syms['padding_enter_mret']['Value'];back=syms['padding_return_mret']['Value']
    third=syms['gap36_fence2']['Value'];ecall=syms['padding_u_ecall']['Value']
    rows=parse_padding_trace(text,ecall)
    trap_index=next(i for i,r in enumerate(rows) if r['trap'])
    require(len(sites)==3 and [int(s['fence_pc'],16) for s in sites]==
            [syms['gap36_fence0']['Value'],syms['gap36_fence1']['Value'],third], 'Wrong three source sites')
    positions={pc:[i for i,r in enumerate(rows) if r['pc']==pc] for pc in (enter,back,third)}
    require(all(len(v)==1 for v in positions.values()) and
            positions[enter][0]<positions[back][0]<positions[third][0], 'Wrong U/handler/fence order')
    for pc in (enter,back):
        require(rows[positions[pc][0]]['insn']==0x30200073, 'Not exact MRET')
    require(positions[enter][0]<trap_index<positions[back][0], 'Wrong exception/return ordering')
    ledger=syms['padding_trap'];handler=syms['padding_handler']
    require(ledger['Size']==56 and handler['Size']>0,'Wrong trap ledger/handler extent')
    stores={}
    for row in rows[trap_index+1:positions[back][0]]:
        if row['mem_wmask']:
            offset=row['mem_addr']-ledger['Value']
            require(handler['Value']<=row['pc']<handler['Value']+handler['Size'] and
                    row['mem_wmask']==255 and offset in (8,16,24,32,40) and offset not in stores,
                    'Unexpected/duplicate handler store')
            stores[offset]=row['mem_wdata']
    require(set(stores)=={8,16,24,32,40} and stores[8]==1 and stores[16]==8 and
            stores[24]==ecall and stores[32]==0 and stores[40]&0x27888==0x6000,
            'Independent trap-store expectations differ')
    ceil_reads=[]
    for row in rows[positions[third][0]+1:]:
        word=row['insn']
        if word&127==0x73 and word>>20==0x7c5:
            funct3=(word>>12)&7;rs1=(word>>15)&31
            if funct3==1 or (funct3 in (2,3) and rs1!=0):break
            if funct3==2 and rs1==0 and row['rd']!=0:ceil_reads.append(row['rd_wdata'])
    require(ceil_reads==[software_ceil] and 0<=software_ceil<=PAD,'Native CEIL read/UART parity differs')
    source=inspect.getsource(frozen.audit_rows)
    replacements=[('len(sites) == 2','len(sites) == 3'),
        ('index < returns[0]', "(index < returns[0] if round_id < 2 else index > positions[back][0])")]
    for before,after in replacements:
        require(source.count(before)==1,'Frozen retirement adapter boundary differs')
        source=source.replace(before,after)
    namespace=dict(frozen.audit_rows.__globals__,positions=positions,back=back)
    exec(compile(source,__file__+':three-sites','exec'),namespace)
    result=namespace['audit_rows'](rows,metadata,blob,sites)
    result.update(capture_stores_checked=195,
        privilege_evidence='Two original M fences before first MRET; third after exact U-entry/handler-return MRETs. Requires independent trap ledger and native privilege samples.',
        independent_trap_stores=stores,native_CSR_ceil_parity=True,exact_cycle_proof=False,
        application_approval=False)
    return result


def uart(text, ecall_pc):
    require('FAIL:' not in text, 'Software failure')
    require(text.splitlines().count('fence_t_gap36_smoke rounds=2 checks=458 failures=0')==1 and
            text.splitlines().count('fence_t_u_padding_successor legacy_checks=458 extra_checks=241 failures=0')==1,
            'Missing full legacy/additional checks')
    require(text.splitlines().count('PASSED: fence_t_u_padding_successor')==1, 'Missing unique successor PASS')
    match=re.findall(r'^fence_t_u_padding_successor ceiling=(\d+) padding_witness=(\d+)$',text,re.M)
    require(len(match)==1 and 0<=int(match[0][0])<=PAD and
            int(match[0][1])==int(int(match[0][0])!=0), 'Invalid software ceiling/witness record')
    return dict(legacy_checks=458,extra_checks=241,software_ceil=int(match[0][0]),
                independent_trap_ledger_required=True,ecall_pc=ecall_pc,
                nonzero_ceil_observed=int(match[0][0])>0,exact_cycle_proof=False,
                native_bitmap_review_required=True,application_approval=False)
