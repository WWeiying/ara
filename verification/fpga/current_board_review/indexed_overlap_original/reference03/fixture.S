// M/S transition adapted from sealed NF2 fixture; no vector operation in handler.
.text
.option push
.option norvc
.balign 4
.global io_handler
io_handler:
  addi sp,sp,-256
  sd ra,8(sp)
  sd gp,24(sp)
  sd tp,32(sp)
  sd t0,40(sp)
  sd t1,48(sp)
  sd t2,56(sp)
  sd s0,64(sp)
  sd s1,72(sp)
  sd a0,80(sp)
  sd a1,88(sp)
  sd a2,96(sp)
  sd a3,104(sp)
  sd a4,112(sp)
  sd a5,120(sp)
  sd a6,128(sp)
  sd a7,136(sp)
  sd s2,144(sp)
  sd s3,152(sp)
  sd s4,160(sp)
  sd s5,168(sp)
  sd s6,176(sp)
  sd s7,184(sp)
  sd s8,192(sp)
  sd s9,200(sp)
  sd s10,208(sp)
  sd s11,216(sp)
  sd t3,224(sp)
  sd t4,232(sp)
  sd t5,240(sp)
  sd t6,248(sp)
  mv a0,sp
  call io_trap
  beqz a0,io_restore
  csrr t0,mstatus
  li t1,0x1800
  or t0,t0,t1
  csrw mstatus,t0
  la t0,io_m_resume
  csrw mepc,t0
io_restore:
  ld ra,8(sp)
  ld gp,24(sp)
  ld tp,32(sp)
  ld t0,40(sp)
  ld t1,48(sp)
  ld t2,56(sp)
  ld s0,64(sp)
  ld s1,72(sp)
  ld a0,80(sp)
  ld a1,88(sp)
  ld a2,96(sp)
  ld a3,104(sp)
  ld a4,112(sp)
  ld a5,120(sp)
  ld a6,128(sp)
  ld a7,136(sp)
  ld s2,144(sp)
  ld s3,152(sp)
  ld s4,160(sp)
  ld s5,168(sp)
  ld s6,176(sp)
  ld s7,184(sp)
  ld s8,192(sp)
  ld s9,200(sp)
  ld s10,208(sp)
  ld s11,216(sp)
  ld t3,224(sp)
  ld t4,232(sp)
  ld t5,240(sp)
  ld t6,248(sp)
  addi sp,sp,256
.global io_retry_mret
io_retry_mret:
  mret
.global io_enter_s
io_enter_s:
  addi sp,sp,-112
  sd ra,0(sp)
  sd s0,8(sp)
  sd s1,16(sp)
  sd s2,24(sp)
  sd s3,32(sp)
  sd s4,40(sp)
  sd s5,48(sp)
  sd s6,56(sp)
  sd s7,64(sp)
  sd s8,72(sp)
  sd s9,80(sp)
  sd s10,88(sp)
  sd s11,96(sp)
  la t0,io_machine_sp
  sd sp,0(t0)
  csrw mstatus,a0
  csrw satp,a1
  fence rw,rw
  sfence.vma zero,zero
  la t0,original_start
  csrw mepc,t0
  mret
io_m_resume:
  la t0,io_machine_sp
  ld sp,0(t0)
  ld ra,0(sp)
  ld s0,8(sp)
  ld s1,16(sp)
  ld s2,24(sp)
  ld s3,32(sp)
  ld s4,40(sp)
  ld s5,48(sp)
  ld s6,56(sp)
  ld s7,64(sp)
  ld s8,72(sp)
  ld s9,80(sp)
  ld s10,88(sp)
  ld s11,96(sp)
  addi sp,sp,112
  ret
.option pop
.bss
.balign 8
io_machine_sp: .zero 8

