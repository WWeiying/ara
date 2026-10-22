.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e32,m8,tu,mu
ret
.global op_0
op_0:
vsetvli t0,zero,e64,m1,tu,mu
vle64.v v16,(a1)
vle64.v v24,(a2)
vsetvli t0,a4,e32,m8,tu,mu
vle32.v v8,(a0)
vlm.v v0,(a5)
vsetvli t0,a3,e32,m8,tu,mu
csrr t4,frm
csrr t5,fflags
csrw frm,a6
csrwi fflags,0
vfwredosum.vs v24,v8,v16,v0.t
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw frm,t4
csrw fflags,t5
vsetvli t0,zero,e64,m1,tu,mu
vse64.v v24,(a2)
ret
.global op_1
op_1:
vsetvli t0,zero,e64,m1,tu,mu
vle64.v v16,(a1)
vle64.v v24,(a2)
vsetvli t0,a4,e32,m8,tu,mu
vle32.v v8,(a0)
vlm.v v0,(a5)
vsetvli t0,a3,e32,m8,tu,mu
csrr t4,frm
csrr t5,fflags
csrw frm,a6
csrwi fflags,0
vfwredusum.vs v24,v8,v16,v0.t
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw frm,t4
csrw fflags,t5
vsetvli t0,zero,e64,m1,tu,mu
vse64.v v24,(a2)
ret
