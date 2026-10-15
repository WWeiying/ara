.section .text
.global gather32
gather32:
    li t0, 32
    vsetvli t1, t0, INDEX_SEW, INDEX_LMUL, ta, ma
    bne t0, t1, unsupported
#if INDEX_BITS == 64
    vle64.v INDEX_REG, (a0)
#else
    vle32.v INDEX_REG, (a0)
#endif
    vsetvli t1, t0, DATA_SEW, DATA_LMUL, tu, mu
    bne t0, t1, unsupported
    bnez a3, overlap
#if INDEX_BITS == 64
    vluxei64.v v16, (a1), INDEX_REG
#else
    vluxei32.v v16, (a1), INDEX_REG
#endif
#if DATA_BITS == 16
    vse16.v v16, (a2)
#elif DATA_BITS == 32
    vse32.v v16, (a2)
#else
    vse64.v v16, (a2)
#endif
    j done
overlap:
#if INDEX_BITS == 64
    vluxei64.v v4, (a1), INDEX_REG
#else
    vluxei32.v v4, (a1), INDEX_REG
#endif
#if DATA_BITS == 16
    vse16.v v4, (a2)
#elif DATA_BITS == 32
    vse32.v v4, (a2)
#else
    vse64.v v4, (a2)
#endif
done:
    csrr t2, vstart
    bnez t2, bad_vstart
unsupported:
    mv a0, t1
    ret
bad_vstart:
    li a0, -1
    ret

.global masked_restart32
masked_restart32:
    li t0, 32
    vsetvli t1, t0, INDEX_SEW, INDEX_LMUL, ta, ma
    bne t0, t1, unsupported
#if INDEX_BITS == 64
    vle64.v INDEX_REG, (a0)
#else
    vle32.v INDEX_REG, (a0)
#endif
    vsetvli t1, t0, DATA_SEW, DATA_LMUL, tu, mu
    bne t0, t1, unsupported
    vmv.v.i v16, -7
    vid.v v8
    vand.vi v8, v8, 1
    vmsne.vi v0, v8, 0
    li t0, 17
    vsetvli t1, t0, DATA_SEW, DATA_LMUL, tu, mu
    bne t0, t1, unsupported
    li t2, 7
    csrw vstart, t2
#if INDEX_BITS == 64
    vluxei64.v v16, (a1), INDEX_REG, v0.t
#else
    vluxei32.v v16, (a1), INDEX_REG, v0.t
#endif
    csrr t2, vstart
    bnez t2, bad_vstart
    li t0, 32
    vsetvli t1, t0, DATA_SEW, DATA_LMUL, tu, mu
#if DATA_BITS == 16
    vse16.v v16, (a2)
#elif DATA_BITS == 32
    vse32.v v16, (a2)
#else
    vse64.v v16, (a2)
#endif
    mv a0, t1
    ret
