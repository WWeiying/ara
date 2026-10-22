.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e32,m2,tu,mu
ret
.global op_0
op_0:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
vzext.vf2 v24,v8,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_1
op_1:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
vsext.vf2 v24,v8,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_2
op_2:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
vzext.vf2 v24,v25,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_3
op_3:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
vsext.vf2 v24,v25,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret

.global op_0_masked
op_0_masked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vzext.vf2 v24,v8,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_1_masked
op_1_masked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vsext.vf2 v24,v8,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_2_masked
op_2_masked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vzext.vf2 v24,v25,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_3_masked
op_3_masked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vsext.vf2 v24,v25,v0.t
csrr a0,vstart
vs2r.v v24,(a1)
ret

.global op_0_unmasked
op_0_unmasked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vzext.vf2 v24,v8
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_1_unmasked
op_1_unmasked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v8,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vsext.vf2 v24,v8
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_2_unmasked
op_2_unmasked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vzext.vf2 v24,v25
csrr a0,vstart
vs2r.v v24,(a1)
ret
.global op_3_unmasked
op_3_unmasked:
vl2re8.v v24,(a1)
vsetvli t0,a4,e16,m1,tu,mu
vle16.v v25,(a0)
vlm.v v0,(a2)
vsetvli t0,a3,e32,m2,tu,mu
csrw vstart,a5
vsext.vf2 v24,v25
csrr a0,vstart
vs2r.v v24,(a1)
ret
