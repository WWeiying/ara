    .text
    .option push
    .option norvc
    .option norelax
    .globl fill_context
fill_context:
    fence rw, rw
    .word 0x00b5605b
    ret
    .globl release_context
release_context:
    .word 0x0000505b
    ret

    // a0=selector/control, a1=save buffer, a2=three u64 observations.
    // The CSR and first save must immediately follow the custom instruction.
    .macro observations rd
    sd \rd, 0(a2)
    frcsr t0
    sd t0, 8(a2)
    csrr t0, vstart
    sd t0, 16(a2)
    csrr zero, vl
    fence rw, rw
    ret
    .endm

    .globl row_case
row_case:
    csrwi fcsr, 1
    li t0, 128
    vsetvli zero, t0, e16, m2, ta, ma
    .balign 64
    .globl row_issue, row_csr, row_save
row_issue:
    .word 0x02053c5b // D128 LOAD v24:v25, V[63].
row_csr:
    csrr t3, vl
row_save:
    vse16.v v24, (a1)
    observations t3

    .globl column_case
column_case:
    csrwi fcsr, 1
    li t0, 256
    vsetvli zero, t0, e16, m4, ta, ma
    .balign 64
    .globl column_issue, column_csr, column_save
column_issue:
    .word 0x0205785b // T64 panel4 K columns 20..23, v16:v19.
column_csr:
    csrr t4, vl
column_save:
    vse16.v v16, (a1)
    observations t4

    .globl qk_case
qk_case:
    csrwi fcsr, 1
    li t0, 128
    vsetvli zero, t0, e32, m4, ta, ma
    .balign 64
    .globl qk_issue, qk_csr, qk_save
qk_issue:
    .word 0x0605705b // T64 H2 D128, all 128 FP32 scores.
qk_csr:
    csrr t5, vl
qk_save:
    vse32.v v0, (a1)
    observations t5

    // a3=raw EW16 seeds/coefficient pairs plus v14:v15 guards;
    // a4=source-preservation save buffer. No SDK preparation dependency.
    .globl pv_case
pv_case:
    csrwi fcsr, 1
    li t0, 512
    vsetvli zero, t0, e16, m8, ta, ma
    vle16.v v8, (a3)
    li t0, 256
    vsetvli zero, t0, e16, m4, ta, ma
    .balign 64
    .globl pv_issue, pv_csr, pv_save
pv_issue:
    .word 0x0485705b // T64 H2 D128, all 256 FP16 results.
pv_csr:
    csrr t6, vl
pv_save:
    vse16.v v0, (a1)
    sd t6, 0(a2)
    frcsr t0
    sd t0, 8(a2)
    csrr t0, vstart
    sd t0, 16(a2)
    li t0, 512
    vsetvli zero, t0, e16, m8, ta, ma
    vse16.v v8, (a4)
    csrr zero, vl
    fence rw, rw
    ret
    .option pop
    .section .note.GNU-stack,"",@progbits
