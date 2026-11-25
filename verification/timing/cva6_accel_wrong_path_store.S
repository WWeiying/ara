/* Train a single branch site on legal vector stores, then invert it with a
   different destination. A wrong-path accelerator store must not escape. */
.text
.global main
.type main, @function
main:
  addi sp, sp, -32
  sd ra, 24(sp)
  sd s0, 16(sp)
  sd s1, 8(sp)
  vsetivli zero, 8, e64, m1, ta, ma
  vmv.v.i v8, 7
  li s0, 16
1:
  li s1, 32
2:
  la a0, legal_target
  li a1, 0
  call maybe_store
  addi s1, s1, -1
  bnez s1, 2b
  la a0, guard_target
  li a1, 1
  call maybe_store
  addi s0, s0, -1
  bnez s0, 1b
  fence rw, rw
  la t0, legal_target
  la t1, guard_target
  li t2, 7
  li t3, 8
  li a0, 1
3:
  ld t4, 0(t0)
  bne t4, t2, 4f
  ld t4, 0(t1)
  bnez t4, 4f
  addi t0, t0, 8
  addi t1, t1, 8
  addi t3, t3, -1
  bnez t3, 3b
  li a0, 0
4:
  ld ra, 24(sp)
  ld s0, 16(sp)
  ld s1, 8(sp)
  addi sp, sp, 32
  ret
.size main, .-main

maybe_store:
  bnez a1, 1f
  vse64.v v8, (a0)
1:
  ret

.bss
.balign 64
legal_target: .zero 64
guard_target: .zero 64
