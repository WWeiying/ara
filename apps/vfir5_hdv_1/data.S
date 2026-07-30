.section .data.src1
.align 4
.global src1
src1:
    .rept 8192
    .word 0x3f800000
    .endr

.section .data.src2
.align 4
.global src2
src2:
    .rept 8192
    .word 0x00000000
    .endr
