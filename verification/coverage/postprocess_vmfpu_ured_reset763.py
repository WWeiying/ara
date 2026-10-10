"""Offline exact seed37/reduction38 cancellation binding; never launches a simulator."""
import inspect
import json
from pathlib import Path
import run_vmfpu_ured_reset763 as old
import ara_verify.vector_commit as vector

life,require=old.life,old.require
SEAL='b257ff434fa0a13730933af987ac7f4d890ff136cdc412f5b0bc28b84489f9bb'
OUT=life.OUT/'vmfpu-ured-intra-reset-qualified763-agent-20261007-02'


def arch_mapping(path):
    starts,retires,trapped=vector._parse_architecture_mapping(path)
    require(not trapped,'Unexpected trapped vector request')
    return vector._map_architecture_retires(starts,retires,trapped,allow_incomplete_tail=True)


def seed_word(pre):
    matches=[c.instruction for c in old.shared.spike_trace.parse_spike_commits(old.PRE/'spike.trace')
             if c.pc==pre['symbols']['ured_ones']]
    require(matches==[0x5e02c457],'Independent seed opcode/PC differs')
    return matches[0]


def cancelled_binding(pending,commits,pre):
    mapping=arch_mapping(commits)
    expected={0:(37,seed_word(pre),8,'ured_ones'),1:(38,pre['words']['ured_reduce'],2,'ured_reduce')}
    require(set(pending)==set(expected),'Cancelled VID population differs')
    result=[]
    for vid,(seq,word,vd,symbol) in expected.items():
        r=pending[vid];retire=mapping.get(seq)
        require(int(r['arch_seq'])==seq and int(r['vid'])==vid and int(r['insn'],16)==word and
                int(r['vd'])==vd and int(r['eew'])==3 and int(r['vl'])==128 and int(r['vstart'])==0 and
                int(r['lane'])==0 and int(r['source'])==0 and int(r['cycle'])==8568+vid and
                int(r['use_vd'])==1 and retire is not None and retire.pc==pre['symbols'][symbol] and
                retire.instruction==word,'Exact cancelled PC/opcode/owner/shape differs')
        result.append(dict(vid=vid,arch_seq=seq,pc=retire.pc,insn=word,vd=vd,vl=128,eew=3))
    return result


def initial_bytes(commits,rows,pre):
    mapping=arch_mapping(OUT/'epoch0/commit_trace.csv')
    owners={int(r['arch_seq']):r for r in rows if r['event']=='alloc'}
    count=0;seen=set()
    for r in rows:
        if r['event']!='write':continue
        seq=int(r['arch_seq']);owner=owners[seq];retire=mapping.get(seq)
        vd=int(owner['vd']);word=int(owner['insn'],16)
        require(retire is not None and retire.instruction==word and int(owner['eew'])==3 and
                word&0xfc00707f==0x5c004057,'Unexpected epoch0 writer or real-PC binding differs')
        require(seq not in (37,38),'Cancelled seed/reduction wrote before observed cancellation')
        if retire.pc==pre['symbols']['ured_seed2']:
            require(seq==35 and vd==1,'Seed2 owner differs');expected=0x4000000000000000
        else:
            require(3<=seq<=34 and vd==seq-3 and retire.pc<pre['symbols']['ured_seed2'],
                    'Initial VRF seed owner/register differs')
            expected=0x0101010101010101*(0x40+vd)
        be=int(r['be'],16);actual=int(r['wdata'],16)
        identity=(seq,int(r['lane']),int(r['addr']))
        require(be==255 and int(r['source'])==0 and 0<=identity[1]<4 and
                vd*4<=identity[2]<vd*4+4 and identity not in seen,
                'Full e64 seed byte enables/lane/address/duplicate differ')
        seen.add(identity)
        for i in range(8):
            require((actual>>(8*i))&255==(expected>>(8*i))&255,'Epoch0 seed byte differs');count+=1
    require(count==4224,'Full32 VRF seeds plusseed2 writes incomplete')
    return count


def collect():
    plan=life.read_bound(old.PLAN,SEAL)
    pins=life.merge_pins(plan['pins'],{str(old.PLAN):SEAL})
    require(json.loads((old.RUN/'manifest.json').read_bytes())==dict(plan,pins=pins),'Actual execution plan differs')
    require(json.loads((old.RUN/'simulation-status.json').read_bytes())['returncode']==0,'Terminal failed')
    require(json.loads((old.QUAL/'failure.json').read_bytes())['first_error']=='Wrong reset-cancelled backend owner',
            'Original failure receipt differs')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_postprocess_vmfpu_ured_reset763.py'),
              Path(vector.__file__).resolve(),old.QUAL/'failure.json'):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    source=inspect.getsource(old.collect)
    original="""require(pending and pre['words']['ured_reduce'] in {int(r['insn'],16) for r in pending.values()} and
                all(int(r['insn'],16) in allowed for r in pending.values()),'Wrong reset-cancelled backend owner')"""
    require(source.count(original)==1,'Frozen cancellation predicate changed')
    source=source.replace(original,"binding=cancelled_binding(pending,QUAL/'epoch0/commit_trace.csv',pre)\n        life.save(QUAL/'cancelled-owner-bindings.json',binding)")
    require(source.count("allowed=set(pre['words'].values())")==1,'Frozen allowed-owner inventory changed')
    source=source.replace("allowed=set(pre['words'].values())","allowed=set(pre['words'].values())|{seed_word(pre)}")
    ns=dict(old.collect.__globals__,QUAL=OUT,initial_bytes=initial_bytes,
            cancelled_binding=cancelled_binding,seed_word=seed_word)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),ns)
    ns['collect'](dict(plan,pins=pins),SEAL)


if __name__=='__main__':collect()
