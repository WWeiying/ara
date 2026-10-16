import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import masks
import memory
import widths
import combine
import floating
import context
import whole
import exceptions
import fixed
import reductions
import extensions
import narrow_overlap
import segments
import fp_widths
import index_widths
import fp_reduction_special
import recovery_prepare
import build
import integer_forms
import permutation
import fp_comparisons
import fp_moves
import segment_alignment
import fault_replay
import copy
import struct
import json
import hashlib
from fractions import Fraction
from unittest.mock import patch

class FamiliesTest(unittest.TestCase):
    def test_page_fault_replay_brackets_exact_instruction_and_keeps_vstart(self):
        for sew in (8,16,32,64):
            asm=fault_replay.assembly(sew)
            self.assertIn(f'fault_0_pc:\nvle{sew}.v v24,(a0),v0.t\ncsrr a0,vstart',asm)
            self.assertIn(f'fault_1_pc:\nvse{sew}.v v24,(a0),v0.t\ncsrr a0,vstart',asm)
            self.assertNotIn('csrw vstart',asm)
            self.assertEqual(asm.count('vlm.v v0,(a3)'),2)
        with self.assertRaises(ValueError):fault_replay.assembly(128)
        source=(ROOT/'fault_replay_oracle.c').read_text()
        self.assertIn('state->vstart!=expected_start',source)
        self.assertIn('info->si_code!=(unmapped ? SEGV_MAPERR:SEGV_ACCERR)',source)
        self.assertIn('if(++faults>1)',source)
        self.assertIn('if(active(i) && *(word *)field_address(i,f)!=input[f*cap+i])',source)
        self.assertIn('Keep the saved PC, vstart and vector register data unchanged',source)
        self.assertIn('#if NEGATIVE_RESTART\n    state->vstart=0;\n#endif',source)

    def test_indexed_fault_replay_loads_indices_before_faulting_instruction(self):
        for sew in (8,16,32,64):
            asm=fault_replay.assembly(sew,indexed=True)
            self.assertEqual(asm.count(f'vle{sew}.v v16,(a5)'),2)
            self.assertIn(f'fault_0_pc:\nvloxei{sew}.v v24,(a0),v16,v0.t\ncsrr a0,vstart',asm)
            self.assertIn(f'fault_1_pc:\nvsoxei{sew}.v v24,(a0),v16,v0.t\ncsrr a0,vstart',asm)
            self.assertNotIn('csrw vstart',asm)
        for boundary in (1,3,5):
            slots=[(i+1)%boundary if i<boundary else boundary+(i-boundary+1)%(8-boundary)
                   for i in range(8)]
            self.assertEqual(sorted(slots),list(range(8)))
            self.assertTrue(all(x<boundary for x in slots[:boundary]))
            self.assertTrue(all(x>=boundary for x in slots[boundary:]))
            self.assertNotEqual(slots,list(range(8)))

    def test_fault_replay_independent_index_eew_and_register_bounds(self):
        for sew in (8,16,32,64):
            for width in (8,16,32,64):
                asm=fault_replay.assembly(sew,True,width)
                self.assertEqual(asm.count(f'vle{width}.v v16,(a5)'),2)
                self.assertIn(f'fault_0_pc:\nvloxei{width}.v v24,(a0),v16,v0.t',asm)
                self.assertIn(f'fault_1_pc:\nvsoxei{width}.v v24,(a0),v16,v0.t',asm)
                # m1 data and index EMUL <=8: v16..v23 cannot overlap v24.
                self.assertLessEqual(width/sew,8)
                self.assertEqual(16 % max(1,width//sew),0)
                self.assertLessEqual(7*(sew//8),(1<<width)-1)
        with self.assertRaises(ValueError):fault_replay.assembly(32,False,8)
        with self.assertRaises(ValueError):fault_replay.assembly(32,True,128)

    def test_fault_replay_lmul_shapes_and_signal_capacity(self):
        shapes=[]
        for lmul,(num,den,code) in fault_replay.LMULS.items():
            for sew in (8,16,32,64):
                if sew*den>64*num:
                    with self.assertRaises(ValueError):fault_replay.assembly(sew,lmul=lmul)
                    continue
                shapes.append((sew,lmul))
                for indexed in (False,True):
                    asm=fault_replay.assembly(sew,indexed,lmul=lmul)
                    self.assertIn(f'vsetivli t0,8,e{sew},{lmul},tu,mu',asm)
                    self.assertEqual(24 % max(1,num//den),0)
                    self.assertEqual(16 % max(1,num//den),0)
                    self.assertLessEqual(24+max(1,num//den),32)
                    self.assertGreaterEqual(512*num//(sew*den),8)
        self.assertEqual(len(shapes),22)
        with self.assertRaises(ValueError):fault_replay.assembly(8,True,64,'m8')
        with self.assertRaises(ValueError):fault_replay.assembly(8,True,8,'bad')
        with self.assertRaises(ValueError):
            fault_replay.run(Path('/unused'),'unused-',indexed=True,index_sew=8,lmul='mf8')
        source=(ROOT/'fault_replay_oracle.c').read_text()
        self.assertIn('state->vlenb*LMUL_NUM!=cap*sizeof(word)*LMUL_DEN',source)
        self.assertIn('cap>CAPACITY_LIMIT',source)
        self.assertIn('output[CAPACITY_LIMIT*REPLAY_FIELDS+2]',source)

    def test_segment_fault_replay_all_fields_and_partial_fault_boundaries(self):
        for fields in range(2,9):
            for sew in (8,16,32,64):
                asm=fault_replay.assembly(sew,fields=fields)
                self.assertIn(f'fault_0_pc:\nvlseg{fields}e{sew}.v v24,(a0),v0.t\ncsrr a0,vstart',asm)
                self.assertIn(f'fault_1_pc:\nvsseg{fields}e{sew}.v v24,(a0),v0.t\ncsrr a0,vstart',asm)
                for f in range(fields):
                    self.assertIn(f'vle{sew}.v v{24+f},(t1)',asm)
                    self.assertIn(f'vse{sew}.v v{24+f},(t1)',asm)
                self.assertLessEqual(24+fields,32)
                for boundary in (1,3,5):
                    for split in (0,fields//2):
                        base=4096-(boundary*fields+split)*(sew//8)
                        for i in range(boundary):
                            self.assertLess(base+(i*fields+fields-1)*(sew//8),4096)
                        self.assertLessEqual(base+boundary*fields*(sew//8),4096)
                        self.assertGreaterEqual(base+(boundary*fields+fields-1)*(sew//8),4096)
        with self.assertRaises(ValueError):fault_replay.assembly(8,fields=9)
        self.assertIn('vloxseg2ei8.v v24,(a0),v16,v0.t',
                      fault_replay.assembly(8,True,fields=2))
        with self.assertRaises(ValueError):fault_replay.assembly(8,lmul='m8',fields=2)

    def test_segment_fault_replay_lmul_group_stride_and_legal_domain(self):
        shapes=0
        for nf in range(2,9):
            for lmul,(num,den,_) in fault_replay.LMULS.items():
                for sew in (8,16,32,64):
                    legal=sew<=64*Fraction(num,den) and nf*Fraction(num,den)<=8
                    if not legal:
                        with self.assertRaises(ValueError):fault_replay.assembly(sew,lmul=lmul,fields=nf)
                        continue
                    shapes+=1
                    asm=fault_replay.assembly(sew,lmul=lmul,fields=nf)
                    stride=max(1,num//den)
                    self.assertLessEqual(24+nf*stride,32)
                    for f in range(nf):
                        register=24+f*stride
                        self.assertEqual(register%stride,0)
                        self.assertIn(f'vle{sew}.v v{register},(t1)',asm)
                        self.assertIn(f'vse{sew}.v v{register},(t1)',asm)
        self.assertEqual(shapes,86)

    def test_indexed_segment_fault_domains_and_narrow_index_limits(self):
        shapes=0
        for nf in range(2,9):
            for lmul,(num,den,_) in fault_replay.LMULS.items():
                for sew in (8,16,32,64):
                    for width in (8,16,32,64):
                        emul=Fraction(width,sew)*Fraction(num,den)
                        legal=(sew<=64*Fraction(num,den) and
                               nf*Fraction(num,den)<=8 and Fraction(1,8)<=emul<=8)
                        if not legal:
                            with self.assertRaises(ValueError):
                                fault_replay.assembly(sew,True,width,lmul,nf)
                            continue
                        shapes+=1
                        vl=max(n for n in range(1,9) if (n-1)*nf*(sew//8)<(1<<width))
                        self.assertEqual(vl,fault_replay.replay_elements(sew,True,width,nf))
                        asm=fault_replay.assembly(sew,True,width,lmul,nf)
                        self.assertIn(f'vsetivli t0,{vl},e{sew},{lmul}',asm)
                        self.assertIn(f'vloxseg{nf}ei{width}.v v24,(a0),v16,v0.t',asm)
                        self.assertIn(f'vsoxseg{nf}ei{width}.v v24,(a0),v16,v0.t',asm)
                        for boundary in (b for b in (1,3,5) if b<vl):
                            slots=[(i+1)%boundary if i<boundary else boundary if i==boundary
                                   else boundary+1+(i-boundary)%(vl-boundary-1) for i in range(vl)]
                            self.assertEqual(sorted(slots),list(range(vl)))
                            self.assertEqual(slots[boundary],boundary)
                            self.assertTrue(all(s<boundary for s in slots[:boundary]))
                            self.assertTrue(all(s>=boundary for s in slots[boundary:]))
                            self.assertLess(max(slots)*nf*(sew//8),1<<width)
        self.assertEqual(shapes,338)
        self.assertEqual([fault_replay.replay_elements(64,True,8,nf) for nf in (5,6,7,8)],
                         [7,6,5,4])

    def test_strided_fault_replay_all_legal_shapes(self):
        from fractions import Fraction
        count=0
        for fields in range(1,9):
            for lmul,(num,den,_) in fault_replay.LMULS.items():
                for sew in (8,16,32,64):
                    legal=sew<=64*Fraction(num,den) and fields*Fraction(num,den)<=8
                    if not legal:
                        with self.assertRaises(ValueError):
                            fault_replay.assembly(sew,lmul=lmul,fields=fields,strided=True)
                        continue
                    count+=1
                    asm=fault_replay.assembly(sew,lmul=lmul,fields=fields,strided=True)
                    op=f'vlsseg{fields}e{sew}.v' if fields>1 else f'vlse{sew}.v'
                    self.assertIn(op+' v24,(a0),t3,v0.t',asm)
                    self.assertIn('ld t3,0(a5)',asm)
                    self.assertLess(asm.index('ld t3,0(a5)'),asm.index('fault_0_pc:'))
                    self.assertIn('csrr a0,vstart',asm)
        self.assertEqual(count,108)
        with self.assertRaises(ValueError):
            fault_replay.assembly(8,indexed=True,strided=True)
        source=(ROOT/'fault_replay_oracle.c').read_text()
        self.assertIn('stride=(REPLAY_FIELDS+gap)*sizeof(word)',source)
        self.assertIn('target=mapping+4096-boundary*stride-accessible_fields*sizeof(word)',source)

    def test_negative_stride_fault_page_and_invalid_mode(self):
        source=(ROOT/'fault_replay_oracle.c').read_text()
        self.assertIn('#define PROTECTED_PAGE mapping',source)
        self.assertIn('target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word)',source)
        self.assertIn('stride=-stride',source)
        self.assertIn('call(unmapped ? 215:226,PROTECTED_PAGE',source)
        self.assertIn('fill(PROTECTED_PAGE)',source)
        with self.assertRaises(ValueError):
            fault_replay.run(Path('/unused'),'unused-',negative_stride=True)

    def test_negative_stride_layout_preserves_complete_prefix_and_gaps(self):
        for nf in range(1,9):
            for size in (1,2,4,8):
                for gap in (1,3):
                    for boundary in (1,3,5):
                        for accessible in ((0,nf//2) if nf>1 else (0,)):
                            step=(nf+gap)*size
                            base=4096+boundary*step-(nf-accessible)*size
                            addresses=[base-i*step+f*size for i in range(8) for f in range(nf)]
                            self.assertEqual(len(set(addresses)),8*nf)
                            self.assertTrue(all(0<=a and a+size<=8192 for a in addresses))
                            self.assertTrue(all(base-i*step>=4096 for i in range(boundary)))
                            fields=[base-boundary*step+f*size for f in range(nf)]
                            self.assertEqual(sum(a>=4096 for a in fields),accessible)
                            self.assertTrue(all(base-i*step+(nf-1)*size<4096
                                                for i in range(boundary+1,8)))

    def test_fault_replay_complete_index_emul_legality(self):
        legal=0
        for lmul,(num,den,_) in fault_replay.LMULS.items():
            ratio=Fraction(num,den)
            for sew in (8,16,32,64):
                for width in (8,16,32,64):
                    emul=ratio*Fraction(width,sew)
                    valid=sew<=64*ratio and Fraction(1,8)<=emul<=8
                    if not valid:
                        with self.assertRaises(ValueError):
                            fault_replay.assembly(sew,True,width,lmul)
                        continue
                    legal+=1
                    asm=fault_replay.assembly(sew,True,width,lmul)
                    group=max(1,int(emul))
                    self.assertEqual(16%group,0)
                    self.assertLessEqual(16+group,24)
                    self.assertIn(f'vloxei{width}.v v24,(a0),v16,v0.t',asm)
        self.assertEqual(legal,78)

    def test_segment_independent_index_widths_and_unique_byte_domain(self):
        for width in (8,16,64):
            asm=segments.assembly(32,'m1',indexed=True,restart=True,index_sew=width)
            self.assertIn(f'vle{width}.v v16,(a5)',asm)
            self.assertIn(f'vluxseg2ei{width}.v',asm)
        source=(ROOT/'segment_oracle.c').read_text()
        self.assertIn('while(bounded<=limit/2)bounded*=2;',source)
        self.assertIn('if(vl>cap)vl=cap;',source)
        with self.assertRaises(ValueError):
            segments.run(Path('/unused'),'unused-',index_sew=8)

    def test_index_width_restart_applied_after_index_setup(self):
        asm=index_widths.assembly(32,'m2',restart=True)
        self.assertIn('csrw vstart,a6\nvluxei8.v',asm)
        self.assertIn('csrw vstart,a6\nvsoxei64.v',asm)
        self.assertNotIn('csrw vstart',index_widths.assembly(32,'m2'))
        source=(ROOT/'index_width_oracle.c').read_text()
        self.assertIn('for(unsigned i=start;i<vl;++i)',source)
        self.assertIn('(vl<=max_start ? vl:cap-1)',source)

    def test_segment_restart_survives_address_setup(self):
        asm=segments.assembly(32,'m2',indexed=True,restart=True)
        self.assertIn('mv t5,a6',asm)
        self.assertIn('csrw vstart,t5\nvluxseg2ei32.v',asm)
        self.assertIn('csrw vstart,t5\nvsoxseg2ei32.v',asm)
        self.assertNotIn('csrw vstart',segments.assembly(32,'m2',indexed=True))
        source=(ROOT/'segment_oracle.c').read_text()
        self.assertIn('for(unsigned i=start;i<vl;++i)',source)
        with self.assertRaises(ValueError):
            segments.run(Path('/unused'),'unused-',misaligned=True,restart=True)

    def test_memory_restart_stack_argument_is_applied_after_all_setup_loads(self):
        asm=memory.assembly(32,'m2',restart=True)
        segment=asm.split('op_9:')[1]
        self.assertIn('ld t4,0(sp)',segment)
        self.assertLess(segment.index('vle32.v v10,(a7)'),segment.index('csrw vstart,t4'))
        self.assertIn('csrw vstart,t4\nvsseg2e32.v v8,(a2),v0.t',segment)
        self.assertNotIn('csrw vstart',memory.assembly(32,'m2'))
        source=(ROOT/'memory_oracle.c').read_text()
        self.assertIn('for(unsigned i=start;i<vl;++i)',source)
        self.assertIn('i>=start && i<vl && selected(mode,i)',source)

    def test_permutation_restart_keeps_full_xlen_scalar_separate(self):
        asm=permutation.assembly(8,'m8',restart=True)
        self.assertIn('mv t3,a6\ncsrw vstart,a7\nvslideup.vx',asm)
        self.assertIn('csrw vstart,a7\nvmerge.vvm',asm)
        self.assertNotIn('csrw vstart',permutation.assembly(32,'m1'))
        source=(ROOT/'permutation_oracle.c').read_text()
        self.assertIn('i>=start && i<vl',source)
        self.assertIn('(vl<=max_start ? vl:cap-1)',source)

    def test_integer_mask_restart_and_overlap_inactive_policy(self):
        asm=masks.assembly(32,'m2',comparison_aliases=True,restart=True)
        self.assertIn('csrw vstart,a6\nvmseq.vv v8,v8,v16,v0.t',asm)
        self.assertIn('csrw vstart,a6\nvmseq.vv v16,v8,v16,v0.t',asm)
        self.assertNotIn('csrw vstart',masks.assembly(32,'m2'))
        source=(ROOT/'mask_oracle.c').read_text()
        self.assertIn('COMPARISON_ALIASES && actual==1',source)
        self.assertIn('start>=vl || i<start',source)
        self.assertIn('(vl<=max_start ? vl:cap-1)',source)
        with self.assertRaises(ValueError):
            masks.assembly(8,'m1',restart=True)
        logic=masks.assembly(8,'m8',aliases=True,restart=True)
        self.assertIn('csrw vstart,a6\nvmand.mm v8,v8,v16',logic)
        self.assertIn('csrw vstart,a6\nvmand.mm v16,v8,v16',logic)
        self.assertNotIn('v0.t',logic)

    def test_fp_compare_restart_preserves_prestart_and_no_body(self):
        asm=fp_comparisons.assembly(16,'m8',restart=True)
        self.assertIn('csrw fflags,a7\ncsrw vstart,a6\nvmfeq.vv',asm)
        self.assertNotIn('csrw vstart',fp_comparisons.assembly(32,'m1'))
        source=(ROOT/'fp_compare_oracle.c').read_text()
        self.assertIn('start>=vl || i<start',source)
        self.assertIn('i>=start && i<vl',source)
        with self.assertRaises(ValueError):
            fp_comparisons.assembly(32,'m1',destination='v8',restart=True)

    def test_fixed_restart_oracle_uses_architectural_vstart_limit(self):
        source=(ROOT/'oracle.c').read_text()
        self.assertIn('csrr %0,vlenb',source)
        self.assertIn('max_start=max_start*8-1;',source)
        self.assertIn('(vl<=max_start ? vl:cap-1)',source)
        self.assertIn('if(op==0 && seed==0 && mode==0 && rm==0 && accumulator==0)',source)
        asm=build.assembly(8,'m8',extra=True,operations=fixed.SCALAR_OPS,
                           sticky_sat=True,scalar_from_input=True)
        self.assertIn('csrw vstart, a6',asm)
        self.assertIn('andi t2, a7, 3',asm)

    def test_segment_alignment_setup_and_readback_are_separate_from_target(self):
        asm=segment_alignment.assembly(32,'m2')
        self.assertIn('vle32.v v24,(t2)',asm)
        self.assertIn('vle32.v v8,(t2)',asm)
        self.assertIn('sd t3,0(a7)\nvlseg3e32.v v24,(a5),v0.t',asm)
        self.assertIn('vssseg4e32.v v8,(a5),a6,v0.t',asm)
        self.assertNotIn('vle32.v v24,(a5)',asm)
        self.assertNotIn('vse32.v v24,(a5)',asm)

    def test_fp_move_restart_is_written_after_setup_and_before_instruction(self):
        asm=fp_moves.assembly(32,'m2',restart=True)
        self.assertIn('srli t2,a6,32\ncsrw fflags,t2',asm)
        self.assertIn('csrw vstart,t2\nvfmerge.vfm',asm)
        self.assertIn('csrw vstart,t2\nvfmv.s.f',asm)
        self.assertIn('csrw vstart,t2\nvfmv.f.s',asm)
        self.assertNotIn('csrw vstart',fp_moves.assembly(32,'m2'))

    def test_fp_compare_aliases_preserve_source_preimages_and_unmasked_form(self):
        for destination in ('v8','v16','v0'):
            asm=fp_comparisons.assembly(32,'m4',destination=destination)
            self.assertIn('vmfeq.vv '+destination+',v8,v16,v0.t',asm)
            self.assertIn('vsm.v '+destination+',(a2)',asm)
            self.assertNotIn('vlm.v v24',asm)
        asm=fp_comparisons.assembly(16,'m2',unmasked=True)
        self.assertIn('vlm.v v0,(a5)',asm)
        self.assertNotIn('v0.t',asm)
        self.assertIn('vmfeq.vf v24,v8,ft0\n',asm)
        with self.assertRaises(ValueError):
            fp_comparisons.assembly(32,'m1',destination='v9')

    def test_fp_moves_distinguish_selector_predicate_and_unmasked_encodings(self):
        asm=fp_moves.assembly(16,'m2')
        self.assertIn('vfmerge.vfm v24,v8,ft0,v0\n',asm)
        self.assertIn('vfslide1up.vf v24,v8,ft0,v0.t\n',asm)
        self.assertIn('vfslide1down.vf v24,v8,ft0\n',asm)
        self.assertIn('vfmv.s.f v24,ft0\n',asm)
        self.assertIn('vfmv.f.s ft1,v8\nfmv.x.d t2,ft1\nsd t2,0(a7)',asm)
        self.assertIn('fld ft0,0(a1)',asm)
        self.assertNotIn('vfmv.s.f v24,ft0,v0',asm)

    def test_fp_comparison_invalid_boxing_is_not_sign_extended_or_reboxed(self):
        for sew,load in ((16,'lhu'),(32,'lwu')):
            for destination in ('v24','v8','v16','v0'):
                for unmasked in (False,True):
                    asm=fp_comparisons.assembly(sew,'m1',unmasked,
                                                 destination,unboxed=True)
                    self.assertEqual(asm.count(load+' t2,0(a1)\nfmv.d.x ft0,t2'),6)
                    self.assertNotIn('or t2,t2,t3',asm)
                    self.assertNotIn('flw ft0',asm)
                    self.assertIn(f'vmfeq.vf {destination},v8,ft0',asm)
        with self.assertRaises(ValueError):
            fp_comparisons.assembly(64,'m1',unboxed=True)
        source=(ROOT/'fp_compare_oracle.c').read_text()
        self.assertIn('if(UNBOXED_COMPARISONS && op>=4)bi=14;',source)

    def test_unmasked_fp_comparison_alias_cross_product(self):
        for sew,lmul in build.shapes():
            if sew == 8:
                continue
            for destination in ('v8','v16','v0'):
                asm=fp_comparisons.assembly(sew,lmul,unmasked=True,
                                             destination=destination)
                self.assertNotIn('v0.t',asm)
                self.assertNotIn('vlm.v v24',asm)
                self.assertEqual(asm.count('vlm.v v0,(a5)'),10)
                self.assertEqual(asm.count(f'vsm.v {destination},(a2)'),10)
                for i,opcode in enumerate(fp_comparisons.OPS):
                    rhs='v16' if i<4 else 'ft0'
                    self.assertIn(f'{opcode} {destination},v8,{rhs}\n',asm)

    def test_fp_comparisons_packed_mask_flags_and_scalar_boxing(self):
        self.assertEqual(len(fp_comparisons.OPS),10)
        for sew in (16,32,64):
            asm=fp_comparisons.assembly(sew,'m1')
            for opcode in fp_comparisons.OPS:
                self.assertIn(opcode+' v24,v8,'+('v16' if opcode.endswith('.vv') else 'ft0')+',v0.t',asm)
            self.assertIn('vlm.v v24,(a2)',asm)
            self.assertIn('vsm.v v24,(a2)',asm)
            self.assertIn('csrw fflags,a7',asm)
            self.assertLess(asm.index('csrr t1,fflags'),asm.index('csrw fflags,t5'))
        self.assertIn('slli t3,t3,16',fp_comparisons.assembly(16,'m1'))

    def test_accumulator_patterns_require_multiply_add(self):
        with self.assertRaises(ValueError):
            integer_forms.run(Path('unused'),'',accumulators=True)
        source=(ROOT/'oracle.c').read_text()
        self.assertIn('uint64_t old=old_destination;',source)
        self.assertIn('out[i+1]=initial_destination(accumulator,i);',source)
        self.assertIn('word expected=initial_destination(accumulator,i);',source)

    def test_macc_source_aliases_preserve_old_destination_inputs(self):
        for alias, count in (('first',8),('second',4),('both',4)):
            ops=integer_forms.macc_operations(alias)
            self.assertEqual(len(ops),count)
            asm=integer_forms.assembly(64,'m8',ops)
            for op,args in ops:
                self.assertIn(f'{op} v24, {args}, v0.t',asm)
                if alias in ('first','both'):
                    self.assertNotIn('v8',args)
                if alias in ('second','both'):
                    self.assertNotIn('v16',args)
                    self.assertTrue(op.endswith('.vv'))
            self.assertLess(asm.index('vle64.v v24, (a2)'),asm.index('csrw vstart, a6'))
        with self.assertRaises(ValueError):
            integer_forms.run(Path('unused'),'',alias_source='first')
        with self.assertRaises(ValueError):
            integer_forms.run(Path('unused'),'',multiply_add=True,alias_source='bad')
        source=(ROOT/'oracle.c').read_text()
        self.assertIn('x=old_destination;',source)
        self.assertIn('vector_y=old_destination;',source)

    def test_macc_restart_is_after_setup_and_captured_before_readback(self):
        with self.assertRaises(ValueError):
            integer_forms.run(Path('unused'),'',restart=True)
        asm=integer_forms.assembly(8,'m8',integer_forms.macc_operations('both'))
        target='vmacc.vv v24, v24, v24, v0.t'
        self.assertLess(asm.index('vlm.v v0, (a5)'),asm.index('csrw vstart, a6'))
        self.assertLess(asm.index('csrw vstart, a6'),asm.index(target))
        self.assertLess(asm.index(target),asm.index('csrr a0, vstart'))
        self.assertLess(asm.index('csrr a0, vstart'),asm.index('vse8.v v24, (a2)'))
        source=(ROOT/'oracle.c').read_text()
        self.assertIn('i<vl && i>=start',source)
        self.assertIn('max_start=max_start*8-1;',source)

    def test_fp_move_failure_classification_is_opt_in_and_bounded(self):
        with self.assertRaises(ValueError):
            fp_moves.run(Path('unused'),'',details=True)
        with self.assertRaises(ValueError):
            fp_moves.run(Path('unused'),'',restart=True,details=True,only=['e8_m1'])
        source=(ROOT/'fp_move_oracle.c').read_text()
        self.assertIn('RVV_FP_MOVE_CLASSIFY returned_vstart=',source)
        self.assertIn('if(first_bad==cap)',source)
        self.assertIn('details++<20',source)
        self.assertIn('num((uint32_t)status)',source)

    def test_macc_chains_are_adjacent_and_expand_once(self):
        ops=integer_forms.macc_operations('both')
        for mixed in (False,True):
            asm=integer_forms.assembly(32,'m4',ops,chain_steps=3,mixed_chain=mixed)
            for i in range(4):
                body=asm.split(f'op_{i}:\n')[1].split('ret\n')[0]
                targets=[line for line in body.splitlines() if line.startswith(('vmacc.','vnmsac.','vmadd.','vnmsub.'))]
                expected=[integer_forms.MACC_OPS[(i+step)%4][0] if mixed else ops[i][0] for step in range(3)]
                self.assertEqual(targets,[f'{op} v24, v24, v24, v0.t' for op in expected])
                self.assertIn('\n'.join(targets),body)
                self.assertEqual(body.count('vle32.v v24'),1)
                self.assertEqual(body.count('csrw vstart'),1)
        vx=integer_forms.assembly(64,'m8',integer_forms.macc_operations('first'),True,3,True)
        self.assertIn('vmacc.vx v24, t3, v24\nvnmsac.vx v24, t3, v24\nvmadd.vx v24, t3, v24\n',vx)

    def test_macc_chain_invalid_combinations_fail_before_filesystem(self):
        for kwargs in ({'chain_steps':0},{'chain_steps':9},{'mixed_chain':True},
                       {'chain_steps':3},{'multiply_add':True,'chain_steps':3,'restart':True}):
            with self.assertRaises(ValueError):
                integer_forms.run(Path('unused'),'',**kwargs)
        with self.assertRaises(ValueError):
            integer_forms.assembly(8,'m1',integer_forms.CARRY_OPS,chain_steps=3)
        source=(ROOT/'oracle.c').read_text()
        self.assertIn('expected=scalar_value(chain_op,a[i],b[i],selected(mode,i),expected);',source)

    def test_permutation_scalar_width_and_mask_semantics(self):
        asm=permutation.assembly(8,'m4')
        self.assertIn('mv t3,a6',asm)
        self.assertIn('vrgatherei16.vv v24,v8,v16,v0.t',asm)
        self.assertIn('vle16.v v16,(a1)',asm)
        self.assertIn('vmerge.vxm v24,v8,t3,v0\n',asm)
        self.assertIn('vmv.v.x v24,t3\n',asm)
        self.assertIn('vslideup.vi v24,v8,31,v0.t',asm)
        self.assertNotIn('vrgatherei16',permutation.assembly(8,'m8'))
        self.assertEqual(len(permutation.operations(8,'m8')),20)
        self.assertEqual(len(permutation.operations(64,'m1')),21)

    def test_mask_carry_has_optional_input_without_execution_predication(self):
        asm=masks.assembly(64,'m2',carry_forms=True)
        self.assertEqual(len(masks.CARRY_SPECS),12)
        self.assertNotIn('v0.t',asm)
        self.assertIn('ld t3,0(a1)',asm)
        for opcode,args,_,_,_,carry in masks.CARRY_SPECS:
            self.assertIn(opcode+' v24,'+args+(',v0' if carry else '')+'\n',asm)
        with self.assertRaises(ValueError):
            masks.run(Path('unused'),'',aliases=True,carry_forms=True)

    def test_data_carry_uses_v0_as_operand_not_execution_mask(self):
        asm=integer_forms.assembly(16,'m2',integer_forms.CARRY_OPS)
        self.assertNotIn('v0.t',asm)
        for opcode,args in integer_forms.CARRY_OPS:
            self.assertIn(opcode+' v24, '+args+', v0',asm)
        with self.assertRaises(ValueError):
            integer_forms.assembly(16,'m2',integer_forms.CARRY_OPS,unmasked=True)
        with self.assertRaises(ValueError):
            integer_forms.run(Path('unused'),'',unmasked=True,carry=True)

    def test_unmasked_integer_forms_keep_predicate_load_but_not_mask_encoding(self):
        for operations in (integer_forms.OPS,integer_forms.MACC_OPS,integer_forms.IMMEDIATE_OPS):
            asm=integer_forms.assembly(32,'m2',operations,unmasked=True)
            self.assertIn('vlm.v v0, (a5)',asm)
            self.assertNotIn('v0.t',asm)
            self.assertIn('v0.t',integer_forms.assembly(32,'m2',operations))

    def test_integer_immediates_distinguish_signed_and_unsigned_fields(self):
        self.assertEqual(len(integer_forms.IMMEDIATE_SPECS),16)
        asm=build.assembly(8,'mf8',operations=integer_forms.IMMEDIATE_OPS)
        for opcode,_,immediate in integer_forms.IMMEDIATE_SPECS:
            self.assertIn(opcode+'.vi v24, v8, '+str(immediate)+', v0.t',asm)
            self.assertIn(immediate,(0,31) if opcode.startswith('vs') else (-16,15))
        with self.assertRaises(ValueError):
            integer_forms.run(Path('unused'),'',multiply_add=True,immediate=True)

    def test_integer_multiply_add_operand_order(self):
        self.assertEqual(len(integer_forms.MACC_OPS),8)
        asm=build.assembly(32,'m2',operations=integer_forms.MACC_OPS,scalar_from_input=True)
        for opcode in ('vmacc','vnmsac','vmadd','vnmsub'):
            self.assertIn(opcode+'.vv v24, v8, v16, v0.t',asm)
            self.assertIn(opcode+'.vx v24, t3, v8, v0.t',asm)

    def test_integer_scalar_forms_match_oracle_order_and_signed_loads(self):
        self.assertEqual(len(integer_forms.OPS),21)
        self.assertEqual([op for op,_ in integer_forms.OPS[:17]],
                         [op.replace('.vv','.vx') for op,_ in build.OPS[:17]])
        self.assertEqual([op for op,_ in integer_forms.OPS[17:]],
                         ['vrsub.vx','vmulhu.vx','vmulh.vx','vmulhsu.vx'])
        for sew,load in ((8,'lb'),(16,'lh'),(32,'lw'),(64,'ld')):
            asm=build.assembly(sew,'m1',operations=integer_forms.OPS,scalar_from_input=True)
            self.assertIn(load+' t3, 0(a1)',asm)
            for opcode,args in integer_forms.OPS:
                self.assertIn(opcode+' v24, '+args+', v0.t',asm)

    def test_destructive_fma_scalar_and_vector_operand_order(self):
        vv=floating.assembly(32,'m2',destructive=True)
        vf=floating.assembly(32,'m2',scalar_forms=True,destructive=True)
        for opcode in floating.DESTRUCTIVE_OPS:
            self.assertIn(opcode+' v24,v8,v16,v0.t',vv)
            self.assertIn(opcode.replace('.vv','.vf')+' v24,ft0,v8,v0.t',vf)

    def test_comparison_mask_aliases_are_masked_and_alias_each_source(self):
        asm=masks.assembly(32,'m4',comparison_aliases=True)
        self.assertIn('vmseq.vv v8,v8,v16,v0.t',asm)
        self.assertIn('vmseq.vv v16,v8,v16,v0.t',asm)
        self.assertNotIn('vlm.v v24',asm)
        self.assertEqual(asm.count('vsm.v v8,(a2)'),6)
        self.assertEqual(asm.count('vsm.v v16,(a2)'),6)

    def test_unboxed_fp_scalar_does_not_accidentally_nan_box(self):
        for sew,load in ((16,'lhu'),(32,'lwu')):
            asm=floating.assembly(sew,'m1',scalar_extras=True,unboxed=True)
            self.assertIn(load+' t2,0(a1)',asm)
            self.assertIn('fmv.d.x ft0,t2',asm)
            self.assertNotIn('flw',asm)
            self.assertNotIn('slli t3,t3,16',asm)
        with self.assertRaises(ValueError):
            floating.assembly(64,'m1',scalar_extras=True,unboxed=True)

    def test_scalar_extra_fp_forms_have_vector_then_scalar_operands(self):
        asm=floating.assembly(16,'m1',scalar_extras=True)
        for opcode in floating.SCALAR_EXTRA_OPS:
            self.assertIn(opcode+' v24,v8,ft0,v0.t',asm)
        self.assertIn('fmv.d.x ft0,t2',asm)
        self.assertEqual(len(floating.operations_for(scalar_extras=True)),7)

    def test_queued_first_continuation_preserves_all_unique_pending_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            base=root/'base';base.write_bytes(b'root')
            dtb=root/'dtb';dtb.write_bytes(b'dtb')
            firmware=root/'firmware';firmware.write_bytes(b'firmware')
            report=root/'report';report.write_text('{"results":[]}')
            cases=[];releases=[]
            for name in ('old_pending','queued_first'):
                release=root/name;(release/'binaries').mkdir(parents=True)
                elf=release/'binaries'/name;elf.write_bytes(name.encode());elf.chmod(0o755)
                package=release/'width_tests.tgz';package.write_bytes(b'package')
                case=dict(name=name,sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),pass_marker='PASS')
                manifest=dict(cases=[case],reference_passed=True,reference_vlens=[512,1024],
                              archive_sha256=hashlib.sha256(package.read_bytes()).hexdigest())
                (release/'transfer_manifest.json').write_text(json.dumps(manifest))
                cases.append(case);releases.append(release)
            for index,(defer,batch,prefer,order) in enumerate((((),False,(),None),(('queued_',),False,(),None),
                    ((),True,(),None),((),True,('old_',),None),(('queued_',),True,('queued_',),None),
                    (('queued_',),True,('old_',),['queued_first','old_pending']),
                    ((),True,(),['queued_first']),((),True,(),None))):
                out=root/f'out{index}'
                if index==7:
                    path=releases[1]/'transfer_manifest.json'
                    restricted=json.loads(path.read_text())
                    restricted.update(reference_vlens=[1024],required_vlen_bits=1024)
                    path.write_text(json.dumps(restricted))
                pending=[] if index==6 else [cases[0]]
                with patch.object(recovery_prepare,'remaining',return_value=pending), \
                     patch.object(recovery_prepare.subprocess,'run') as run, \
                     patch.object(recovery_prepare.subprocess,'check_output',side_effect=[b'0 88000000',b'0 88000004']), \
                     patch.object(recovery_prepare,'patch_embedded_dtb',return_value=b'firmware'):
                    recovery_prepare.prepare(out,base,dtb,firmware,releases[0],report,[releases[1]],True,defer,batch,prefer,
                                             execution_order=order)
                merged=json.loads((out/'resume/transfer_manifest.json').read_text())
                execution=merged['cases']
                if index==7:
                    self.assertEqual(merged['reference_vlens'],[1024])
                    self.assertEqual(merged['required_vlen_bits'],1024)
                    self.assertEqual(recovery_prepare.reference_coverage(merged),{1024})
                else:
                    self.assertEqual(merged['reference_vlens'],[512,1024])
                expected = [cases[0],cases[1]] if defer or prefer==('old_',) else [cases[1],cases[0]]
                if order is not None:
                    expected = [next(c for c in cases if c['name']==name) for name in order]
                self.assertEqual(execution,expected)
                self.assertEqual(len(list((out/'resume/binaries').iterdir())),len(expected))
                self.assertEqual((out/'previous_report.json').read_bytes(),report.read_bytes())
                provenance=json.loads((out/'recovery.json').read_text())
                if order is not None:
                    self.assertEqual(provenance['explicit_execution_order'],order)
                self.assertEqual(provenance['pending_in_stalled_batch'],len(pending))
                self.assertEqual(provenance['deferred_cases'],['queued_first'] if defer else [])
                self.assertEqual(provenance['prioritized_prefixes'],list(prefer))
                self.assertEqual(provenance['prioritized_cases'],[c['name'] for c in execution if c['name'].startswith(prefer)])
                if batch:
                    protocol=json.loads((out/'resume/batch_protocol.json').read_text())
                    self.assertEqual(protocol['inputs']['cases'],execution)
                    self.assertEqual(protocol['inputs']['archive_sha256'],
                                     recovery_prepare.digest(out/'resume/width_tests.tgz'))
                    preloaded=out/'overlay'/provenance['guest_batch']['script_path'].lstrip('/')
                    self.assertEqual(preloaded.read_bytes(),(out/'resume/batch.sh').read_bytes())
                    self.assertTrue(preloaded.stat().st_mode&0o111)
                    self.assertEqual(protocol['script_sha256'],recovery_prepare.digest(preloaded))
                    self.assertIn('batch.sh',run.call_args_list[0].kwargs['input'].decode())
                    self.assertFalse(protocol['board_task_started'])
                    self.assertFalse(provenance['guest_batch']['observer_adapter_required'])
                    expected_modules={'width_suite.py','batch_serial.py','guest_batch.py','guest_watch.py'}
                    self.assertEqual(set(provenance['guest_batch']['observer_sha256']),expected_modules)
                    for name,sha in provenance['guest_batch']['observer_sha256'].items():
                        self.assertEqual(recovery_prepare.digest(out/'resume'/name),sha)
                    from batch_serial import verify
                    checked,_=verify(out/'resume')
                    self.assertEqual(checked['cases'],execution)
                else:
                    self.assertNotIn('guest_batch',provenance)
                    self.assertFalse((out/'resume/batch.sh').exists())
                    self.assertFalse((out/'resume/width_suite.py').exists())

    def test_recovery_deferral_rejects_partial_execution_and_empty_prefix(self):
        for queued_first,prefixes in ((False,['rvv_fp_']),(True,[''])):
            with self.assertRaises(ValueError):
                recovery_prepare.prepare(Path('unused'),None,None,None,None,None,[],queued_first,prefixes)

    def test_recovery_priority_rejects_partial_execution_and_empty_prefix(self):
        for queued_first,prefixes in ((False,['rvv_macc_']),(True,[''])):
            with self.assertRaises(ValueError):
                recovery_prepare.prepare(Path('unused'),None,None,None,None,None,[],queued_first,
                                         prioritize_prefixes=prefixes)

    def test_fixed_scalar_forms_use_real_scalar_and_distinct_oracles(self):
        asm=build.assembly(16,'m2',extra=True,operations=fixed.SCALAR_OPS,
                           sticky_sat=True,scalar_from_input=True)
        self.assertIn('lh t3, 0(a1)',asm)
        self.assertIn('vsmul.vx v24, v8, t3, v0.t',asm)
        self.assertIn('vsadd.vi v24, v8, -3, v0.t',asm)
        self.assertEqual(len(fixed.SCALAR_OPS),len(fixed.SCALAR_ORACLE))
        self.assertEqual(fixed.SCALAR_ORACLE[:5],[20,4,3,6,5])

    def test_embedded_dtb_patch_cannot_touch_executable_segments(self):
        header=struct.pack('<16sHHIQQQIHHHHHH',b'\x7fELF\x02\x01'+b'\0'*10,
                           2,243,1,0,64,128,0,64,56,1,64,1,0)
        segment=struct.pack('<IIQQQQQQ',1,4,120,0,0,8,8,8)
        original=b'dtb-old!';replacement=b'dtb-new!'
        section=struct.pack('<IIQQQQIIQQ',0,1,2,0,120,8,0,0,1,0)
        elf=header+segment+original+section
        changed=recovery_prepare.patch_embedded_dtb(elf,original,replacement)
        self.assertEqual(changed[:120],elf[:120])
        self.assertEqual(changed[120:128],replacement)
        self.assertEqual(changed[128:],elf[128:])
        executable=header+segment+original+struct.pack('<IIQQQQIIQQ',0,1,6,0,120,8,0,0,1,0)
        with self.assertRaises(ValueError):
            recovery_prepare.patch_embedded_dtb(executable,original,replacement)
        with self.assertRaises(ValueError):
            recovery_prepare.patch_embedded_dtb(elf+original,original,replacement)

    def test_fp_scalar_operand_order_and_half_nan_boxing(self):
        asm=floating.assembly(16,'m8',scalar_forms=True)
        self.assertIn('fmv.d.x ft0,t2',asm)
        self.assertIn('slli t3,t3,16',asm)
        self.assertIn('vfsub.vf v24,v8,ft0,v0.t',asm)
        self.assertIn('vfmacc.vf v24,ft0,v8,v0.t',asm)
        self.assertEqual(asm.count('csrw frm,t4'),8)
        self.assertIn('flw ft0,0(a1)',floating.assembly(32,'m1',scalar_forms=True))

    def test_stall_continuation_preserves_attempts_and_requires_live_evidence(self):
        cases=[dict(name=str(i),pass_marker='RVV_TEST_PASS') for i in range(3)]
        manifest=dict(cases=cases,archive_sha256='archive')
        first=dict(core=dict(cycles=100,retired=9,trap_count=0,last_pc=10,head_pc=14),
                   identity=dict(frequency_hz=100),watchdog_snapshot=False,live=dict(flags=0))
        last=copy.deepcopy(first);last['core']['cycles']=401
        report=dict(inputs=manifest,state='scene_preserved_incomplete',rtl_modified=False,board_reset=False,
                    results=[dict(name='0',status='passed',exit_code=0,output='RVV_TEST_PASS cases=23'),
                             dict(name='1',status='stalled')],
                    progress_diagnosis=dict(stalled=True,snapshots=[first,last]))
        self.assertEqual(recovery_prepare.remaining(manifest,report),cases[2:])
        changed=copy.deepcopy(report);changed['progress_diagnosis']['snapshots'][1]['core']['retired']+=1
        with self.assertRaises(ValueError):recovery_prepare.remaining(manifest,changed)
        changed=copy.deepcopy(report);changed['results'][0]['exit_code']=1
        with self.assertRaises(ValueError):recovery_prepare.remaining(manifest,changed)

        gap=copy.deepcopy(report)
        gap['results'][0]=dict(name='0',status='incomplete',
            error='UART observation gap; no correctness result inferred')
        gap.update(observation_reattached=True,serial_writes=False)
        gap['progress_diagnosis']['name']='1'
        with self.assertRaises(ValueError):recovery_prepare.remaining(manifest,gap)
        self.assertEqual(recovery_prepare.remaining(manifest,gap,True),[cases[0],cases[2]])
        for key,value in (('observation_reattached',False),('serial_writes',True)):
            changed=copy.deepcopy(gap);changed[key]=value
            with self.assertRaises(ValueError):recovery_prepare.remaining(manifest,changed,True)
        changed=copy.deepcopy(gap);changed['results'][0]['error']='Unrelated observation failure'
        with self.assertRaises(ValueError):recovery_prepare.remaining(manifest,changed,True)
        changed=copy.deepcopy(gap);changed['progress_diagnosis']['name']='0'
        with self.assertRaises(ValueError):recovery_prepare.remaining(manifest,changed,True)
        changed=copy.deepcopy(gap);changed['progress_diagnosis']['snapshots'][1]['core']['retired']+=1
        with self.assertRaises(ValueError):recovery_prepare.remaining(manifest,changed,True)

    def test_special_fp_reduction_keeps_order_and_initial_flags(self):
        asm=fp_reduction_special.assembly(16,'m8')
        self.assertIn('vfredosum.vs v24,v8,v16,v0.t',asm)
        self.assertIn('vsetvli t0,zero,e16,m1,tu,mu',asm)
        self.assertNotIn('vfredusum',asm)
        self.assertEqual(asm.count('csrw fflags,a7'),3)
        self.assertEqual(asm.count('csrw fflags,t5'),3)

    def test_indexed_segments_keep_index_and_data_groups_disjoint(self):
        self.assertEqual(segments.indexed_fields(8,'m4'),[])
        self.assertEqual(segments.indexed_fields(32,'m4'),[2])
        asm=segments.assembly(8,'m2',indexed=True)
        self.assertIn('vsetvli t0,a4,e32,m8,tu,mu',asm)
        self.assertIn('vluxseg4ei32.v v24,(a0),v16,v0.t',asm)
        self.assertIn('vsoxseg4ei32.v v8,(a1),v16,v0.t',asm)
        self.assertNotIn('seg5',asm)

    def test_scalar_mask_forms_are_packed_and_sign_extended(self):
        asm=masks.assembly(64,'m8',scalar_forms=True)
        self.assertIn('vmsltu.vx v24,v8,t3,v0.t',asm)
        self.assertIn('vmslt.vi v24,v8,-3,v0.t',asm)
        self.assertEqual(asm.count('vsm.v v24,(a2)'),12)
        self.assertEqual(asm.count('li t3,-3'),6)

    def test_mask_logic_alias_preserves_source_preimage(self):
        asm=masks.assembly(32,'m4',aliases=True)
        self.assertIn('vmand.mm v8,v8,v16',asm)
        self.assertIn('vmand.mm v16,v8,v16',asm)
        self.assertNotIn('vlm.v v24',asm)
        self.assertEqual(asm.count('vsm.v v8,(a2)'),8)
        self.assertEqual(asm.count('vsm.v v16,(a2)'),8)

    def test_independent_index_eew_limits_and_ordered_duplicates(self):
        ops=index_widths.operations(8,'m8')
        self.assertEqual({s for s,_,_ in ops},{8})
        self.assertEqual({m for _,_,m in ops},set(range(5)))
        asm=index_widths.assembly(8,'m1')
        self.assertIn('vsetvli t0,a4,e64,m8,tu,mu',asm)
        self.assertIn('vloxei64.v v24,(a0),v8,v0.t',asm)
        self.assertIn('vsoxei64.v v24,(a1),v8,v0.t',asm)
        lmuls=[x[0] for x in index_widths.build.LMULS]
        for sew,lmul in index_widths.build.shapes():
            for width,index_lmul,_ in index_widths.operations(sew,lmul):
                self.assertEqual(lmuls.index(index_lmul)-lmuls.index(lmul),
                                 width.bit_length()-sew.bit_length())

    def test_fp_width_groups_and_csr_boundary(self):
        self.assertEqual(len(fp_widths.shapes()),4)
        self.assertEqual(len(fp_widths.shapes(16)),5)
        half_width=fp_widths.assembly('m4',16)
        self.assertIn('vsetvli t0,a4,e32,m8,tu,mu',half_width)
        self.assertIn('vsetvli t0,a3,e16,m4,tu,mu',half_width)
        asm=fp_widths.assembly('m4')
        self.assertIn('vsetvli t0,a4,e64,m8,tu,mu',asm)
        self.assertIn('vfncvt.rod.f.f.w v24,v8,v0.t',asm)
        self.assertEqual(asm.count('csrw fflags,t5'),3)
        self.assertIn(0x7c55,floating.BITS[16])
        half=floating.assembly(16,'mf4',extras=True)
        self.assertIn('vsetvli t0,a3,e16,mf4,tu,mu',half)

    def test_nf_segment_limits_and_register_spacing(self):
        self.assertEqual(segments.fields('m2'),[3,4])
        self.assertEqual(segments.fields('m4'),[])
        self.assertEqual(segments.fields('mf8'),list(range(3,9)))
        asm=segments.assembly(32,'m2')
        self.assertIn('vle32.v v30,(a6)',asm)
        self.assertIn('vlsseg4e32.v v24,(a0),a5,v0.t',asm)
        self.assertIn('vssseg4e32.v v8,(a1),a5,v0.t',asm)
        self.assertIn('csrr t4,vstart',asm)
        self.assertNotIn('seg5',asm)

    def test_extension_overlap_is_high_end_and_not_fractional_source(self):
        self.assertEqual(len(extensions.cases()),28)
        asm=extensions.assembly(64,'m8',8,'m1')
        self.assertIn('vzext.vf8 v24,v31,v0.t',asm)
        self.assertIn('vs8r.v v24,(a1)',asm)
        fractional=extensions.assembly(32,'m1',4,'mf4')
        self.assertNotIn('op_2:',fractional)
        self.assertIn('vs1r.v v24,(a1)',fractional)

    def test_narrow_overlap_keeps_low_end_and_preserves_whole_group(self):
        asm=narrow_overlap.assembly(32,'m4')
        self.assertIn('vnsrl.wi v24,v24,3,v0.t',asm)
        self.assertIn('vsetvli t0,a4,e64,m8,tu,mu',asm)
        self.assertIn('vs8r.v v24,(a1)',asm)

    def test_fixed_rounding_and_sticky_fields_are_separate(self):
        asm=fixed.build.assembly(8,'m8',extra=True,operations=fixed.OPS,sticky_sat=True)
        self.assertEqual(asm.count('andi t2, a7, 3'),4)
        self.assertEqual(asm.count('srli t2, a7, 2'),4)
        self.assertNotIn('csrw vxrm, a7',asm)

    def test_reduction_destination_is_single_register(self):
        self.assertEqual(len(reductions.cases()),32)
        asm=reductions.assembly('integer',32,'m8')
        self.assertIn('vwredsum.vs v24,v8,v16,v0.t',asm)
        self.assertIn('vsetvli t0,zero,e64,m1,tu,mu',asm)
        self.assertIn('vsetvli t0,a3,e32,m8,tu,mu',asm)

    def test_fp_reference_and_csr_boundaries(self):
        for sew,lmul in ((32,'mf2'),(64,'m8')):
            asm=floating.assembly(sew,lmul)
            self.assertEqual(asm.count('csrw fflags,t5'),13)
            self.assertEqual(asm.count('csrw frm,t4'),13)
            self.assertIn('vfnmsac.vv v24,v8,v16,v0.t',asm)
        self.assertEqual(len(floating.BITS[32]),16)
        self.assertIn(1,floating.BITS[64])
        extra=floating.assembly(32,'m1',extras=True)
        self.assertIn('vfcvt.rtz.x.f.v v24,v8,v0.t',extra)
        self.assertIn('vfclass.v v24,v8,v0.t',extra)
        self.assertEqual(extra.count('csrw frm,t4'),16)

    def test_live_window_does_not_call_syscall(self):
        asm=context.assembly()
        self.assertNotIn('ecall',asm)
        self.assertIn('wait_signal:',asm)
        self.assertEqual(asm.count('vs8r.v'),4)
        source=(ROOT/'context_oracle.c').read_text()
        self.assertIn('action.sa_flags=SA_ONSTACK',source)
        self.assertIn('while(!*nested_ready)',source)
        self.assertIn('inner_handled!=before+1',source)

    def test_whole_and_fault_first_instruction_shape(self):
        asm=whole.assembly()
        for n in (1,2,4,8):
            self.assertIn(f'vl{n}re64.v v24',asm)
            self.assertIn(f'vmv{n}r.v v24,v8',asm)
        self.assertIn('vsetvl zero,zero,t0',asm)
        for sew in (8,16,32,64):
            self.assertIn(f'vle{sew}ff.v v24,(a0),v0.t',exceptions.assembly(sew))

    def test_mask_destination_is_not_predicate_or_source(self):
        self.assertEqual(len(masks.OPS),23)
        for sew,lmul in masks.build.shapes():
            asm=masks.assembly(sew,lmul)
            self.assertEqual(asm.count('csrr a0,vstart'),23)
            self.assertIn('vmsbf.m v24,v8,v0.t',asm)
            self.assertIn('vcpop.m t2,v8,v0.t',asm)
            self.assertIn('vsm.v v24,(a2)',asm)

    def test_segment_group_and_initial_tail(self):
        asm=memory.assembly(32,'m4')
        segment=asm.split('op_8:')[1].split('.global op_9')[0]
        self.assertIn('vle32.v v28,(a7)',segment)
        self.assertLess(segment.index('vle32.v v28'),segment.index('vsetvli t0,a3'))
        self.assertIn('vlseg2e32.v v24',segment)
        m8=memory.assembly(8,'m8')
        self.assertNotIn('vlseg2',m8)
        self.assertNotIn('vsseg2',m8)

    def test_widening_shape_limits(self):
        self.assertEqual(len(widths.shapes()),15)
        for sew,lmul in widths.shapes():
            self.assertLessEqual(sew*2,64)
            self.assertNotEqual(lmul,'m8')
            asm=widths.assembly(sew,lmul)
            self.assertEqual(asm.count('csrw vxrm,t4'),13)
            self.assertEqual(asm.count('csrw vxsat,t5'),13)
            self.assertIn('vnclip.wv v24,v8,v16,v0.t',asm)

    def test_combine_requires_reference_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            (root/'transfer_manifest.json').write_text('{"reference_passed":false}')
            with self.assertRaises(ValueError):combine.combine(Path(tmp)/'out',[root])

if __name__=='__main__':unittest.main()
