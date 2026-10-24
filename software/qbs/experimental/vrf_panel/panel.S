    .section .text
    .option push
    .option norvc
    .option norelax
    .p2align 2

// Internal leaf: the C wrapper validates all seven standard scalar ABI args.
// a0 records, a1 count, a2/out0, a3/out1, a4 stride elements, a5/n0, a6/n1.
    .globl qbs_vrf_panel_asm
    .hidden qbs_vrf_panel_asm
    .type qbs_vrf_panel_asm,@function
qbs_vrf_panel_asm:
    mv t0, a0
    mv t1, a1
    slli a4, a4, 2
    fence rw, rw
    li t2, 128
    vsetvli zero, t2, e32, m4, tu, mu

    ld a1, 16(t0)
    ld a0, 0(t0)
    .word 0x06b5045b                 // QBEXEC M4 v8, a0, a1
    ld a0, 8(t0)
    .word 0x06b5085b                 // QBEXEC M4 v16, a0, a1
    addi t1, t1, -1
    addi t0, t0, 24
    beqz t1, .Lstore
.Lstripe:
    ld a1, 16(t0)
    ld a0, 0(t0)
    .word 0x16b5045b                 // QBACC M4 v8, a0, a1
    ld a0, 8(t0)
    .word 0x16b5085b                 // QBACC M4 v16, a0, a1
    addi t1, t1, -1
    addi t0, t0, 24
    bnez t1, .Lstripe

.Lstore:
    vsetvli zero, a5, e32, m1, tu, mu
    vse32.v v8, (a2)
    add a2, a2, a4
    vse32.v v9, (a2)
    add a2, a2, a4
    vse32.v v10, (a2)
    add a2, a2, a4
    vse32.v v11, (a2)
    vsetvli zero, a6, e32, m1, tu, mu
    vse32.v v16, (a3)
    add a3, a3, a4
    vse32.v v17, (a3)
    add a3, a3, a4
    vse32.v v18, (a3)
    add a3, a3, a4
    vse32.v v19, (a3)
    // Ara serializes scalar extracts behind all older vector instructions.
    vmv.x.s t2, v19
    fence rw, rw
    ret
    .size qbs_vrf_panel_asm, .-qbs_vrf_panel_asm

    .globl qbs_vrf_panel_info
    .hidden qbs_vrf_panel_info
    .type qbs_vrf_panel_info,@function
qbs_vrf_panel_info:
    .word 0x0005155b                 // QBINFO a0, a0
    ret
    .size qbs_vrf_panel_info, .-qbs_vrf_panel_info

    .globl qbs_vrf_panel_vlenb
    .hidden qbs_vrf_panel_vlenb
    .type qbs_vrf_panel_vlenb,@function
qbs_vrf_panel_vlenb:
    csrr a0, vlenb
    ret
    .size qbs_vrf_panel_vlenb, .-qbs_vrf_panel_vlenb
    .option pop
    .section .note.GNU-stack,"",@progbits
