// Experimental resident QK. The caller owns and validates the loaded context.
// a0=F32 scores (256B/head), a1=T, a2=H, a3=D, a4=query-base.
// Admitted geometry: T1..64, H1/2, D64/96/128, base+H<=loaded Q rows.
// Clobbers v0..v3 and caller-saved integer temporaries; no scalar FP arithmetic.
    .text
    .option push
    .option norvc
    .option norelax
    .p2align 2
    .globl akv_experimental_resident_qk
    .type akv_experimental_resident_qk,@function
akv_experimental_resident_qk:
    mv              t0, a0
    mv              t1, a1
    mv              t2, a2
    addi            a0, a1, -1
    addi            t3, a2, -1
    slli            t3, t3, 6
    or              a0, a0, t3
    slli            t3, a4, 9
    or              a0, a0, t3
    li              t3, 64
    beq             a3, t3, .Lresident_qk_issue
    li              t3, 96
    beq             a3, t3, .Lresident_qk_d96
    ori             a0, a0, 128
    j               .Lresident_qk_issue
.Lresident_qk_d96:
    ori             a0, a0, 256
.Lresident_qk_issue:
    .word           0x0605705b  // custom2/7/3, vd=v0, rs1=a0, rs2=0
    vsetvli         zero, t1, e32, m2, ta, ma
    vse32.v         v0, (t0)
    li              t3, 1
    beq             t2, t3, .Lresident_qk_done
    addi            t0, t0, 256
    vse32.v         v2, (t0)
.Lresident_qk_done:
    ret
    .size akv_experimental_resident_qk, .-akv_experimental_resident_qk
    .option pop
    .section .note.GNU-stack,"",@progbits
