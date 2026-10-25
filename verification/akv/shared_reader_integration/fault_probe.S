.option push
.option norvc
.option norelax
.text
.balign 4
.global rf_qbs_only
.type rf_qbs_only,@function
rf_qbs_only:
    fence rw, rw
    li t0, 32
    vsetvli zero, t0, e32, m1, ta, ma
    vle32.v v8, (a2)
    .word 0x00b5045b
    vse32.v v8, (a3)
    vmv.x.s t0, v8
    fence rw, rw
    ret
.size rf_qbs_only,.-rf_qbs_only
.option pop
