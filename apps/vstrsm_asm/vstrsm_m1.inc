__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void strsm_f32_left_lower_32x32(const float *L, float *B) {
    // ABI: a0=L, a1=B.
    //
    // Nested loop with a forward skip: the outer row_loop divides B[i,:] by the
    // diagonal, then (if any rows remain below) the inner update_loop does the
    // rank-1 elimination B[j,:] -= L[j][i]*X[i,:].  The forward branch target
    // update_done and both loop tops are 16B aligned EP starts.  Scalar address
    // math (slli/add) and its dependent flw are split across EPs.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vstrsm_hdv_task_start:\n"

    // setup: VL config + indices + base pointers + row count.
    "li s0, 32\n"
    "vsetvli zero, s0, e32, m1, ta, ma\n"
    "li t0, 0\n"
    "mv t1, a0\n"
    "mv t2, a1\n"
    "li t6, 32\n"

    // outer loop top: diagonal address = &L[i][i].
    "row_loop:\n"
    "slli t4, t0, 2\n"
    "add t3, t1, t4\n"
    "nop\n"
    // load the diagonal element.
    "flw fa0, 0(t3)\n"
    "nop\n"
    "nop\n"
    // load RHS row, divide by diagonal, store back.
    "vle32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    "vfdiv.vf v0, v0, fa0\n"
    "nop\n"
    "nop\n"
    "vse32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    // set up the below-rows update: next L/B rows + remaining count.
    "addi t5, t1, 128\n"
    "addi a2, t2, 128\n"
    "addi a4, t6, -1\n"
    // skip the inner loop when no rows remain below.
    "beqz a4, update_done\n"
    "nop\n"
    "nop\n"

    // inner loop top: &L[j][i] then L[j][i].
    "update_loop:\n"
    "add a3, t5, t4\n"
    "nop\n"
    "nop\n"
    "flw fa1, 0(a3)\n"
    "nop\n"
    "nop\n"
    // B[j,:] -= L[j][i] * X[i,:].
    "vle32.v v1, (a2)\n"
    "nop\n"
    "nop\n"
    "vfnmsac.vf v1, fa1, v0\n"
    "nop\n"
    "nop\n"
    "vse32.v v1, (a2)\n"
    "nop\n"
    "nop\n"
    // bump inner L/B pointers + decrement count.
    "addi t5, t5, 128\n"
    "addi a2, a2, 128\n"
    "addi a4, a4, -1\n"
    // inner back-edge.
    "bnez a4, update_loop\n"
    "nop\n"
    "nop\n"

    // outer pointer bumps + index/row updates.
    "update_done:\n"
    "addi t1, t1, 128\n"
    "addi t2, t2, 128\n"
    "addi t0, t0, 1\n"
    "addi t6, t6, -1\n"
    "nop\n"
    "nop\n"
    // outer back-edge.
    "bnez t6, row_loop\n"
    "nop\n"
    "nop\n"

    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
