__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void vssymv_f32_32x32(const float *A, const float *x, float *y,
                      const float alpha, const float beta) {
    // ABI: a0=A, a1=x, a2=y, fa0=alpha, fa1=beta.
    //
    // Single strip-mine row loop.  Per row: dot(A[i,:], x) via vfmul+vfredusum,
    // move the reduction scalar to ft1 (5.1 vector->scalar writeback), then the
    // dependent scalar FP chain alpha*dot + beta*y[i] is split one-per-EP because
    // each step consumes the previous result (load-use / writeback hazards).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vssymv_hdv_task_start:\n"
    "addi sp, sp, -16\n"
    "sd s0, 0(sp)\n"

    // setup A: li t3,32 ; vsetvli (config) ; vle x.
    "li t3, 32\n"
    "vsetvli zero, t3, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    // setup B: zero seed ft0 ; row count ; A/y row pointers.
    "fmv.w.x ft0, zero\n"
    "li t0, 1024\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"
    "nop\n"

    // row loop top: re-config VL || load A row.
    "row_loop:\n"
    "vsetvli s0, t0, e32, m1, ta, ma\n"
    "vle32.v v1, (t1)\n"
    "nop\n"
    // A[i,:]*x || seed — vfmul writes v2, vfmv.v.f writes v16 (no conflict).
    "vfmul.vv v2, v1, v0\n"
    "vfmv.v.f v16, ft0\n"
    "nop\n"
    // reduce — separate EP: vfredusum reads v2, v16; writes v16.
    // Must be in different EP from vfmv.v.f to avoid WAW bypass on v16.
    "vfredusum.vs v16, v2, v16\n"
    "nop\n"
    "nop\n"
    // dot -> ft1 (vector->scalar writeback): isolate so fmadd sees it.
    "vfmv.f.s ft1, v16\n"
    "flw ft2, 0(t2)\n"
    "nop\n"
    // beta*y[i] (load-use of ft2): isolate.
    "fmul.s ft2, ft2, fa1\n"
    "nop\n"
    "nop\n"
    // alpha*dot + beta*y[i] -> store.
    "fmadd.s ft2, ft1, fa0, ft2\n"
    "fsw ft2, 0(t2)\n"
    "nop\n"
    // pointer bumps + row decrement.
    "addi t1, t1, 128\n"
    "addi t2, t2, 4\n"
    "sub t0, t0, s0\n"
    // branch (loop_end).
    "bnez t0, row_loop\n"
    "nop\n"
    "nop\n"

    // ret terminates the HDV task.
    "ld s0, 0(sp)\n"
    "addi sp, sp, 16\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
