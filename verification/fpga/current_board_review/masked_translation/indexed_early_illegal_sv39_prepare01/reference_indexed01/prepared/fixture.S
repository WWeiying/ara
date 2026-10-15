// SPDX-License-Identifier: SHL-0.51
// Ordered indexed prefix followed by alignment fault and same-PC restart.
#define SNAP(c,n) csrr t1,c; sd t1,8*n(t0)
#define SNAPSTORE(n) vse32.v v##n,(t3); addi t3,t3,128
#define LOAD(n) vle32.v v##n,(t3); addi t3,t3,128
#define REGS(op) op(16); op(24); op(23); op(25); op(20); op(8); op(17)
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
  li t3,96
  mul t3,t1,t3
  la t0,mt_records
  add t0,t0,t3
  SNAP(mcause,0); SNAP(mepc,1); SNAP(mtval,2); SNAP(mstatus,3)
  SNAP(satp,4); SNAP(vl,5); SNAP(vtype,6)
.global mt_trap_vstart_read
mt_trap_vstart_read:
  SNAP(vstart,7)
  SNAP(fcsr,8); SNAP(vcsr,9)
  la t3,mt_marker
  ld t1,0(t3)
  sd t1,80(t0)
  la t3,mt_pages
  li t4,16392
  add t3,t3,t4
  ld t1,0(t3)
  sd t1,88(t0)
  // Reject wrong mode/CSR/control state before any vector or repair operation.
  ld t1,24(t0)
  li t4,0x8000031888
  and t1,t1,t4
  li t4,0x800
  bne t1,t4,mt_bad_trap
  ld t1,32(t0)
  la t4,mt_expected_satp
  ld t4,0(t4)
  bne t1,t4,mt_bad_trap
  ld t1,40(t0)
  li t4,3
  bne t1,t4,mt_bad_trap
  ld t1,48(t0)
  li t4,24
  bne t1,t4,mt_bad_trap
  ld t1,56(t0)
  la t4,mt_trap_count
  ld t4,0(t4)
  li t5,1
  bne t4,t5,1f
  li t4,2
  bne t1,t4,mt_bad_trap
  j 2f
1: bnez t1,mt_bad_trap
2:
  ld t1,64(t0)
  li t4,117
  bne t1,t4,mt_bad_trap
  ld t1,72(t0)
  li t4,5
  bne t1,t4,mt_bad_trap
  la t4,mt_trap_count
  ld t4,0(t4)
  li t5,1
  bne t4,t5,mt_check_ecall
  ld t1,0(t0)
  li t4,6
  bne t1,t4,mt_bad_trap
  ld t1,8(t0)
  la t4,mt_target
  bne t1,t4,mt_bad_trap
  ld t1,16(t0)
  li t4,0x40000011
  bne t1,t4,mt_bad_trap
  ld t1,80(t0)
  bnez t1,mt_bad_trap
  ld t1,88(t0)
  la t4,mt_repair_pte
  ld t4,0(t4)
  bne t1,t4,mt_bad_trap
  csrw vstart,zero
  li t1,32
  vsetvli t1,t1,e32,m1,tu,mu
  la t3,mt_fault
  addi t3,t3,64
  REGS(SNAPSTORE)
  csrr zero,vl
  fence rw,rw
  la t0,mt_pages
  la t3,mt_prefix
  addi t3,t3,64
  li t4,1024
3: ld t1,0(t0)
  sd t1,0(t3)
  addi t0,t0,8
  addi t3,t3,8
  addi t4,t4,-1
  bnez t4,3b
.global mt_prefix_checkpoint
mt_prefix_checkpoint:
  nop
  la t3,mt_pages
  addi t3,t3,8
  li t1,0xbad0123456789abc
.global mt_prefix_poison
mt_prefix_poison:
  sd t1,0(t3)
  fence rw,rw
  li t1,16
  vsetvli t1,t1,e64,m1,tu,mu
  la t3,mt_fix_index
.global mt_repair_index
mt_repair_index:
  vle64.v v16,(t3)
  li t1,3
  vsetvli t1,t1,e64,m1,tu,mu
  la t0,mt_records
  ld t1,56(t0)
.global mt_restart_vstart_write
mt_restart_vstart_write:
  csrw vstart,t1
  la t0,mt_restart
  SNAP(vl,0); SNAP(vtype,1); SNAP(vstart,2)
.global mt_retry_mret
mt_retry_mret:
  mret
mt_check_ecall:
  ld t1,0(t0)
  li t4,9
  bne t1,t4,mt_bad_trap
  ld t1,8(t0)
  la t4,mt_ecall
  bne t1,t4,mt_bad_trap
  ld t1,16(t0)
  bnez t1,mt_bad_trap
  ld t1,80(t0)
  li t4,1
  bne t1,t4,mt_bad_trap
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

.global mt_enter_s
mt_enter_s:
  addi sp,sp,-16
  sd ra,0(sp)
  la t0,mt_frame
  sd sp,0(t0)
  csrw mstatus,a0
  csrw satp,a1
  fence rw,rw
  sfence.vma zero,zero
  la t0,mt_s_entry
  csrw mepc,t0
  mret
.global mt_m_resume
mt_m_resume:
  la t0,mt_frame
  ld sp,0(t0)
  ld ra,0(sp)
  addi sp,sp,16
  ret

.global mt_s_entry
mt_s_entry:
  li t1,32
  vsetvli t1,t1,e32,m1,tu,mu
  la t3,mt_seed
  addi t3,t3,64
  REGS(LOAD)
  li a0,0x40000000
  la a2,mt_mask
  li a3,3
  li t2,0
  vsetvli t0,a3,e64,m1,tu,mu
  vlm.v v0,(a2)
.global mt_target
mt_target:
  vsoxei64.v v24,(a0),v16,v0.t
  la t0,mt_post
  SNAP(vl,0); SNAP(vtype,1); SNAP(vstart,2); SNAP(fcsr,3); SNAP(vcsr,4)

  // Different index/data/address/mask owner after exception cleanup.
  la a2,mt_mask
  addi a2,a2,16
  vlm.v v0,(a2)
  li t2,0x40000100
.global mt_successor_indexed_store
mt_successor_indexed_store:
  vsoxei64.v v8,(t2),v20,v0.t
  la t0,mt_store_post
  SNAP(vl,0); SNAP(vtype,1); SNAP(vstart,2); SNAP(fcsr,3); SNAP(vcsr,4)
.global mt_recovery_load
mt_recovery_load:
  vle64.v v8,(t2),v0.t
  la t0,mt_load_post
  SNAP(vl,0); SNAP(vtype,1); SNAP(vstart,2); SNAP(fcsr,3); SNAP(vcsr,4)
  la a2,mt_mask
  addi a2,a2,32
  vlm.v v0,(a2)
.global mt_successor_add
mt_successor_add:
  vadd.vi v8,v8,1,v0.t
  la t0,mt_after
  SNAP(vl,0); SNAP(vtype,1); SNAP(vstart,2); SNAP(fcsr,3); SNAP(vcsr,4)
  la t0,mt_marker
  li t1,1
.global mt_younger_store
mt_younger_store:
  sd t1,0(t0)
  li t1,32
  vsetvli t1,t1,e32,m1,tu,mu
  la t3,mt_result
  addi t3,t3,64
  REGS(SNAPSTORE)
  csrr zero,vl
  fence rw,rw
  li t1,3
  vsetvli t1,t1,e64,m1,tu,mu
.global mt_ecall
mt_ecall:
  ecall
  unimp
.option pop

