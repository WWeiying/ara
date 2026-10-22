.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e8,m8,tu,mu
ret
.global op_0
op_0:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmand.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_1
op_1:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmnand.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_2
op_2:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmandn.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_3
op_3:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmxor.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_4
op_4:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmor.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_5
op_5:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmnor.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_6
op_6:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmorn.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_7
op_7:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmxnor.mm v8,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v8,(a2)
ret
.global op_8
op_8:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmand.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_9
op_9:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmnand.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_10
op_10:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmandn.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_11
op_11:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmxor.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_12
op_12:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmor.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_13
op_13:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmnor.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_14
op_14:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmorn.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
.global op_15
op_15:
vsetvli t0,a4,e8,m8,tu,mu
vle8.v v8,(a0)
vle8.v v16,(a1)
vlm.v v0,(a5)
vsetvli t0,a3,e8,m8,tu,mu
csrw vstart,a6
vmxnor.mm v16,v8,v16
csrr a0,vstart
vsetvli t0,a4,e8,m8,tu,mu
vsm.v v16,(a2)
ret
