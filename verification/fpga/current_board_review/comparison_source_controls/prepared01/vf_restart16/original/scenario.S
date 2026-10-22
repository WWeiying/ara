.text
.global compare
compare:
    vsetvli t0,zero,e8,m8,tu,mu
    vlm.v v24,(a2)
    vlm.v v0,(a3)
    li t1,64
    vsetvli t0,t1,e16,m1,tu,mu
    vle16.v v8,(a0)
    vle16.v v16,(a1)
    li t1,0xffffffffffff3c00
    fmv.d.x ft0,t1
    li t1,32
    vsetvli t0,t1,e16,m1,tu,mu
    li t1,33
    csrw fcsr,t1
    li t1,5
    csrw vcsr,t1
    csrw vstart,a4
    csrr t0,vl
    sd t0,0(a5)
    csrr t0,vtype
    sd t0,8(a5)
    csrr t0,vstart
    sd t0,16(a5)
    csrr t0,fflags
    sd t0,24(a5)
    csrr t0,frm
    sd t0,32(a5)
    csrr t0,vcsr
    sd t0,40(a5)
.global source_target
source_target:
    vmfeq.vf v24,v8,ft0,v0.t
.global source_after
source_after:
    csrr t0,vl
    sd t0,48(a5)
    csrr t0,vtype
    sd t0,56(a5)
    csrr t0,vstart
    sd t0,64(a5)
    csrr t0,fflags
    sd t0,72(a5)
    csrr t0,frm
    sd t0,80(a5)
    csrr t0,vcsr
    sd t0,88(a5)
    vsetvli t0,zero,e8,m8,tu,mu
    vsm.v v24,(a2)
    li t1,64
    vsetvli t0,t1,e16,m1,tu,mu
    ret
.global capture_predicate
capture_predicate:
    vsetvli t0,zero,e8,m8,tu,mu
    vsm.v v0,(a0)
    ret
