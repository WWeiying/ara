.text
.option push
.option norvc
.balign 4
.global nx_snapshot
nx_snapshot:
  csrw vstart,zero
  addi a0,a0,64
  vs1r.v v16,(a0)
  addi a0,a0,128
  .irp reg,23,24,25,26,27,28,29,30,31
  vs1r.v v\reg,(a0)
  addi a0,a0,128
  .endr
  fence rw,rw
  ret
.global nx_handler
nx_handler:
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
  call nx_trap
  bnez a0,nx_return_m
  vsetivli zero,8,e32,mf2,tu,mu
  la t0,nx_restart
  ld t0,0(t0)
  csrw vstart,t0
  j nx_restore
nx_return_m:
  csrr t0,mstatus
  li t1,0x8000031888
  not t1,t1
  and t0,t0,t1
  li t1,0x1800
  or t0,t0,t1
  csrw mstatus,t0
  la t0,nx_m_resume
  csrw mepc,t0
nx_restore:
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
.global nx_retry_mret
nx_retry_mret:
  mret
.global nx_enter_s
nx_enter_s:
  addi sp,sp,-16
  sd ra,0(sp)
  csrw mstatus,a0
  csrw satp,a1
  fence rw,rw
  sfence.vma zero,zero
  la t0,nx_s_entry
  csrw mepc,t0
  mret
nx_m_resume:
  ld ra,0(sp)
  addi sp,sp,16
  ret
nx_s_entry:
  la t1,nx_seed
  addi t1,t1,64
  li t0,32
  vsetvli zero,t0,e32,m1,tu,mu
  vle32.v v16,(t1)
  addi t1,t1,128
  .irp reg,23,24,25,26,27,28,29,30,31
  vle32.v v\reg,(t1)
  addi t1,t1,128
  .endr
  la t0,nx_args
  ld a0,0(t0)
  la a1,nx_input
  la a2,nx_output
  addi a2,a2,4
  la a3,nx_mask
  li a4,16
  la a5,nx_stride
  ld t0,8(t0)
  jalr ra,t0,0
  la t1,nx_post
  sd a0,0(t1)
  csrr t0,vl
  sd t0,8(t1)
  csrr t0,vtype
  sd t0,16(t1)
  csrr t0,vstart
  sd t0,24(t1)
  csrr t0,fcsr
  sd t0,32(t1)
  csrr t0,vcsr
  sd t0,40(t1)
  la a0,nx_result
  call nx_snapshot
  la t0,nx_marker
  li t1,1
.global nx_younger_store
nx_younger_store:
  sd t1,0(t0)
.global nx_ecall
nx_ecall:
  ecall
  unimp
.option pop
