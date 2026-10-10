"""Known-state mask comparison predicates; no EDA, no generic unknown/skip override."""
import preflight_queue_mask_source_lifetime_tail as software

require=software.require
VLEN=1024
REGISTER_MASK=(1<<VLEN)-1

def known_register(value):
    require(type(value) is int and 0<=value<=REGISTER_MASK,'Full known VLEN1024 register required')
    return value

def compare_transition(old,actual,active_gold,vl):
    old=known_register(old);actual=known_register(actual);active_gold=known_register(active_gold)
    require(type(vl) is int and 0<vl<=VLEN,'Exact nonzero mask VL required')
    active=(1<<vl)-1;tail=REGISTER_MASK^active
    require((actual^active_gold)&active==0,'Defined active mask mismatch')
    require(old&~actual&tail==0,'Agnostic mask tail cleared an old1')
    return dict(active_bits_strict=vl,tail_bits_set_checked=VLEN-vl,
                tail_old0_became1=bin((~old)&actual&tail).count('1'),
                tail_retained=VLEN-vl-bin((old^actual)&tail).count('1'),
                whole_vd_skipped=False,Spike_tail_equality_required=False)

def case_context(index):
    require(type(index) is int and 0<=index<8,'Exact sealed eight-cell index required')
    sew,lmul=software.prior.CELLS[index];vl=128*lmul//(sew//8)
    source=software.prior.expected(index,'source')
    old8=int.from_bytes(source[16:144],'little')
    old9=int.from_bytes(source[144:272],'little') if lmul==2 else None
    gold=int.from_bytes(software.expected(index,'vid')[16:16+vl//8],'little')
    return dict(sew=sew,lmul=lmul,vl=vl,old8=old8,old9=old9,active_gold=gold)

def check_case(index,proven_pre_state,effective_post_state):
    """Caller must first prove loads and build post-state from ALL accepted writes."""
    context=case_context(index)
    require(proven_pre_state.get(8)==context['old8'],'Independent v8 load state not proved')
    require(8 in effective_post_state,'Missing complete effective post-v8')
    result=compare_transition(context['old8'],effective_post_state[8],context['active_gold'],context['vl'])
    if context['lmul']==2:
        require(proven_pre_state.get(9)==context['old9'],'Independent v9 load state not proved')
        require(effective_post_state.get(9)==context['old9'],'Non-destination v9 changed')
    for reg,value in effective_post_state.items():
        known_register(value)
        if reg!=8:
            require(reg in proven_pre_state and value==proven_pre_state[reg],
                    'Unexpected non-destination register effect')
    result.update(cell=index,non_destination_v9_strict=context['lmul']==2)
    return result

def apply_known_architectural_bytes(pre_state,accepted):
    """Apply deshuffled bytes. Absent writes retain old; never invent missing data."""
    state={reg:known_register(value) for reg,value in pre_state.items()}
    for (reg,byte),(value,write) in accepted.items():
        require(type(reg) is int and reg in state and type(byte) is int and 0<=byte<128,
                'Unknown pre-state or out-of-range native destination')
        require(type(value) is int and 0<=value<256,'Unknown accepted native byte')
        mask=255<<(8*byte)
        state[reg]=(state[reg]&~mask)|(value<<(8*byte))
    return state

def audit_known_writes(writes):
    """Call before folding: final-write coalescing must not hide an earlier X/Z."""
    for w in writes:
        require(type(w.be) is int and 0<=w.be<256 and w.be&~w.known_be==0,
                'Unknown byte in accepted native write')
        require(0<=w.lane<4 and 0<=w.eew<=3,'Invalid native lane/EEW')
    return len(writes)

def check_identity_transport(before,after):
    """Identity transport preserves actual DUT tail choice, NOT Spike tail choice."""
    require(before.keys()==after.keys(),'Identity transport register set changed')
    for reg,value in before.items():
        known_register(value);known_register(after[reg])
        require(value==after[reg],'Identity transport changed logical DUT state')
