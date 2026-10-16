# Encodings used only in NOP slots of the hash-pinned diagnostic kernel.
.section .text
.option norvc
.globl probe_load, probe_compare, probe_trap
probe_load:
    ld a2, 136(a0)
probe_compare:
    addi a2, a2, -63
probe_trap:
    .option rvc
    c.bnez a2, resume
    c.ebreak
resume:
    nop
