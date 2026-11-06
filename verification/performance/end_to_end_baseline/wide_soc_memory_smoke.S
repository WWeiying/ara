// Ordinary RVV only. Scalar ABI; v0/v8 and caller-saved scalar registers clobbered.
  .section .text
  .option push
  .option norvc
  .balign 4
  .globl wide_soc_memory_smoke_scalar
  .type wide_soc_memory_smoke_scalar,@function
wide_soc_memory_smoke_scalar:
  beqz a0, .Lscalar8
  li t0, 1
  beq a0, t0, .Lscalar16
  li t0, 2
  beq a0, t0, .Lscalar32
  sd a2, (a1)
  fence rw, rw
  ld a0, (a1)
  ret
.Lscalar8:
  sb a2, (a1)
  fence rw, rw
  lbu a0, (a1)
  ret
.Lscalar16:
  sh a2, (a1)
  fence rw, rw
  lhu a0, (a1)
  ret
.Lscalar32:
  sw a2, (a1)
  fence rw, rw
  lwu a0, (a1)
  ret
  .size wide_soc_memory_smoke_scalar,.-wide_soc_memory_smoke_scalar

  .globl wide_soc_memory_smoke_signed
  .type wide_soc_memory_smoke_signed,@function
wide_soc_memory_smoke_signed:
  beqz a0, .Lsigned8
  li t0, 1
  beq a0, t0, .Lsigned16
  li t0, 2
  beq a0, t0, .Lsigned32
  ld a0, (a1)
  ret
.Lsigned8:
  lb a0, (a1)
  ret
.Lsigned16:
  lh a0, (a1)
  ret
.Lsigned32:
  lw a0, (a1)
  ret
  .size wide_soc_memory_smoke_signed,.-wide_soc_memory_smoke_signed

  .globl wide_soc_memory_smoke_vlmax
  .type wide_soc_memory_smoke_vlmax,@function
wide_soc_memory_smoke_vlmax:
  beqz a0, .Lmax8
  li t0, 1
  beq a0, t0, .Lmax16
  li t0, 2
  beq a0, t0, .Lmax32
  vsetvli a0, zero, e64, m1, tu, mu
  ret
.Lmax8:
  vsetvli a0, zero, e8, m1, tu, mu
  ret
.Lmax16:
  vsetvli a0, zero, e16, m1, tu, mu
  ret
.Lmax32:
  vsetvli a0, zero, e32, m1, tu, mu
  ret
  .size wide_soc_memory_smoke_vlmax,.-wide_soc_memory_smoke_vlmax

// a0=dst a1=src a2=observed a3=seed a4=mask a5=AVL a6=flags.
// Each path executes exactly eight vector instructions. The last store spans
// VLMAX, allowing C to check tu/mu lanes and to skip agnostic register bytes.
  .macro MEMORY_CASE bits
  .balign 4
  .globl wide_soc_memory_smoke_e\bits
  .type wide_soc_memory_smoke_e\bits,@function
wide_soc_memory_smoke_e\bits:
  vsetvli t0, zero, e\bits, m1, tu, mu
  vle\bits\().v v8, (a3)
  vlm.v v0, (a4)
  andi t2, a6, 2
  beqz t2, .Lagnostic\@
  vsetvli t1, a5, e\bits, m1, tu, mu
  j .Ltransfer\@
.Lagnostic\@:
  vsetvli t1, a5, e\bits, m1, ta, ma
.Ltransfer\@:
  andi t2, a6, 1
  beqz t2, .Lunmasked\@
  vle\bits\().v v8, (a1), v0.t
  vse\bits\().v v8, (a0), v0.t
  j .Lobserve\@
.Lunmasked\@:
  vle\bits\().v v8, (a1)
  vse\bits\().v v8, (a0)
.Lobserve\@:
  fence rw, rw
  vsetvli zero, t0, e\bits, m1, tu, mu
  vse\bits\().v v8, (a2)
  fence rw, rw
  mv a0, t1
  ret
  .size wide_soc_memory_smoke_e\bits,.-wide_soc_memory_smoke_e\bits
  .endm
  MEMORY_CASE 8
  MEMORY_CASE 16
  MEMORY_CASE 32
  MEMORY_CASE 64
  .option pop
