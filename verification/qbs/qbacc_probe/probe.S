    .section .text
    .option push
    .option norvc
// Five scalar ABI arguments: descriptor, activation, old VD, output, CSR record.
// Each call owns its vectors from initialization through final store; no live
// architectural partial sum is assumed to survive an intervening C call.
    .macro QBACC_PROBE m, regs, lmul, sew, mnemonic, width
    .globl qbacc_m\m\()_e\width
    .type qbacc_m\m\()_e\width,@function
qbacc_m\m\()_e\width:
    li t0, (\regs * 1024 / \width)
    vsetvli zero, t0, \sew, \lmul, tu, mu
    \mnemonic v8, (a2)
    li t0, 7
    vsetvli zero, t0, e16, m8, ta, ma
    csrwi fcsr, 8
    csrwi vcsr, 5
    csrr t0, vl
    sd t0, 0(a4)
    csrr t0, vtype
    sd t0, 8(a4)
    fence rw, rw
    .word (((\m - 1 + 8) << 25) | (11 << 20) | (10 << 15) | (8 << 7) | 0x5b)
    csrr t0, vl
    sd t0, 16(a4)
    csrr t0, vtype
    sd t0, 24(a4)
    frcsr t0
    sd t0, 32(a4)
    csrr t0, vcsr
    sd t0, 40(a4)
    li t0, (\regs * 32)
    vsetvli zero, t0, e32, \lmul, tu, mu
    vse32.v v8, (a3)
    ret
    .size qbacc_m\m\()_e\width, .-qbacc_m\m\()_e\width
    .endm
    QBACC_PROBE 1, 1, m1, e8, vle8.v, 8
    QBACC_PROBE 1, 1, m1, e32, vle32.v, 32
    QBACC_PROBE 3, 4, m4, e8, vle8.v, 8
    QBACC_PROBE 3, 4, m4, e32, vle32.v, 32
    QBACC_PROBE 4, 4, m4, e8, vle8.v, 8
    QBACC_PROBE 4, 4, m4, e32, vle32.v, 32
    QBACC_PROBE 5, 8, m8, e8, vle8.v, 8
    QBACC_PROBE 5, 8, m8, e32, vle32.v, 32
    QBACC_PROBE 8, 8, m8, e8, vle8.v, 8
    QBACC_PROBE 8, 8, m8, e32, vle32.v, 32
    .option pop
