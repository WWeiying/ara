/* SPDX-License-Identifier: Apache-2.0 */
/* Fixed-register diagnostic, NOT a timed replacement kernel. UART macros
 * touch only t3-t6 and never call C, alter vtype, or spill vector registers.
 * Each D record consumes a dependent scalar result. Serializing operations
 * changes scheduling: success here does not prove the original sequence works.
 */
.section .text.probe_quant_ops,"ax",@progbits
.balign 4
.global probe_quant_ops
.type probe_quant_ops,@function

.macro uart_char value
  li t5, \value
1:
  lw t4, 20(t3)
  andi t4, t4, 32
  beqz t4, 1b
  sw t5, 0(t3)
.endm

.macro record id, kind
#ifdef ARA_FPGA
  li t3, 0x03002000
  uart_char 81
  uart_char (48 + (\id / 10))
  uart_char (48 + (\id % 10))
  uart_char 32
  uart_char \kind
  .if \kind != 66
    uart_char 32
    li t6, 28
2:
    srl t5, a2, t6
    andi t5, t5, 15
    addi t5, t5, 48
    li t4, 58
    bltu t5, t4, 3f
    addi t5, t5, 39
3:
    lw t4, 20(t3)
    andi t4, t4, 32
    beqz t4, 3b
    sw t5, 0(t3)
    addi t6, t6, -4
    bgez t6, 2b
  .endif
  uart_char 13
  uart_char 10
#endif
.endm

.macro substage letter
#ifdef ARA_FPGA
  li t3, 0x03002000
  uart_char 81
  uart_char 48
  uart_char 49
  uart_char \letter
  uart_char 13
  uart_char 10
#endif
.endm

.macro begin id
  li a4, \id
  sd a4, 0(a3)
  record \id, 66
.endm

.macro done id, expected
  sd a2, (8 * \id)(a3)
  li t2, \expected
  sext.w t2, t2
  bne a2, t2, .Lfail
  record \id, 68
.endm

probe_quant_ops:
  mv a3, a2
  begin 1
  vsetvli t0, zero, e32, m8, ta, ma
  substage 97
  mv a2, t0
  li t1, 256
  bne t0, t1, .Lfail
  li t0, 0xff800000
  vmv.v.x v8, t0
  substage 98
  vmv.s.x v24, t0
  substage 99
  li t0, 0x7f800000
  vmv.v.x v16, t0
  substage 100
  vmv.s.x v25, t0
  substage 101
  substage 102
  vmv.x.s a2, v8
  substage 103
  done 1, 0xff800000

  begin 2
  vle32.v v0, (a0)
  vmv.x.s a2, v0
  done 2, 0xc1700000

  begin 3
  vfmax.vv v8, v8, v0
  vmv.x.s a2, v8
  done 3, 0xc1700000

  begin 4
  vfmin.vv v16, v16, v0
  vmv.x.s a2, v16
  done 4, 0xc1700000

  begin 18
  vmv.x.s a2, v25
  done 18, 0x7f800000

  /* Keep only element zero active to isolate intra-lane reduction from
   * the cross-lane/SLDU reduction. */
  vsetivli zero, 1, e32, m8, ta, ma
  begin 19
  vfredmin.vs v9, v16, v25
  vfmv.f.s ft1, v9
  fmv.x.w a2, ft1
  done 19, 0xc1700000
  vsetvli t0, zero, e32, m8, ta, ma

  /* Discriminate standalone vfredmin from the adjacent max/min sequence. */
  begin 17
  vfredmin.vs v9, v16, v25
  vfmv.f.s ft1, v9
  fmv.x.w a2, ft1
  done 17, 0xc1700000

  begin 5
  vfredmax.vs v8, v8, v24
  vfmv.f.s ft0, v8
  fmv.x.w a2, ft0
  done 5, 0x41700000

  begin 6
  vfredmin.vs v9, v16, v25
  vfmv.f.s ft1, v9
  fmv.x.w a2, ft1
  done 6, 0xc1700000

  begin 7
  li t0, 0xc2fe0000
  fmv.w.x ft0, t0
  fdiv.s ft0, ft0, ft1
  fmv.x.w a2, ft0
  done 7, 0x41077777

  begin 8
  li t0, 0x3f800000
  fmv.w.x ft1, t0
  fdiv.s ft1, ft1, ft0
  fmv.x.w a2, ft1
  done 8, 0x3df1e3c8

  begin 9
  vmv.s.x v16, zero
  vle32.v v8, (a0)
  vfmul.vf v8, v8, ft0
  vfmv.f.s ft1, v8
  fmv.x.w a2, ft1
  done 9, 0xc2fdffff

  begin 10
  fsrmi t1, 0
  vfcvt.x.f.v v8, v8
  fsrm t1
  vmv.x.s a2, v8
  done 10, -127

  begin 11
  csrwi vxrm, 0
  vsetvli zero, zero, e16, m4, ta, ma
  vnclip.wi v20, v8, 0
  vmv.x.s a2, v20
  done 11, -127

  begin 12
  vsetvli zero, zero, e8, m2, ta, ma
  vnclip.wi v8, v20, 0
  vse8.v v8, (a1)
  fence rw, rw
  lb a2, 0(a1)
  done 12, -127

  begin 13
  vsetivli zero, 16, e8, m1, ta, ma
  vwredsum.vs v10, v8, v16
  vsetivli zero, 1, e16, m1, ta, ma
  vmv.x.s a2, v10
  done 13, -1016

  begin 14
  li t0, 256
  vsetvli zero, t0, e8, m2, ta, ma
  vslidedown.vi v8, v8, 16
  vsetivli zero, 16, e8, m1, ta, ma
  vwredsum.vs v10, v8, v16
  vsetivli zero, 1, e16, m1, ta, ma
  vmv.x.s a2, v10
  done 14, 889

  /* Preserve the original adjacent reductions and overlapping vd/vs2. */
  begin 15
  vsetvli t0, zero, e32, m8, ta, ma
  li t0, 0xff800000
  vmv.v.x v8, t0
  vmv.s.x v24, t0
  li t0, 0x7f800000
  vmv.v.x v16, t0
  vmv.s.x v25, t0
  vle32.v v0, (a0)
  vfmax.vv v8, v8, v0
  vfmin.vv v16, v16, v0
  vfredmax.vs v8, v8, v24
  vfredmin.vs v9, v16, v25
  vfmv.f.s ft0, v8
  vfmv.f.s ft1, v9
  fmv.x.w a2, ft0
  done 15, 0x41700000
  begin 16
  fmv.x.w a2, ft1
  done 16, 0xc1700000
  li a0, 0
  ret
.Lfail:
  /* The live stage is retained at trace[0]; a2 is the unexpected value. */
  record 0, 70
  li a0, 1
  ret
.size probe_quant_ops, .-probe_quant_ops
