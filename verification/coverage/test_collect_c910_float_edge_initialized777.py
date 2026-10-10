import copy
from dataclasses import replace
import unittest
import collect_c910_float_edge_initialized777 as q


class InitializedNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre=q.runner.preflight(); cls.symbols=pre['symbols']; cls.reference=q.reference_prefix(pre)
        roles={cls.symbols['edge_'+op+str(w)]:(op,w) for op in ('load_a','load_b','div','store') for w in (16,32,64)}
        init={cls.symbols['edge_initial_v'+str(b)]:b for b in (8,16,24)}
        cls.mapping={}; cls.activities={}; counters={op:0 for op in ('load_a','load_b','div','store')}
        for index,commit in enumerate(cls.reference):
            if commit.pc not in roles and commit.pc not in init: continue
            seq=len(cls.mapping); cls.mapping[seq]=index; writes=[]
            if commit.pc in init:
                base=init[commit.pc]; eew=0; vl=1024; vd=base; use=True
                for reg in range(base,base+8):
                    for word in range(4):
                        for lane in range(4):
                            writes.append(q.vc.VectorWrite(row=len(writes),cycle=seq,arch_seq=seq,vid=seq%8,lane=lane,source=0,
                                instruction=commit.instruction,eew=0,addr=reg*4+word,be=255,data=0,known_be=255))
            else:
                op,w=roles[commit.pc]; phase=counters[op]; counters[op]+=1
                eew={16:1,32:2,64:3}[w]; vl=256//w; vd={'load_a':8,'load_b':16,'div':24,'store':24}[op]; use=op!='store'
                if use:
                    value=q.p.gold(w,phase%8,phase//8%2)[{'load_a':0,'load_b':1,'div':2}[op]]
                    for lane in range(4):
                        writes.append(q.vc.VectorWrite(row=len(writes),cycle=seq,arch_seq=seq,vid=seq%8,lane=lane,source=1 if op=='div' else 4,
                            instruction=commit.instruction,eew=eew,addr=vd*4,be=255,data=q.p.word(value,w),known_be=255))
            cls.activities[seq]=q.vc.ArchActivity(instruction=commit.instruction,allocations=1,completions=1,
                vd=vd,use_vd=use,eew=eew,vl=vl,vstart=0,writes=writes)

    def state(self,activities): return q.native_state(self.reference,activities,self.mapping,self.symbols)

    def test_full147_writers_contexts_initialized3072_and_original4608(self):
        proof=self.state(self.activities)
        self.assertEqual(proof['initialization']['compared_bytes'],3072)
        self.assertEqual(proof['defined_bytes'],4608)
        self.assertEqual(proof['operations']['store'],48)

    def test_init_unknown_nonzero_missing_extra_wrongcontext_rejected(self):
        for case in ('unknown','nonzero','missing','extra','context','producer'):
            activities=copy.deepcopy(self.activities); a=activities[0]
            if case=='unknown': a.writes[0]=replace(a.writes[0],known_be=254)
            elif case=='nonzero': a.writes[0]=replace(a.writes[0],data=1)
            elif case=='missing': a.writes.pop()
            elif case=='extra': a.writes.append(replace(a.writes[0],addr=0))
            elif case=='context': a.vl=32
            else: a.writes[0]=replace(a.writes[0],source=3)
            with self.assertRaises(ValueError,msg=case): self.state(activities)

    def test_generic_no_stop_zero_unknown_contract_source(self):
        import inspect
        text=inspect.getsource(q.native)
        self.assertNotIn('stop_spike_index=',text)
        self.assertIn("result['status'] == 'PASS'",text)
        self.assertIn("'skipped_unknown_bytes'",text)
        self.assertIn('store_adapter.restore_stores',text)


if __name__=='__main__': unittest.main()
