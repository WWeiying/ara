.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e64,m2,tu,mu
ret
.global op_0
op_0:
vl2re8.v v24,(a1)
vsetvli t0,a4,e32,m1,tu,mu
vle32.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m2,tu,mu
vzext.vf2 v24,v8,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_1
op_1:
vl2re8.v v24,(a1)
vsetvli t0,a4,e32,m1,tu,mu
vle32.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m2,tu,mu
vsext.vf2 v24,v8,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_2
op_2:
vl2re8.v v24,(a1)
vsetvli t0,a4,e32,m1,tu,mu
vle32.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m2,tu,mu
vzext.vf2 v24,v25,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_3
op_3:
vl2re8.v v24,(a1)
vsetvli t0,a4,e32,m1,tu,mu
vle32.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e64,m2,tu,mu
vsext.vf2 v24,v25,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
