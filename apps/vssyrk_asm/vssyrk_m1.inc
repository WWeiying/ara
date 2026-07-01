__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void ssyrk_f32_full_32x32x32(const float *A, float *C, const float alpha,
                             const float beta) {
    // ABI: a0=A, a1=C, fa0=alpha, fa1=beta.
    //
    // Nested loop.  Outer (row_loop) seeds acc = beta*C[i,:]; inner (k_loop)
    // reads scalar a_ik, scales by alpha, and accumulates the strided column
    // A[:,k] via vfmacc.vf.  Scalar load-use (flw->fmul) and the strided-load
    // base bump are kept in separate EPs.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vssyrk_hdv_task_start:\n"
    "addi sp, sp, -16\n"
    "sd s0, 0(sp)\n"

    // setup: VL config + row stride + counters + base pointers.
    "li s0, 32\n"
    "vsetvli zero, s0, e32, m1, ta, ma\n"
    "li t5, 128\n"
    "li t0, 32\n"
    "mv t1, a0\n"
    "mv t2, a1\n"

    // outer loop top: acc = beta * C[i,:].
    "row_loop:\n"
    "vle32.v v4, (t2)\n"
    "vfmul.vf v4, v4, fa1\n"
    "nop\n"
    // reset inner pointers / k counter.
    "mv t3, a0\n"
    "mv t4, t1\n"
    "li a2, 32\n"

    // inner loop top: load scalar a_ik.
    "k_loop:\n"
    "flw ft0, 0(t4)\n"
    "nop\n"
    "nop\n"
    // alpha * a_ik (load-use of ft0).
    "fmul.s ft1, ft0, fa0\n"
    "nop\n"
    "nop\n"
    // strided load of column k (base t3, stride t5).
    "vlse32.v v0, (t3), t5\n"
    "nop\n"
    "nop\n"
    // acc += (alpha*a_ik) * A[:,k].
    "vfmacc.vf v4, ft1, v0\n"
    "nop\n"
    "nop\n"
    // bump inner pointers + decrement k.
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "addi a2, a2, -1\n"
    // inner back-edge.
    "bnez a2, k_loop\n"
    "nop\n"
    "nop\n"

    // store the full output row C[i,:].
    "vse32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    // outer pointer bumps + row decrement.
    "addi t1, t1, 128\n"
    "addi t2, t2, 128\n"
    "addi t0, t0, -1\n"
    // outer back-edge.
    "bnez t0, row_loop\n"
    "nop\n"
    "nop\n"

    "ld s0, 0(sp)\n"
    "addi sp, sp, 16\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
