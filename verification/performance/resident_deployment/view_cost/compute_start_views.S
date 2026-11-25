    .section .text.init
    .globl _start
_start:
    la sp, compute_stack_top
    la t0, trap
    csrw mtvec, t0
    csrwi medeleg, 0
    csrwi mideleg, 0
    li t0, -1
    csrw pmpaddr0, t0
    li t0, 0x1f
    csrw pmpcfg0, t0

    la t0, root_page
    li t1, 1536
.Lclear_tables:
    sd zero, 0(t0)
    addi t0, t0, 8
    addi t1, t1, -1
    bnez t1, .Lclear_tables

    /* Only the low identity and MMIO mappings retain gigapage leaves. */
    la t0, root_page
    li t1, 0x200000ef
    sd t1, 16(t0)
    li t1, 0x300000ef
    sd t1, 24(t0)

    /* VA 0xffffffc000000000: L2[256] -> L1[0] -> 512 L0 leaves. */
    la t1, high_l1
    srli t1, t1, 2
    ori t1, t1, 1
    li t2, 2048
    add t2, t0, t2
    sd t1, 0(t2)
    la t0, high_l1
    la t1, high_l0
    srli t1, t1, 2
    ori t1, t1, 1
    sd t1, 0(t0)
    la t0, high_l0
    li t1, 0x200000c7
    li t2, 512
.Lmap_pages:
    /* S-only RW, A/D set, no execute/global; contiguous physical 4KiB pages. */
    sd t1, 0(t0)
    addi t0, t0, 8
    addi t1, t1, 1024
    addi t2, t2, -1
    bnez t2, .Lmap_pages

    fence rw, rw
    la t0, root_page
    srli t0, t0, 12
    li t1, 0x8000000000000000
    or t0, t0, t1
    csrw satp, t0
    sfence.vma zero, zero
    li t0, 0x6e00
    csrw mstatus, t0
    la t0, supervisor_main
    csrw mepc, t0
    mret

supervisor_main:
    csrwi fcsr, 0
    csrwi vstart, 0
    la t0, root_page
    srli t1, t0, 12
    li t2, 0x8000000000000000
    or t1, t1, t2
    csrr t2, satp
    bne t1, t2, .Lmapping_bad
    li t2, 2048
    add t0, t0, t2
    ld t1, 0(t0)
    la t2, high_l1
    srli t2, t2, 2
    ori t2, t2, 1
    bne t1, t2, .Lmapping_bad
    la t0, high_l1
    ld t1, 0(t0)
    la t2, high_l0
    srli t2, t2, 2
    ori t2, t2, 1
    bne t1, t2, .Lmapping_bad
    la t0, high_l0
    li t1, 0x200000c7
    li t2, 512
.Lcheck_pages:
    ld t3, 0(t0)
    bne t1, t3, .Lmapping_bad
    addi t0, t0, 8
    addi t1, t1, 1024
    addi t2, t2, -1
    bnez t2, .Lcheck_pages

    /* Read the marker through the high alias and compare with low identity. */
    la t0, mapping_ok
    li t1, 0xffffffbf80000000
    add t1, t0, t1
    li t2, 0xc0000000
.Lprint_checked:
    lbu t3, 0(t0)
    lbu t4, 0(t1)
    bne t3, t4, .Lmapping_bad
    beqz t3, .Lcompute
    sb t4, 0(t2)
    addi t0, t0, 1
    addi t1, t1, 1
    j .Lprint_checked
.Lcompute:
    call main
.Lexit:
    li t0, 0xd0000000
    sd a0, 0(t0)
.Lhalt:
    j .Lhalt

.Lmapping_bad:
    la t0, mapping_bad
    li t1, 0xc0000000
.Lprint_bad:
    lbu t2, 0(t0)
    beqz t2, .Lfail
    sb t2, 0(t1)
    addi t0, t0, 1
    j .Lprint_bad
.Lfail:
    li a0, 1
    j .Lexit

    .balign 4
trap:
    csrr a0, mcause
    csrr a1, mtval
    csrr a2, mepc
    call trap_report
    j .Lfail

    .section .rodata
mapping_ok:
    .asciz "RESIDENT_VIEWS_MAPPING sv39_high_va_4k_512_contiguous\n"
mapping_bad:
    .asciz "RESIDENT_VIEWS_TRAP mapping_check\n"

    .section .bss
    .balign 4096
root_page:
    .space 4096
high_l1:
    .space 4096
high_l0:
    .space 4096
    .balign 16
    .space 65536
compute_stack_top:
    .section .note.GNU-stack,"",@progbits
