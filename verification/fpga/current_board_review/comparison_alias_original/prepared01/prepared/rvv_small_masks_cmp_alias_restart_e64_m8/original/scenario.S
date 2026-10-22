.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e64,m8,tu,mu
ret
.global op_0
op_0:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmseq.vv v8,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_1
op_1:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsne.vv v8,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_2
op_2:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsltu.vv v8,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_3
op_3:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmslt.vv v8,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_4
op_4:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsleu.vv v8,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_5
op_5:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsle.vv v8,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_6
op_6:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmseq.vv v16,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_7
op_7:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsne.vv v16,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_8
op_8:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsltu.vv v16,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_9
op_9:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmslt.vv v16,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_10
op_10:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsleu.vv v16,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_11
op_11:
vsetvli t0,a4,e64,m8,tu,mu
vle64.v v8,(a0)
vle64.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e64,m8,tu,mu
csrw vstart,a6
vmsle.vv v16,v8,v16,v0.t
csrr a0,vstart
vsetvli t0,a4,e64,m8,tu,mu
vsm.v v16,(a2)
ret
