.text
.option push
.option norvc
.balign 4
.global mx_handler
mx_handler:
  addi sp,sp,-128
  sd ra,0(sp)
  sd t0,8(sp)
  sd t1,16(sp)
  sd t2,24(sp)
  sd t3,32(sp)
  sd t4,40(sp)
  sd t5,48(sp)
  sd t6,56(sp)
  sd a0,64(sp)
  sd a1,72(sp)
  sd a2,80(sp)
  sd a3,88(sp)
  sd a4,96(sp)
  sd a5,104(sp)
  sd a6,112(sp)
  sd a7,120(sp)
  call mx_trap
  csrr t0,mstatus
  li t1,0x8000031888
  not t1,t1
  and t0,t0,t1
  li t1,0x1800
  or t0,t0,t1
  csrw mstatus,t0
  la t0,mx_m_resume
  csrw mepc,t0
  ld ra,0(sp)
  ld t0,8(sp)
  ld t1,16(sp)
  ld t2,24(sp)
  ld t3,32(sp)
  ld t4,40(sp)
  ld t5,48(sp)
  ld t6,56(sp)
  ld a0,64(sp)
  ld a1,72(sp)
  ld a2,80(sp)
  ld a3,88(sp)
  ld a4,96(sp)
  ld a5,104(sp)
  ld a6,112(sp)
  ld a7,120(sp)
  addi sp,sp,128
.global mx_trap_mret
mx_trap_mret:
  mret
.global mx_enter_s
mx_enter_s:
  addi sp,sp,-16
  sd ra,0(sp)
  csrw mstatus,a0
  csrw satp,a1
  fence rw,rw
  sfence.vma zero,zero
  la t0,mx_s_entry
  csrw mepc,t0
  mret
mx_m_resume:
  ld ra,0(sp)
  addi sp,sp,16
  ret
mx_s_entry:
  la t0,mx_args
  ld a0,0(t0)
  ld a1,8(t0)
  ld a2,16(t0)
  ld a3,24(t0)
  ld a4,32(t0)
  ld a5,40(t0)
  ld a6,48(t0)
  ld a7,56(t0)
  ld t0,64(t0)
  jalr t0
  la t0,mx_return
  sd a0,0(t0)
  la t0,mx_case
  ld t0,0(t0)
  slli t0,t0,5
  la t1,mx_post
  add t1,t1,t0
  csrr t0,vl
  sd t0,0(t1)
  csrr t0,vtype
  sd t0,8(t1)
  csrr t0,vstart
  sd t0,16(t1)
  sd a0,24(t1)
.global mx_ecall
mx_ecall:
  ecall
  unimp
.option pop
