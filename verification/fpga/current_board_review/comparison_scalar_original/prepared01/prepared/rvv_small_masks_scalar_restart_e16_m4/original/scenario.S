.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e16,m4,tu,mu
ret
.global op_0
op_0:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
li t3,-3
vmseq.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_1
op_1:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
li t3,-3
vmsne.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_2
op_2:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
li t3,-3
vmsltu.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_3
op_3:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
li t3,-3
vmslt.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_4
op_4:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
li t3,-3
vmsleu.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_5
op_5:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
li t3,-3
vmsle.vx v24,v8,t3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_6
op_6:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
vmseq.vi v24,v8,-3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_7
op_7:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
vmsne.vi v24,v8,-3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_8
op_8:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
vmsltu.vi v24,v8,-3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_9
op_9:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
vmslt.vi v24,v8,-3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_10
op_10:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
vmsleu.vi v24,v8,-3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
.global op_11
op_11:
vsetvli t0,a4,e16,m4,tu,mu
vle16.v v8,(a0)
vle16.v v16,(a1)
vlm.v v0,(a5)
vlm.v v24,(a2)
vsetvli t0,a3,e16,m4,tu,mu
csrw vstart,a6
vmsle.vi v24,v8,-3,v0.t
csrr a0,vstart
vsetvli t0,a4,e16,m4,tu,mu
vsm.v v24,(a2)
ret
