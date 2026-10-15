.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e32,mf2,tu,mu
ret
.global op_0
op_0:
vsetvli t0,zero,e32,m1,tu,mu
vle32.v v16,(a1)
vle32.v v24,(a2)
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vlm.v v0,(a5)
vsetvli t0,a3,e32,mf2,tu,mu
csrr t4,frm
csrr t5,fflags
csrw frm,a6
csrw fflags,a7
vfredosum.vs v24,v8,v16,v0.t
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw frm,t4
csrw fflags,t5
vsetvli t0,zero,e32,m1,tu,mu
vse32.v v24,(a2)
ret
.global op_1
op_1:
vsetvli t0,zero,e32,m1,tu,mu
vle32.v v16,(a1)
vle32.v v24,(a2)
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vlm.v v0,(a5)
vsetvli t0,a3,e32,mf2,tu,mu
csrr t4,frm
csrr t5,fflags
csrw frm,a6
csrw fflags,a7
vfredmin.vs v24,v8,v16,v0.t
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw frm,t4
csrw fflags,t5
vsetvli t0,zero,e32,m1,tu,mu
vse32.v v24,(a2)
ret
.global op_2
op_2:
vsetvli t0,zero,e32,m1,tu,mu
vle32.v v16,(a1)
vle32.v v24,(a2)
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vlm.v v0,(a5)
vsetvli t0,a3,e32,mf2,tu,mu
csrr t4,frm
csrr t5,fflags
csrw frm,a6
csrw fflags,a7
vfredmax.vs v24,v8,v16,v0.t
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw frm,t4
csrw fflags,t5
vsetvli t0,zero,e32,m1,tu,mu
vse32.v v24,(a2)
ret
