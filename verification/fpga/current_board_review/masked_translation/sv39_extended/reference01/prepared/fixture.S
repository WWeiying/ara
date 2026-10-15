// Independent S-mode execution and precise, unchanged-PC restart.
.text
.option push
.option norvc
.balign 4
.global mx_snapshot
mx_snapshot:
  li t0,64
  vsetvli t0,t0,e16,m1,tu,mu
  addi a0,a0,64
  vse16.v v23,(a0)
  addi a0,a0,128
  vse16.v v24,(a0)
  addi a0,a0,128
  vse16.v v25,(a0)
  csrr zero,vl
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
  vsetvli t0,t0,e16,m1,tu,mu
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
  la t0,mx_current
  ld t2,0(t0)
  slli t0,t2,9
  la t1,mx_seed
  add t1,t1,t0
  addi t1,t1,64
  li t0,64
  vsetvli t0,t0,e16,m1,tu,mu
  vle16.v v23,(t1)
  addi t1,t1,128
  vle16.v v24,(t1)
  addi t1,t1,128
  vle16.v v25,(t1)
  la t1,mx_mask
  slli t0,t2,4
  add t1,t1,t0
  vlm.v v0,(t1)
  li t0,8
  vsetvli t0,t0,e16,m1,tu,mu
  la t0,mx_args
  ld a0,0(t0)
  ld t3,8(t0)
  ld t1,16(t0)
  jr t1
.global mx_unit_load
mx_unit_load:
  vle16.v v24,(a0),v0.t
  j mx_after
.global mx_unit_store
mx_unit_store:
  vse16.v v24,(a0),v0.t
  j mx_after
.global mx_stride_load
mx_stride_load:
  vlse16.v v24,(a0),t3,v0.t
  j mx_after
.global mx_stride_store
mx_stride_store:
  vsse16.v v24,(a0),t3,v0.t
  j mx_after
.global mx_fof_load
mx_fof_load:
  vle16ff.v v24,(a0),v0.t
mx_after:
  li t0,40
  mul t0,t0,t2
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
  li t0,6
  bltu t2,t0,1f
  li t0,8
  j 2f
1:li t0,64
2:vsetvli t0,t0,e16,m1,tu,mu
  li t0,260
  mul t0,t0,t2
  la t1,mx_out
  add t1,t1,t0
  addi t1,t1,2
  vse16.v v24,(t1)
  slli t0,t2,9
  la a0,mx_result
  add a0,a0,t0
  call mx_snapshot
  la t0,mx_marker
  slli t1,t2,3
  add t0,t0,t1
  li t1,1
.global mx_younger_store
mx_younger_store:
  sd t1,0(t0)
  li t0,8
  vsetvli t0,t0,e16,m1,tu,mu
.global mx_ecall
mx_ecall:
  ecall
  unimp
.option pop
