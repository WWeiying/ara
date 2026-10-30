/* Synthetic ownership fixture, not a performance kernel. */
.option push
.option norvc
.option norelax
.text
.balign 4
.global rh_trap_handler
.type rh_trap_handler,@function
rh_trap_handler:
    /* No C call, FP/vector operation, or scratch GPR other than saved t0/t1. */
    addi sp, sp, -16
    sd t0, 0(sp)
    sd t1, 8(sp)
    csrr t0, mcause
    la t1, rh_trap_cause
    sd t0, 0(t1)
    csrr t0, mtval
    la t1, rh_trap_tval
    sd t0, 0(t1)
    csrr t0, mepc
    la t1, rh_trap_epc
    sd t0, 0(t1)
    addi t0, t0, 4
    csrw mepc, t0
    la t1, rh_trap_count
    ld t0, 0(t1)
    addi t0, t0, 1
    sd t0, 0(t1)
    ld t1, 8(sp)
    ld t0, 0(sp)
    addi sp, sp, 16
    mret
.size rh_trap_handler,.-rh_trap_handler

.global rh_qbs_info
.type rh_qbs_info,@function
rh_qbs_info:
    .word 0x0005155b
    ret
.size rh_qbs_info,.-rh_qbs_info
.global rh_akv_info
.type rh_akv_info,@function
rh_akv_info:
    .word 0x0005455b
    ret
.size rh_akv_info,.-rh_akv_info

/* descriptor, activation, initial_v8, result_v8, resident_Q1_output.
 * The QBS destination v8 is not touched by the following AKV load into v16.
 * No normal vector memory request is inserted between the two custom ops. */
.global rh_qbs_then_akv
.type rh_qbs_then_akv,@function
rh_qbs_then_akv:
    fence rw, rw
    li t2, 32
    vsetvli zero, t2, e32, m1, ta, ma
    vle32.v v8, (a2)
    li t0, 0x13579
    li t1, 0x2468a
.global rh_qbs_site
rh_qbs_site:
    .word 0x00b5045b
    li a0, 4 /* Q row 1, selector = (1 << 2) | Q */
    li t2, 64
    vsetvli zero, t2, e16, m1, ta, ma
    .word 0x0005385b /* VAKVLOAD -> v16 */
    vse16.v v16, (a4)
    li t2, 32
    vsetvli zero, t2, e32, m1, ta, ma
    vse32.v v8, (a3)
    /* Current Ara VMVXS waits for all older vector work, including stores. */
    vmv.x.s t2, v8
    fence rw, rw
    li t2, 0x13579
    xor t0, t0, t2
    li t2, 0x2468a
    xor t1, t1, t2
    or a0, t0, t1
    ret
.size rh_qbs_then_akv,.-rh_qbs_then_akv

.global rh_akv_full
.type rh_akv_full,@function
rh_akv_full:
    li a1, 0
    fence rw, rw
    .word 0x00b5605b
    ret
.size rh_akv_full,.-rh_akv_full
.global rh_akv_load
.type rh_akv_load,@function
rh_akv_load:
    li t0, 64
    vsetvli zero, t0, e16, m1, ta, ma
    .word 0x0005345b
    vse16.v v8, (a1)
    vmv.x.s t0, v8
    fence rw, rw
    ret
.size rh_akv_load,.-rh_akv_load
.global rh_akv_release
.type rh_akv_release,@function
rh_akv_release:
    .word 0x0000505b
    ret
.size rh_akv_release,.-rh_akv_release

/* Normal VLSU success before/after all special owners, with defined v8. */
.global rh_rvv_copy_add
.type rh_rvv_copy_add,@function
rh_rvv_copy_add:
    li t0, 32
    vsetvli zero, t0, e32, m1, ta, ma
    vle32.v v8, (a0)
    vadd.vi v8, v8, 1
    vse32.v v8, (a1)
    vmv.x.s t0, v8
    fence rw, rw
    ret
.size rh_rvv_copy_add,.-rh_rvv_copy_add
.option pop
