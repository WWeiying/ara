.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e64,m8,tu,mu
ret
.global op_0
op_0:
vl8re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m8,tu,mu
vzext.vf8 v24,v8,v0.t
csrr a0,vstart
vs8r.v v24,(a1)
ret
.global op_1
op_1:
vl8re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m8,tu,mu
vsext.vf8 v24,v8,v0.t
csrr a0,vstart
vs8r.v v24,(a1)
ret
.global op_2
op_2:
vl8re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v31,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m8,tu,mu
vzext.vf8 v24,v31,v0.t
csrr a0,vstart
vs8r.v v24,(a1)
ret
.global op_3
op_3:
vl8re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v31,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m8,tu,mu
vsext.vf8 v24,v31,v0.t
csrr a0,vstart
vs8r.v v24,(a1)
ret
