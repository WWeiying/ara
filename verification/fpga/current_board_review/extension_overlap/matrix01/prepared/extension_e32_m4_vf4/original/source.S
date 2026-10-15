.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e32,m4,tu,mu
ret
.global op_0
op_0:
vl4re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m4,tu,mu
vzext.vf4 v24,v8,v0.t
csrr a0,vstart
vs4r.v v24,(a1)
ret
.global op_1
op_1:
vl4re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m4,tu,mu
vsext.vf4 v24,v8,v0.t
csrr a0,vstart
vs4r.v v24,(a1)
ret
.global op_2
op_2:
vl4re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v27,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m4,tu,mu
vzext.vf4 v24,v27,v0.t
csrr a0,vstart
vs4r.v v24,(a1)
ret
.global op_3
op_3:
vl4re8.v v24,(a1)
vsetvli t0,a4,e8,m1,tu,mu
vle8.v v27,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m4,tu,mu
vsext.vf4 v24,v27,v0.t
csrr a0,vstart
vs4r.v v24,(a1)
ret
