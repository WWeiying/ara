__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest) {
    // ABI: a0=matrix, a1=vector (x), a2=dest.  Each "addi t2,base,off ; vle v,(t2)"
    // is split so the vle snapshots the freshly bumped base (scalar->vector
    // operand hazard).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsgemv_hdv_task_start:\n"

    // setup: load the real input vector x (a1), 128 elements = 4 chunks of 32,
    // into v0..v3.  (Deviates from the original benchmark, which synthesised x
    // with vid and ignored the vector argument; this makes it a true gemv.)
    "li t3, 32\n"
    "nop\n"
    "nop\n"
    // VL config || load x chunk 0 (reads a1).
    "vsetvli zero, t3, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "nop\n"
    // x chunk 1.
    "addi t2, a1, 128\n"
    "nop\n"
    "nop\n"
    "vle32.v v1, (t2)\n"
    "nop\n"
    "nop\n"
    // x chunk 2.
    "addi t2, a1, 256\n"
    "nop\n"
    "nop\n"
    "vle32.v v2, (t2)\n"
    "nop\n"
    "nop\n"
    // x chunk 3.
    "addi t2, a1, 384\n"
    "nop\n"
    "nop\n"
    "vle32.v v3, (t2)\n"
    "nop\n"
    "nop\n"
    // matrix row pointer + row counter.
    "mv t0, a0\n"
    "li t6, 1024\n"
    "nop\n"

    // row loop top: VL config || load chunk0 (reads t0).
    "row_loop:\n"
    "vsetvli t5, t6, e32, m1, ta, ma\n"
    "vle32.v v4, (t0)\n"
    "nop\n"
    // chunk1 base then load.
    "addi t2, t0, 128\n"
    "nop\n"
    "nop\n"
    "vle32.v v5, (t2)\n"
    "nop\n"
    "nop\n"
    // chunk2 base then load.
    "addi t2, t0, 256\n"
    "nop\n"
    "nop\n"
    "vle32.v v6, (t2)\n"
    "nop\n"
    "nop\n"
    // chunk3 base then load.
    "addi t2, t0, 384\n"
    "nop\n"
    "nop\n"
    "vle32.v v7, (t2)\n"
    "nop\n"
    "nop\n"
    // accumulate (vector chain).
    "vmv.v.i v8, 0\n"
    "vfmacc.vv v8, v4, v0\n"
    "vfmacc.vv v8, v5, v1\n"
    "vfmacc.vv v8, v6, v2\n"
    "vfmacc.vv v8, v7, v3\n"
    "nop\n"
    // reduce.
    "vmv.v.i v16, 0\n"
    "vfredsum.vs v16, v8, v16\n"
    "nop\n"
    // reduction -> fa0 (vector->scalar writeback), isolate, then store.
    "vfmv.f.s fa0, v16\n"
    "nop\n"
    "nop\n"
    "fsw fa0, (a2)\n"
    "nop\n"
    "nop\n"
    // pointer bumps + row decrement.
    "addi t0, t0, 512\n"
    "addi a2, a2, 4\n"
    "sub t6, t6, t5\n"
    // branch (loop_end).
    "bnez t6, row_loop\n"
    "nop\n"
    "nop\n"

    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
