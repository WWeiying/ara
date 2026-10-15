.text
.option push
.option norvc
.balign 4
.global mx_bootstrap
mx_bootstrap:
  la a5,mx_action_source
  la a1,mx_action_copy
  .word 0xcdb1f057
  .word 0x0207f407
  .word 0x0205f427
  ret
.global mx_snapshot
mx_snapshot:
  li t0,128
  vsetvli t0,t0,e64,m8,tu,mu
  addi a0,a0,64
  vse64.v v24,(a0)
  fence rw,rw
  ret
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
  bnez a0,mx_return_m
  li t0,8
  vsetvli t0,t0,e64,m8,tu,mu
  la t0,mx_restart
  ld t0,0(t0)
  csrw vstart,t0
  j mx_restore
mx_return_m:
  csrr t0,mstatus
  li t1,0x8000031888
  not t1,t1
  and t0,t0,t1
  li t1,0x1800
  or t0,t0,t1
  csrw mstatus,t0
  la t0,mx_m_resume
  csrw mepc,t0
mx_restore:
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
  li a0,0x40001000
  la a1,mx_input
  la a2,mx_out
  addi a2,a2,8
  la a3,mx_mask
  li a4,128
  la a5,mx_stride
  la t0,mx_store
  ld t0,0(t0)
  bnez t0,1f
  call replay_0
  j 2f
1:call replay_1
2:la t0,mx_return
  sd a0,0(t0)
  la t0,mx_case
  ld t0,0(t0)
  li t1,48
  mul t0,t0,t1
  la t1,mx_post
  add t1,t1,t0
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
  sd a0,40(t1)
  la a0,mx_result
  call mx_snapshot
  la t0,mx_marker
  li t1,1
.global mx_younger_store
mx_younger_store:
  sd t1,0(t0)
.global mx_ecall
mx_ecall:
  ecall
  unimp
.option pop

