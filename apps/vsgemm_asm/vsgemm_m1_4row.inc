__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_32x32x32_4row(const float *A, const float *B, float *C) {
    // ABI: a0=A, a1=B, a2=C.
    //
    // Nested loop, 4-row blocking: outer (row_block_loop) processes 4 C rows at a
    // time with accumulators v8..v11; inner (k_loop) loads 4 scalars A[i+r][k]
    // and one B[k,:] row, doing 4 vfmacc.vf.  Scalar loads are one-per-EP (the
    // scalar LSU is synchronous); the 4 vfmacc are packed (Ara resolves the
    // vector deps); each "addi a5,t2,off ; vse v,(a5)" store base is split.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsgemm_hdv_task_start:\n"

    // setup: VL config + row-block count + A/C bases.  AVL is set to 1024 (VL
    // still resolves to 32 because VLMAX=32) so the data prefetcher sees
    // avl >= vl*2 for the B-row load across the whole inner loop -- this lets the
    // prefetch engage WITHOUT a per-iteration vsetvli (which would cost an EP).
    "li a3, 1024\n"
    "vsetvli zero, a3, e32, m1, ta, ma\n"
    "li t0, 8\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"

    // outer loop top: zero the 4 row accumulators.
    "row_block_loop_32:\n"
    "vmv.v.i v8, 0\n"
    "vmv.v.i v9, 0\n"
    "vmv.v.i v10, 0\n"
    "vmv.v.i v11, 0\n"
    "nop\n"
    "nop\n"
    // A base pointer for row i (rows i+1..i+3 are read via immediate offsets
    // 128/256/384 off t3, so t4..t6 are no longer needed).
    "mv t3, t1\n"
    "mv a3, a1\n"
    "li a4, 1024\n"

    // inner loop top: VL config.
    "k_loop_32:\n"
    // Rows i+1..i+3 of A are read via immediate offsets 128/256/384 off t3 (the
    // row stride is 128B), so only t3 is bumped below.
    // ── Dense pack: packet256 + cross + p-bits (boundary p-bit=1 keep in same EP,
    //    p-bit=0 cut; cross=1 carries the packet tail EP into the next packet;
    //    see hdv_vliw_pack_unit.sv) ─────────────────────────────────────────────
    // packet 0 (256-bit, loop_start, cross): the 4 scalar A loads packed into ONE
    // EP (p-bits keep slots 1/3/5) so the pipelined scalar LSU issues all 4 ARs
    // back-to-back and overlaps their AXI round-trips (~36->~15 cyc/iter); then
    // the B load and the first 2 of the 4 vfmacc.  The vfmacc EP is the packet
    // tail (< 8 slots), so cross=1 carries it into packet 1 with no pad nops.
    // (The prefetch AVL comes from the setup vsetvli, a3=1024.)
    // p-bits = 0x82a (keep flw fa0..fa3 at 1/3/5; cut before vle at 7; keep
    // vfmacc(v8) -> vfmacc(v9) at 11).
    "flw fa0, 0(t3)\n"
    "flw fa1, 128(t3)\n"
    "flw fa2, 256(t3)\n"
    "flw fa3, 384(t3)\n"
    "vle32.v v0, (a3)\n"
    "vfmacc.vf v8, fa0, v0\n"
    "vfmacc.vf v9, fa1, v0\n"
    // packet 1 (256-bit, loop_end): the carried v8/v9 complete the 4-wide vfmacc
    // EP with v10/v11 (continue at slot 1, cut at 3), then the 3 addi as one EP
    // (continue at slots 5/7), then bnez (a branch forces its own EP).
    // p-bits = 0xa2.
    "vfmacc.vf v10, fa2, v0\n"
    "vfmacc.vf v11, fa3, v0\n"
    "addi t3, t3, 4\n"
    "addi a3, a3, 128\n"
    "addi a4, a4, -32\n"
    "bnez a4, k_loop_32\n"
    "nop\n"

    // store row i.
    "vse32.v v8, (t2)\n"
    "nop\n"
    "nop\n"
    // store row i+1.
    "addi a5, t2, 128\n"
    "nop\n"
    "nop\n"
    "vse32.v v9, (a5)\n"
    "nop\n"
    "nop\n"
    // store row i+2.
    "addi a5, t2, 256\n"
    "nop\n"
    "nop\n"
    "vse32.v v10, (a5)\n"
    "nop\n"
    "nop\n"
    // store row i+3.
    "addi a5, t2, 384\n"
    "nop\n"
    "nop\n"
    "vse32.v v11, (a5)\n"
    "nop\n"
    "nop\n"
    // advance to next 4-row block + block decrement.
    "addi t1, t1, 512\n"
    "addi t2, t2, 512\n"
    "addi t0, t0, -1\n"
    // outer back-edge.
    "bnez t0, row_block_loop_32\n"
    "nop\n"
    "nop\n"

    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
