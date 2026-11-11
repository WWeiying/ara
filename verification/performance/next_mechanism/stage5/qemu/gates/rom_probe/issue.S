    .text
    .option norvc
    .global rom_full, rom_full_pc
    .type rom_full,@function
rom_full:
rom_full_pc:
    .word 0x00b5605b
    ret
    .size rom_full,.-rom_full
    .section .note.GNU-stack,"",@progbits
