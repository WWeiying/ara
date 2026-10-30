/* Success-only baseline. All custom encodings are checked against akv_abi.h
 * by main before use; build.py also checks the linked instruction windows. */
    .section .text
    .option push
    .option norvc
    .option norelax

    .balign 4
    .globl rvtest_init
    .type rvtest_init, @function
rvtest_init:
    la t0, mtvec_handler
    csrw mtvec, t0
    /* CSR_ACC_CONS, hardware/deps/cva6/core/include/riscv_pkg.sv. */
    li t0, 1
    csrw 0x7c2, t0
    csrr t0, 0x7c2
    la t1, probe_boot_consistency
    sd t0, 0(t1)
    ret
    .size rvtest_init, .-rvtest_init

    .balign 4
    .globl mtvec_handler
    .type mtvec_handler, @function
mtvec_handler:
    /* No recovery in this ELF: never resume with clobbered GPRs. */
    csrr a0, mcause
    csrr a1, mepc
    csrr a2, mtval
    tail probe_unexpected_trap
    .size mtvec_handler, .-mtvec_handler

    .globl probe_info
    .type probe_info, @function
probe_info:
    .word 0x0005455b             /* rd=a0, selector=a0 */
    ret
    .size probe_info, .-probe_info

    .globl probe_vector_bytes
    .type probe_vector_bytes, @function
probe_vector_bytes:
    csrr a0, vlenb
    ret
    .size probe_vector_bytes, .-probe_vector_bytes

    .globl probe_full
    .type probe_full, @function
probe_full:
    csrwi vstart, 0
    fence rw, rw
    .word 0x00b5605b             /* descriptor=a0, tile_start=a1 */
    ret
    .size probe_full, .-probe_full

    .globl probe_release
    .type probe_release, @function
probe_release:
    .word 0x0000505b
    ret
    .size probe_release, .-probe_release

    .globl probe_row
    .type probe_row, @function
probe_row:
    li t0, 128
    vsetvli t6, t0, e16, m2, ta, ma
    .word 0x0205345b             /* D128 row: selector=a0, vd=v8..v9 */
    vse16.v v8, (a1)
    vsetvli zero, t0, e8, m1, ta, ma
    fence rw, rw
    mv a0, t6
    ret
    .size probe_row, .-probe_row

    .globl probe_canary
    .type probe_canary, @function
probe_canary:
    li t0, 32
    vsetvli t6, t0, e32, m2, ta, ma
    vle32.v v16, (a0)
    vadd.vi v16, v16, 1
    vse32.v v16, (a1)
    vsetvli zero, t0, e8, m1, ta, ma
    fence rw, rw
    mv a0, t6
    ret
    .size probe_canary, .-probe_canary

    /* a0=64, a1=128 FP32 result words, a2=six uint64_t markers.
     * v8..11 accumulator; v16..19 and v20..23 independent exact 1.0.
     * No memory access or config/CSR instruction in the immediate FMA/refill
     * adjacency window. Only serial has the intentional LMUL-decrease drain. */
    .macro TIMED_PROBE name, serial
    .balign 64
    .globl \name
    .type \name, @function
\name:
    li t0, 128
    vsetvli t6, t0, e32, m4, ta, ma
    vmv.v.i v8, 0
    li t3, 0x3f800000
    vmv.v.x v16, t3
    vmv.v.x v20, t3
    vsetvli zero, t0, e16, m1, ta, ma
    vsetvli zero, t0, e32, m4, ta, ma
    li t3, 8
    csrw fflags, t3
    .globl \name\()_start
\name\()_start:
    rdcycle t1
    .globl \name\()_fma_first
\name\()_fma_first:
    .rept 15
    vfmacc.vv v8, v16, v20
    .endr
    .globl \name\()_fma_last
\name\()_fma_last:
    vfmacc.vv v8, v16, v20
    .if \serial
    vsetvli zero, t0, e16, m1, ta, ma
    .endif
    .globl \name\()_refill
\name\()_refill:
    .word 0x02a0605b             /* rs1=x0, rs2=a0, rd=x0 */
    .globl \name\()_returned
\name\()_returned:
    rdcycle t2
    vsetvli zero, t0, e8, m1, ta, ma
    .globl \name\()_drained
\name\()_drained:
    rdcycle t5
    csrr t3, fflags
    csrr t4, vstart
    vsetvli zero, t0, e32, m4, ta, ma
    vse32.v v8, (a1)
    vsetvli zero, t0, e8, m1, ta, ma
    fence rw, rw
    sd t1, 0(a2)
    sd t2, 8(a2)
    sd t5, 16(a2)
    sd t6, 24(a2)
    sd t3, 32(a2)
    sd t4, 40(a2)
    ret
    .size \name, .-\name
    .endm

    TIMED_PROBE probe_immediate, 0
    TIMED_PROBE probe_serial, 1
    .option pop
    .section .note.GNU-stack,"",@progbits
