/* Standard FP32 staged oracle only. No QBEXEC and no custom-app Spike verdict. */
.section .text
.globl _start
_start:
    li t0, 0x6600
    csrs mstatus, t0
    la t0, probe_trap
    csrw mtvec, t0
    csrwi frm, 2
    la t4, probe_ledger

.macro RECORD offset
    fmv.x.w t0, ft5
    sd t0, \offset(t4)
    csrr t0, fflags
    sd t0, (\offset+8)(t4)
    or t3, t3, t0
.endm

.macro PHASE phase, scale, activation
    li t3, 8
    csrwi fflags, 0
    li t0, 256
    fcvt.s.w ft0, t0, rne
    fsgnj.s ft5, ft0, ft0
    RECORD (\phase*112)
    csrwi fflags, 0
    fcvt.s.w ft1, zero, rne
    fsgnj.s ft5, ft1, ft1
    RECORD (\phase*112+16)
    li t0, \scale
    fmv.w.x ft2, t0
    li t0, \activation
    fmv.w.x ft3, t0
    csrwi fflags, 0
    fmul.s ft2, ft2, ft3, rne
    fsgnj.s ft5, ft2, ft2
    RECORD (\phase*112+32)
    fmv.w.x ft4, zero
    csrwi fflags, 0
    fmul.s ft4, ft4, ft3, rne
    fsgnj.s ft5, ft4, ft4
    RECORD (\phase*112+48)
    fmv.w.x ft6, zero
    csrwi fflags, 0
    fmadd.s ft5, ft2, ft0, ft6, rne
    RECORD (\phase*112+64)
    fsgnjn.s ft4, ft4, ft4
    csrwi fflags, 0
    fmadd.s ft5, ft4, ft1, ft5, rne
    RECORD (\phase*112+80)
    csrw fflags, t3
    csrr t0, fflags
    sd t0, (\phase*112+96)(t4)
    csrr t0, frm
    sd t0, (\phase*112+104)(t4)
.endm
    PHASE 0, 0x3f800000, 1
    PHASE 1, 0x3f000000, 3
    li t0, 1
    j probe_exit
probe_trap:
    li t0, 3
probe_exit:
    la t1, tohost
    sd t0, 0(t1)
1:  j 1b
.section .data
.balign 64
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
.globl probe_ledger
probe_ledger: .zero 224

