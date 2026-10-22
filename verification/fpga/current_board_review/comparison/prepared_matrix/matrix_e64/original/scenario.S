.text
.global cmp
cmp:
vsetvli t0,a5,e64,m8,tu,mu
vle64.v v8,(a1)
vle64.v v16,(a2)
vlm.v v24,(a3)
vlm.v v0,(a6)
vsetvli t0,a4,e64,m8,tu,mu
srli t0,a0,3
andi t0,t0,1
csrw fflags,t0
csrw vstart,a7
andi t0,a0,4
andi a0,a0,3
bnez t0,unmasked
li t0,0
beq a0,t0,m0
li t0,1
beq a0,t0,m1
li t0,2
beq a0,t0,m2
j m3
m0:
vmfeq.vv v24,v8,v16,v0.t
j done
m1:
vmfne.vv v24,v8,v16,v0.t
j done
m2:
vmflt.vv v24,v8,v16,v0.t
j done
m3:
vmfle.vv v24,v8,v16,v0.t
j done
unmasked:
li t0,0
beq a0,t0,u0
li t0,1
beq a0,t0,u1
li t0,2
beq a0,t0,u2
j u3
u0:
vmfeq.vv v24,v8,v16
j done
u1:
vmfne.vv v24,v8,v16
j done
u2:
vmflt.vv v24,v8,v16
j done
u3:
vmfle.vv v24,v8,v16
j done
done:
csrr a0,vstart
csrr t0,fflags
slli t0,t0,32
or a0,a0,t0
vsetvli t0,a5,e64,m8,tu,mu
vsm.v v24,(a3)
ret
.global inspect
inspect:
vse64.v v8,(a0)
vse64.v v16,(a1)
vsm.v v0,(a2)
ret
