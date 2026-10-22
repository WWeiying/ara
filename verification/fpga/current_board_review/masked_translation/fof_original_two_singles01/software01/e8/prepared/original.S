.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e8,m1,tu,mu
ret
.global load_0
load_0:
vsetvli t0,a3,e8,m1,tu,mu
vle8.v v24,(a1)
vlm.v v0,(a2)
vle8.v v24,(a0),v0.t
csrr a0,vl
csrr t1,vstart
slli t1,t1,32
or a0,a0,t1
vsetvli t0,a3,e8,m1,tu,mu
vse8.v v24,(a1)
ret
.global load_1
load_1:
vsetvli t0,a3,e8,m1,tu,mu
vle8.v v24,(a1)
vlm.v v0,(a2)
vle8ff.v v24,(a0),v0.t
csrr a0,vl
csrr t1,vstart
slli t1,t1,32
or a0,a0,t1
vsetvli t0,a3,e8,m1,tu,mu
vse8.v v24,(a1)
ret
