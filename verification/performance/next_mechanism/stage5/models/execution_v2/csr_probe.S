    .text
    .option push
    .option norvc
    .option norelax
    .globl stage5_csr_syscall_probe
    .type stage5_csr_syscall_probe,@function
// a0=vstart, a1=vcsr, a2=fcsr, a3=output, a4=issue getpid.
// No C call, floating operation or vector arithmetic in the measured interval.
stage5_csr_syscall_probe:
    addi sp,sp,-48
    csrr t0,vstart
    sd t0,0(sp)
    csrr t0,vcsr
    sd t0,8(sp)
    csrr t0,fcsr
    sd t0,16(sp)
    csrr t0,vl
    sd t0,24(sp)
    csrr t0,vtype
    sd t0,32(sp)
    mv t5,a3
    li t0,13
    vsetvli t0,t0,e16,m1,ta,ma
    csrw fcsr,a2
    csrw vcsr,a1
    csrw vstart,a0
    csrr t0,vstart
    sd t0,0(t5)
    csrr t0,vcsr
    sd t0,8(t5)
    csrr t0,fcsr
    sd t0,16(t5)
    csrr t0,vl
    sd t0,24(t5)
    csrr t0,vtype
    sd t0,32(t5)
    li a0,0
    beqz a4,.Lafter
    li a7,172
    ecall
.Lafter:
    sd a0,80(t5)
    csrr t0,vstart
    sd t0,40(t5)
    csrr t0,vcsr
    sd t0,48(t5)
    csrr t0,fcsr
    sd t0,56(t5)
    csrr t0,vl
    sd t0,64(t5)
    csrr t0,vtype
    sd t0,72(t5)
    csrwi vstart,0
    ld t0,24(sp)
    ld t1,32(sp)
    vsetvl zero,t0,t1
    ld t0,16(sp)
    csrw fcsr,t0
    ld t0,8(sp)
    csrw vcsr,t0
    ld t0,0(sp)
    csrw vstart,t0
    csrr t0,vstart
    sd t0,88(t5)
    csrr t0,vcsr
    sd t0,96(t5)
    csrr t0,fcsr
    sd t0,104(t5)
    csrr t0,vl
    sd t0,112(t5)
    csrr t0,vtype
    sd t0,120(t5)
    addi sp,sp,48
    ret
    .size stage5_csr_syscall_probe,.-stage5_csr_syscall_probe
    .option pop
    .section .note.GNU-stack,"",@progbits
