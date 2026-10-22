.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e16,m8,tu,mu
ret
.global op_0
op_0:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vrgather.vv v24,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_1
op_1:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vrgather.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_2
op_2:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vrgather.vi v24,v8,0,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_3
op_3:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vrgather.vi v24,v8,31,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_4
op_4:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmerge.vvm v24,v8,v16,v0
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_5
op_5:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmerge.vxm v24,v8,t3,v0
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_6
op_6:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmerge.vim v24,v8,-16,v0
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_7
op_7:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmerge.vim v24,v8,15,v0
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_8
op_8:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmv.v.v v24,v8
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_9
op_9:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmv.v.x v24,t3
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_10
op_10:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmv.v.i v24,-16
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_11
op_11:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vmv.v.i v24,15
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_12
op_12:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslideup.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_13
op_13:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslidedown.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_14
op_14:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslideup.vi v24,v8,0,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_15
op_15:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslideup.vi v24,v8,31,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_16
op_16:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslidedown.vi v24,v8,0,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_17
op_17:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslidedown.vi v24,v8,31,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_18
op_18:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslide1up.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_19
op_19:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vslide1down.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
.global op_20
op_20:
vsetvli t0,a4,e16,m8,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vle16.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e16,m8,tu,mu
mv t3,a6
csrw vstart,a7
vrgatherei16.vv v24,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m8,tu,mu
vse16.v v24,(a2)
ret
