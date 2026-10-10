/* Ordinary Linux system calls may clobber vectors. No ecall is used while
 * state is live: test scheduler preemption, asynchronous signals, or faults. */
    .text
    .option push
    .option arch, +v
    .align 2
    .globl rvv_vlenb
    .type rvv_vlenb, @function
rvv_vlenb:
    csrr a0, vlenb
    ret
    .size rvv_vlenb, .-rvv_vlenb

    .globl rvv_add_u32
    .type rvv_add_u32, @function
rvv_add_u32:
    beqz a3, 2f
1:  vsetvli t0, a3, e32, m1, tu, mu
    vle32.v v8, (a0)
    vle32.v v9, (a1)
    vadd.vv v10, v8, v9
    vse32.v v10, (a2)
    slli t1, t0, 2
    add a0, a0, t1
    add a1, a1, t1
    add a2, a2, t1
    sub a3, a3, t0
    bnez a3, 1b
2:  ret
    .size rvv_add_u32, .-rvv_add_u32

    .globl rvv_max_f32
    .type rvv_max_f32, @function
rvv_max_f32:
    vsetivli zero, 1, e32, m1, tu, mu
    vle32.v v3, (a1)
    vsetvli zero, a3, e32, m1, tu, mu
    vle32.v v2, (a0)
    vfredmax.vs v1, v2, v3
    vsetivli zero, 1, e32, m1, tu, mu
    vse32.v v1, (a2)
    ret
    .size rvv_max_f32, .-rvv_max_f32

    .macro load_all base, stride, ptr
    mv \ptr, \base
    vl8re8.v v0, (\ptr)
    add \ptr, \ptr, \stride
    vl8re8.v v8, (\ptr)
    add \ptr, \ptr, \stride
    vl8re8.v v16, (\ptr)
    add \ptr, \ptr, \stride
    vl8re8.v v24, (\ptr)
    .endm

    .globl rvv_clobber_state
    .type rvv_clobber_state, @function
rvv_clobber_state:
    csrwi vstart, 0
    vsetvli t0, zero, e8, m1, tu, mu
    csrr t1, vlenb
    slli t1, t1, 3
    load_all a0, t1, t2
    csrwi vcsr, 0
    ret
    .size rvv_clobber_state, .-rvv_clobber_state

/* a0=input bytes, a1=snapshot, a2=vl/vtype/vstart/vcsr snapshot,
 * a3=kind (0 parent,1 child,2 signal,3 fault,4 illegal),
 * a4=shared turn/signal count/fault address, a5=handshake rounds. */
    .globl rvv_context_probe
    .type rvv_context_probe, @function
rvv_context_probe:
    addi sp, sp, -48
    sd s0, 40(sp)
    sd s1, 32(sp)
    sd s2, 24(sp)
    sd s3, 16(sp)
    sd s4, 8(sp)
    sd s5, 0(sp)
    mv s0, a1
    mv s1, a2
    mv s2, a3
    mv s3, a4
    mv s4, a5
    csrr s5, vlenb
    slli s5, s5, 3
    csrwi vstart, 0
    vsetvli t0, zero, e8, m1, tu, mu
    load_all a0, s5, t1
    li a0, 0
    li t0, 1
    beq s2, t0, .Lchild_csrs
    vsetivli zero, 9, e16, m2, tu, mu
    csrwi vcsr, 3
    csrwi vstart, 3
    j .Lselect
.Lchild_csrs:
    vsetivli zero, 11, e8, m2, tu, mu
    csrwi vcsr, 5
    csrwi vstart, 1
.Lselect:
    li t0, 2
    beq s2, t0, .Lsignal
    li t0, 3
    beq s2, t0, .Lfault
    li t0, 4
    beq s2, t0, .Lillegal
    beqz s2, .Lparent
.Lchild:
    lw t0, 0(s3)
    beqz t0, .Lchild
    fence rw, rw
    sw zero, 0(s3)
    addi s4, s4, -1
    bnez s4, .Lchild
    j .Lsnapshot
.Lparent:
    li t0, 1
    fence rw, rw
    sw t0, 0(s3)
.Lparent_wait:
    lw t0, 0(s3)
    bnez t0, .Lparent_wait
    fence rw, rw
    addi s4, s4, -1
    bnez s4, .Lparent
    j .Lsnapshot
.Lsignal:
    lw t1, 0(s3)
1:  lw t0, 0(s3)
    beq t0, t1, 1b
    j .Lsnapshot
.Lfault:
    .globl rvv_fault_site
rvv_fault_site:
    ld a0, 0(s3)
    j .Lsnapshot
.Lillegal:
    .globl rvv_illegal_site
rvv_illegal_site:
    .2byte 0
    .globl rvv_illegal_resume
rvv_illegal_resume:
.Lsnapshot:
    csrr t0, vl
    sd t0, 0(s1)
    csrr t0, vtype
    sd t0, 8(s1)
    csrr t0, vstart
    sd t0, 16(s1)
    csrr t0, vcsr
    sd t0, 24(s1)
    csrwi vstart, 0
    vs8r.v v0, (s0)
    add s0, s0, s5
    vs8r.v v8, (s0)
    add s0, s0, s5
    vs8r.v v16, (s0)
    add s0, s0, s5
    vs8r.v v24, (s0)
    csrwi vcsr, 0
    ld s0, 40(sp)
    ld s1, 32(sp)
    ld s2, 24(sp)
    ld s3, 16(sp)
    ld s4, 8(sp)
    ld s5, 0(sp)
    addi sp, sp, 48
    ret
    .size rvv_context_probe, .-rvv_context_probe
    .option pop
    .section .note.GNU-stack,"",@progbits
