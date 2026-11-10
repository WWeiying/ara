    .text
    .option norvc
    .macro ISSUE name, word
    .global gate_\name
    .global gate_\name\()_pc
    .type gate_\name,@function
gate_\name:
gate_\name\()_pc:
    .word \word
    ret
    .size gate_\name,.-gate_\name
    .endm
    ISSUE full, 0x00b5605b
    ISSUE refill, 0x02a0605b
    ISSUE release, 0x0000505b
    ISSUE v1full, 0x00b5205b
    ISSUE v1refill, 0x02a0205b
    ISSUE row64, 0x0005305b
    ISSUE row96, 0x0405305b
    ISSUE row128, 0x0205305b
    ISSUE column, 0x0005705b
    ISSUE panel, 0x0205705b
    ISSUE qk, 0x0605705b
    ISSUE pv, 0x0485705b
    ISSUE bad_rd, 0x0605715b
    ISSUE bad_source, 0x0445705b
    ISSUE alias, 0x0485745b
    ISSUE bad_full, 0x00b560db
    ISSUE info, 0x0005455b

    .global gate_vectors
    .type gate_vectors,@function
gate_vectors:
    li t0,1024
    vsetvli zero,t0,e8,m8,ta,ma
    vle8.v v0,(a0)
    addi a0,a0,1024
    vle8.v v8,(a0)
    addi a0,a0,1024
    vle8.v v16,(a0)
    addi a0,a0,1024
    vle8.v v24,(a0)
    li t0,384
    vsetvli zero,t0,e16,m8,tu,ma
    vle16.v v8,(a1)
    li t1,3072
    sub a0,a0,t1
    li t0,128
    vsetvli zero,t0,e32,m4,ta,ma
    vle32.v v0,(a0)
    ret
    .size gate_vectors,.-gate_vectors

    .global gate_capture
    .type gate_capture,@function
gate_capture:
    beqz a5,1f
    li t0,16
    beq a2,t0,2f
    vsetvli zero,a3,e32,m2,ta,ma
    vse32.v v0,(a0)
    li t0,1
    beq a4,t0,3f
    addi a0,a0,256
    vse32.v v2,(a0)
    j 3f
2:  vsetvli zero,a3,e16,m2,ta,ma
    vse16.v v0,(a0)
    li t0,1
    beq a4,t0,3f
    addi a0,a0,256
    vse16.v v2,(a0)
    j 3f
1:  li t0,128
    vsetvli zero,t0,e32,m4,ta,ma
    vse32.v v0,(a0)
3:  li t0,512
    vsetvli zero,t0,e8,m4,ta,ma
    vse8.v v4,(a1)
    addi a1,a1,512
    li t0,1024
    vsetvli zero,t0,e8,m8,ta,ma
    vse8.v v8,(a1)
    addi a1,a1,1024
    vse8.v v16,(a1)
    addi a1,a1,1024
    vse8.v v24,(a1)
    ret
    .size gate_capture,.-gate_capture
    .section .note.GNU-stack,"",@progbits
