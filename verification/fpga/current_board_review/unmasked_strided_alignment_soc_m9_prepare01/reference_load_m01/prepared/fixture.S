#define SNAP(c,n) csrr t1,c; sd t1,8*n(t0)
.text
.option push
.option norvc
.balign 4
.global mt_handler
mt_handler:
  la t0,mt_trap_count
  ld t1,0(t0)
  li t3,2
  bgeu t1,t3,mt_bad_trap
  addi t3,t1,1
  sd t3,0(t0)
  li t3,80
  mul t3,t1,t3
  la t0,mt_records
  add t0,t0,t3
  SNAP(mcause,0); SNAP(mepc,1); SNAP(mtval,2); SNAP(mstatus,3)
  SNAP(satp,4); SNAP(vl,5); SNAP(vtype,6)
.global mt_trap_vstart_read
mt_trap_vstart_read:
  SNAP(vstart,7); SNAP(fcsr,8); SNAP(vcsr,9)
  ld t1,24(t0)
  li t4,0x8000031888
  and t1,t1,t4
  li t4,(SV39*0x800+(1-SV39)*0x1800)
  bne t1,t4,mt_bad_trap
  ld t1,32(t0)
  la t4,mt_expected_satp
  ld t4,0(t4)
  bne t1,t4,mt_bad_trap
  ld t1,40(t0); li t4,2; bne t1,t4,mt_bad_trap
  ld t1,48(t0); li t4,24; bne t1,t4,mt_bad_trap
  ld t1,64(t0); li t4,117; bne t1,t4,mt_bad_trap
  ld t1,72(t0); li t4,5; bne t1,t4,mt_bad_trap
  la t4,mt_trap_count
  ld t4,0(t4); li t5,1
  bne t4,t5,mt_check_ecall
  ld t1,0(t0); li t4,(4+2*STORE); bne t1,t4,mt_bad_trap
  ld t1,8(t0); la t4,mt_target; bne t1,t4,mt_bad_trap
  ld t1,16(t0); la t4,mt_target_addr; ld t4,0(t4); addi t4,t4,4; bne t1,t4,mt_bad_trap
  ld t1,56(t0); li t4,1; bne t1,t4,mt_bad_trap
  csrw vstart,zero
  li t1,16
  vsetvli t1,t1,e64,m1,tu,mu
  la t3,mt_fault
  addi t3,t3,16
.global mt_fault_snapshot
mt_fault_snapshot:
  vse64.v v24,(t3)
  csrr zero,vl
  fence rw,rw
  la t3,mt_mem
  addi t3,t3,16
  la t4,mt_fault_mem
  li t5,16
1:ld t1,0(t3); sd t1,0(t4); addi t3,t3,8; addi t4,t4,8; addi t5,t5,-1; bnez t5,1b
  la t3,mt_mem
  addi t3,t3,16
  li t1,0xfedcba9876543210
.global mt_poison_prefix
mt_poison_prefix:
  sd t1,0(t3)
  fence rw,rw
  li t1,2
  vsetvli t1,t1,e64,m1,tu,mu
.global mt_repair_stride
mt_repair_stride:
  li t2,8
  li t1,1
.global mt_restore_start
mt_restore_start:
  csrw vstart,t1
.global mt_retry_mret
mt_retry_mret:
  mret
mt_check_ecall:
  ld t1,0(t0); li t4,(SV39*9+(1-SV39)*11); bne t1,t4,mt_bad_trap
  ld t1,8(t0); la t4,mt_ecall; bne t1,t4,mt_bad_trap
  ld t1,16(t0); bnez t1,mt_bad_trap
  ld t1,56(t0); bnez t1,mt_bad_trap
  j mt_return_m
mt_bad_trap:
  la t0,mt_unexpected
  li t1,1
  sd t1,0(t0)
mt_return_m:
  csrr t1,mstatus
  li t3,0x8000031888
  not t3,t3
  and t1,t1,t3
  li t3,0x1800
  or t1,t1,t3
  csrw mstatus,t1
  la t1,mt_m_resume
  csrw mepc,t1
  mret
.global mt_enter
mt_enter:
  addi sp,sp,-16
  sd ra,0(sp)
  la t0,mt_frame
  sd sp,0(t0)
  csrw mstatus,a0
  csrw satp,a1
  fence rw,rw
  sfence.vma zero,zero
  la t0,mt_test_entry
  csrw mepc,t0
  mret
.global mt_m_resume
mt_m_resume:
  la t0,mt_frame
  ld sp,0(t0)
  ld ra,0(sp)
  addi sp,sp,16
  ret
mt_test_entry:
  li t1,16
  vsetvli t1,t1,e64,m1,tu,mu
  la t3,mt_seed
  addi t3,t3,16
  vle64.v v24,(t3)
  vle64.v v8,(t3)
  la a0,mt_target_addr
  ld a0,0(a0)
  li t2,4
  li t1,2
  vsetvli t1,t1,e64,m1,tu,mu
.global mt_target
mt_target:
#if STORE
  vsse64.v v24,(a0),t2
#else
  vlse64.v v24,(a0),t2
#endif
  la t0,mt_post
  SNAP(vl,0); SNAP(vtype,1); SNAP(vstart,2); SNAP(fcsr,3); SNAP(vcsr,4)
  li t1,16
  vsetvli t1,t1,e64,m1,tu,mu
  la t3,mt_result
  addi t3,t3,16
.global mt_result_snapshot
mt_result_snapshot:
  vse64.v v24,(t3)
  li t1,2
  vsetvli t1,t1,e64,m1,tu,mu
  la a1,mt_other_addr
  ld a1,0(a1)
.global mt_successor_load
mt_successor_load:
  vle64.v v8,(a1)
  addi a1,a1,64
.global mt_successor_store
mt_successor_store:
  vse64.v v8,(a1)
  la t0,mt_tail
  SNAP(vl,0); SNAP(vtype,1); SNAP(vstart,2); SNAP(fcsr,3); SNAP(vcsr,4)
  li t1,16
  vsetvli t1,t1,e64,m1,tu,mu
  la t3,mt_next
  addi t3,t3,16
.global mt_next_snapshot
mt_next_snapshot:
  vse64.v v8,(t3)
  csrr zero,vl
  fence rw,rw
  la t0,mt_marker
  li t1,1
  sd t1,0(t0)
  li t1,2
  vsetvli t1,t1,e64,m1,tu,mu
.global mt_ecall
mt_ecall:
  ecall
  unimp
.option pop
