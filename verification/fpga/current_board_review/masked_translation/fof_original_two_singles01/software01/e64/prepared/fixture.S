.text
.option push
.option norvc
.balign 4
.global fx_handler
fx_handler:
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
  call fx_trap
  csrr t0,mstatus
  li t1,0x8000031888
  not t1,t1
  and t0,t0,t1
  li t1,0x1800
  or t0,t0,t1
  csrw mstatus,t0
  la t0,fx_m_resume
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
.global fx_trap_mret
fx_trap_mret:
  mret
.global fx_enter_s
fx_enter_s:
  addi sp,sp,-16
  sd ra,0(sp)
  csrw mstatus,a0
  csrw satp,a1
  fence rw,rw
  sfence.vma zero,zero
  la t0,fx_s_entry
  csrw mepc,t0
.global fx_enter_mret
fx_enter_mret:
  mret
fx_m_resume:
  ld ra,0(sp)
  addi sp,sp,16
  ret
fx_s_entry:
#if SEW == 8
  li a0,0x40000ffc
#else
  li a0,0x40001000
#endif
  la a1,fx_out
  addi a1,a1,(SEW/8)
  la a2,fx_mask
  li a3,8
  call load_1
  la t0,fx_return
  sd a0,0(t0)
  la t1,fx_post
  csrr t0,vl
  sd t0,0(t1)
  csrr t0,vtype
  sd t0,8(t1)
  csrr t0,vstart
  sd t0,16(t1)
  csrr t0,fcsr
  sd t0,24(t1)
  csrr t0,vcsr
  sd t0,32(t1)
  la t0,fx_marker
  li t1,1
.global fx_younger_store
fx_younger_store:
  sd t1,0(t0)
.global fx_ecall
fx_ecall:
  ecall
  unimp
.option pop
