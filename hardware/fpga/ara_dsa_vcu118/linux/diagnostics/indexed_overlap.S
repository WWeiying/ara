.section .text
.global _start
_start:
    li s0, 0
    li s1, 1000
    la a6, table
    la s2, output
#ifdef FAULT_TABLE
map_table:
    li a0, 0
    li a1, 131072
    li a2, 3
    li a3, 0x22
    li a4, -1
    li a5, 0
    li a7, 222
    ecall
    bltz a0, failed
    mv a6, a0
#ifdef PREFAULT
    li a1, 32
    li a2, 4096
6:
    lw a3, 0(a0)
    add a0, a0, a2
    addi a1, a1, -1
    bnez a1, 6b
#endif
#endif
1:
    li a0, 32
    vsetvli a5, a0, e64, m2, ta, ma
#ifdef EXACT_WIDEN
    la a1, indices
    vle16.v v12, (a1)
    vle16.v v1, (a1)
    vzext.vf4 v2, v12
    vzext.vf4 v12, v1
#else
    vid.v v2
#endif
#ifdef FAULT_TABLE
    vsll.vi v2, v2, 12
#else
    vsll.vi v2, v2, 2
#endif
    vsetvli zero, zero, e32, m1, ta, ma
    bnez s0, 2f
    vluxei64.v v8, (a6), v2
    vse32.v v8, (s2)
    j 3f
2:
    vluxei64.v v2, (a6), v2
    vse32.v v2, (s2)
3:
    mv a0, s2
    li a1, 32
    li a2, 0x3f800000
#ifdef FAULT_TABLE
    li a2, 0
#endif
4:
    lw a3, 0(a0)
    bne a2, a3, failed
    addi a0, a0, 4
    addi a1, a1, -1
    bnez a1, 4b
    addi s1, s1, -1
    bnez s1, 1b
    li a0, 1
    la a1, ok_control
    li a2, 11
    beqz s0, 5f
    la a1, ok_overlap
5:
    li a7, 64
    ecall
    bnez s0, passed
    li s0, 1
    li s1, 1000
#ifdef FAULT_TABLE
    j map_table
#endif
    j 1b
passed:
    li a0, 0
    j exit
failed:
    addi a0, s0, 10
exit:
    li a7, 93
    ecall
.section .rodata
ok_control: .ascii "CONTROL_OK\n"
ok_overlap: .ascii "OVERLAP_OK\n"
.balign 128
table: .fill 32,4,0x3f800000
.balign 64
indices:
.set idx,0
.rept 32
    .2byte idx
    .set idx,idx+1
.endr
.section .bss
.balign 128
output: .skip 128
