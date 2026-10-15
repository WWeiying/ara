.section .text
.balign 4
.global run_epoch
run_epoch:
    vsetivli zero, 16, e16, m1, tu, mu
    vmv.v.i v0, 0
    li t0, 2
    vmv.s.x v0, t0
    li t0, 0x7c01
    vmv.v.x v2, t0
    li t0, 0x3c00
    vmv.v.x v3, t0
    vmv.v.x v4, t0
    vmv.v.x v5, t0
    vmv.v.i v8, 0
    vmv.v.i v9, 0
    csrwi fflags, 0
    vfredusum.vs v8, v4, v2, v0.t
#if VARIANT == 2
    vsetivli zero, 1, e16, m1, tu, mu
#endif
#if VARIANT != 0
    vfredusum.vs v9, v5, v3, v0.t
#endif
    csrr t0, fflags
    sd t0, 0(a0)
    vsetivli zero, 1, e16, m1, tu, mu
    addi t0, a0, 8
    vse16.v v8, (t0)
    addi t0, a0, 10
    vse16.v v9, (t0)
    fence
    csrr zero, vl
    ret
