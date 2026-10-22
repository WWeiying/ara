"""Synthetic full482 RVFI oracle and exact compiled ABI; no simulation or reference."""
from copy import deepcopy
import unittest
import checker as c


class Fixture:
    def __init__(self,spec):
        self.s=spec;self.code=spec['code'];self.order=0
        body=set(spec['main_pcs'])
        self.setters={r:next(p for p,i in self.code.items() if p in body and
            i&127 in (0x13,0x33,0x17,0x37,0x1b,0x3b) and i>>7&31==r)
            for r in (5,10,11,12,13,14,15,16,28)}
        self.setters[17]=0x800005da
        c.require(self.code[self.setters[17]]==0x4881,'Actual zero a7 C.LI site')
        self.memsites={}
        for size,kind in ((8,'write'),(1,'write'),(8,'read')):
            choices=[(p,c.memory_op(i)) for p,i in self.code.items() if p in body and c.memory_op(i) and
                c.memory_op(i)['size']==size and c.memory_op(i)['kind']==kind and
                c.memory_op(i)['base'] in self.setters and c.memory_op(i)['register'] in self.setters and
                c.memory_op(i)['base']!=c.memory_op(i)['register']]
            self.memsites[size,kind]=choices[0]

    def row(self,pc,rd=0,value=0,address=0,rm=0,wm=0,data=0):
        r=dict(cycle=str(self.order+1),event='retire',order=str(self.order),port='0',trans_id='-1',
            pc=f'{pc:016x}',insn=f'{self.code[pc]:08x}',rd=str(rd),rd_wdata=f'{value&c.MASK64:016x}',
            mem_addr=f'{address&c.MASK64:016x}',mem_rmask=f'{rm:02x}',mem_wmask=f'{wm:02x}',
            mem_wdata=f'{data&c.MASK64:016x}',trap='0')
        self.order+=1;return r

    def setreg(self,reg,value):return self.row(self.setters[reg],reg,value)

    def memory(self,address,size,value,kind):
        pc,d=self.memsites[size,kind]
        yield self.setreg(d['base'],address-d['offset'])
        enable=((1<<size)-1)<<(address%8)
        if kind=='write':
            yield self.setreg(d['register'],value)
            yield self.row(pc,address=address,wm=enable,data=value)
        else:yield self.row(pc,rd=d['register'],value=value,address=address,rm=enable)

    def abi(self):
        sy=self.s['symbols'];base=sy['_start']
        c.require([self.code[base+i] for i in (0,4,8,12,0x4a)]==
            [0x00041197,0xa2018193,0x00100117,0xfe810113,0x561000ef],'Compiled full482 ABI')
        for offset,rd,value in ((0,3,0x80041000),(4,3,0x80040a20),(8,2,0x80100008),
                (12,2,0x800ffff0),(0x10,0,0),(0x14,5,0x80000014),(0x18,5,0x80000050),
                (0x1c,0,0),(0x20,5,0x6000),(0x22,5,0x6600),(0x26,0,0),
                (0x2a,0,0),(0x2e,0,0),(0x32,5,0x80040032),
                (0x36,5,sy['__bss_start']),(0x3a,6,sy['__bss_end'])):
            yield self.row(base+offset,rd,value)
        for address in range(sy['__bss_start'],sy['__bss_end'],8):
            yield self.row(base+0x3e)
            yield self.row(base+0x42,address=address,wm=255,data=0)
            yield self.row(base+0x46,5,address+8)
            yield self.row(base+0x48)
        yield self.row(base+0x3e)
        yield self.row(base+0x4a,1,base+0x4e)
        main=sy['main']
        yield self.row(main,2,0x800fffe0)
        yield self.row(main+2,address=0x800fffe8,wm=255,data=0x8000004e)
        yield self.row(main+4,address=0x800fffe0,wm=255,data=0)
        pc=self.s['main_vlenb'];yield self.row(pc,(self.code[pc]>>7)&31,128)

    def full(self,gold):
        yield from self.abi()
        for i,r in enumerate(self.s['capacity']):
            yield self.row(r['pc'],5 if i==0 else 10 if i==1 else 0,c.MASK64 if i==0 else 512 if i==1 else 0)
        pc=self.s['body_vlenb'];yield self.row(pc,(self.code[pc]>>7)&31,128)
        sy=self.s['symbols']
        for call,g in enumerate(gold['rows']):
            for name,data in (('a',gold['a']),('b',gold['b']),('mask',gold['masks'][g['mode']]),
                    ('out',[91]+g['old']+[91])):
                chunks=len(data)//8
                for j in range(chunks):
                    yield from self.memory(sy[name]+j*8,8,int.from_bytes(bytes(data[j*8:j*8+8]),'little'),'write')
                for j in range(chunks*8,len(data)):yield from self.memory(sy[name]+j,1,data[j],'write')
            for name,value in (('checks',call),('elements',call*512),('errors',0)):
                yield from self.memory(sy[name],8,value,'write')
            for reg,value in zip(range(10,18),[sy['a'],sy['b'],sy['out']+1,g['vl'],512,sy['mask'],g['vstart'],0]):
                yield self.setreg(reg,value)
            for i,r in enumerate(self.s['routine']):
                if i in (0,5,10):yield self.row(r['pc'],5,g['vl'] if i==5 else 512)
                elif i==6:yield self.row(r['pc'],28,0,address=sy['b'],rm=1<<(sy['b']%8))
                elif i==9:yield self.row(r['pc'],10,0)
                else:yield self.row(r['pc'])
            output=bytes([91]+g['output']+[91])+b'\xa5'*6
            for j in range(65):
                yield from self.memory(sy['out']+j*8,8,int.from_bytes(output[j*8:j*8+8],'little'),'read')
        for name,value in (('checks',482),('elements',246784),('errors',0)):
            yield from self.memory(sy[name],8,value,'write')
        text='BOARD_CASE_BEGIN '+c.ID+'\n'
        text+=''.join(f'RVV_TRIAL seed=0 vl={r["vl"]} mask=0 vstart={r["vstart"]} completed={r["trial"]}\n'
            for r in gold['rows'] if r['mode']==r['accumulator']==0)
        text+='\n'.join([c.SUMMARY,'MACC_PREFIX_PASS '+c.ID+' trials=482','BOARD_CASE_PASS '+c.ID,'BOARD_REPLAY_PASS'])+'\n'
        for value in text.encode():yield from self.memory(self.s['uart'],1,value,'write')
        yield self.setreg(5,self.s['ctrl']);yield self.setreg(10,0)
        yield self.row(self.s['exit_store'],address=self.s['ctrl'],wm=255,data=0)
        yield self.row(self.s['park'])


class Memory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=c.specification();cls.gold=c.read(c.REF/'model.json')
        cls.profile=c.read(c.HERE/'reset_profile.json')
        state=c.Strict(cls.spec,cls.gold,cls.profile);cls.snapshots={}
        for row in Fixture(cls.spec).full(cls.gold):
            pc=int(row['pc'],16);address=int(row['mem_addr'],16)
            if pc==cls.spec['symbols']['main']+4:
                cls.snapshots['abi']=(deepcopy(state),dict(row))
            if state.current and state.current['trial']==481 and row['mem_rmask']!='00' and int(row['pc'],16)!=cls.spec['routine'][6]['pc']:
                chunk=(address-state.s['out'])//8
                if chunk in (0,1,32,64):cls.snapshots['output'+str(chunk)]=(deepcopy(state),dict(row))
            if not state.calls and address==state.s['a'] and int(row['mem_wmask'],16):
                cls.snapshots['setup']=(deepcopy(state),dict(row))
            if pc==cls.spec['routine'][0]['pc'] and len(state.calls)==1:
                cls.snapshots['call1']=(deepcopy(state),dict(row))
            state.consume(row)
        cls.result=state.finish()

    def test_full482_complete(self):
        self.assertEqual([self.result[k] for k in ('calls','results','guards','helper_instructions')],[482,246784,964,6266])

    def test_real_reset_abi_unknown_and_corrupt_store(self):
        state,row=self.snapshots['abi']
        for field,value in (('mem_wdata','0000000000000001'),('mem_wmask','0f'),('mem_addr','00000000800fffe8')):
            with self.subTest(field=field),self.assertRaises(ValueError):deepcopy(state).consume(dict(row,**{field:value}))
        state=deepcopy(state);del state.regs[8]
        with self.assertRaisesRegex(ValueError,'Unknown source GPR'):state.consume(row)

    def test_actual_setup_be_data_address(self):
        state,row=self.snapshots['setup']
        for field,value in (('mem_wmask','7f'),('mem_rmask','01'),('mem_addr',f'{int(row["mem_addr"],16)+8:016x}'),
                ('mem_wdata',f'{int(row["mem_wdata"],16)^1:016x}')):
            with self.subTest(field=field),self.assertRaises(ValueError):deepcopy(state).consume(dict(row,**{field:value}))

    def test_same_bytes_do_not_credit_missing_fresh_setup(self):
        state,row=self.snapshots['call1']
        for name in ('a','b','mask','out'):
            s=deepcopy(state);s.fresh[name].discard(0);s.fresh64[name].discard(0)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Missing fresh per-call setup'):s.consume(row)

    def test_complete_prestart_active_tail_and_guards(self):
        for chunk in (0,1,32,64):
            state,row=self.snapshots['output'+str(chunk)]
            for bit in ((0,8) if chunk in (0,64) else (0,)):
                with self.subTest(chunk=chunk,bit=bit),self.assertRaisesRegex(ValueError,'payload mismatch'):
                    deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^(1<<bit):016x}'))

    def test_unused_final_load_high_bytes_permitted(self):
        state,row=self.snapshots['output64']
        deepcopy(state).consume(dict(row,rd_wdata=f'{int(row["rd_wdata"],16)^(0xff<<56):016x}'))

    def test_unused_helper_scalar_pc_rejected(self):
        state,row=self.snapshots['call1']
        dis=(c.REF/'soc/program.dis').read_text()
        for n in range(1,8):
            for i in (6,12):
                instruction=c.instructions(dis,'op_'+str(n))[i]
                with self.subTest(op=n,index=i),self.assertRaisesRegex(ValueError,'unused original helper'):
                    deepcopy(state).consume(dict(row,pc=f'{instruction["pc"]:016x}',insn=f'{instruction["insn"]:08x}'))


if __name__=='__main__':unittest.main()
