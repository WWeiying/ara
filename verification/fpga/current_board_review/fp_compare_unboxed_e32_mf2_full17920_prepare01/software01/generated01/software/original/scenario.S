.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e32,mf2,tu,mu
ret
.global op_0
op_0:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfeq.vv v24,v8,v16
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_1
op_1:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfne.vv v24,v8,v16
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_2
op_2:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmflt.vv v24,v8,v16
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_3
op_3:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfle.vv v24,v8,v16
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_4
op_4:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
lwu t2,0(a1)
fmv.d.x ft0,t2
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfeq.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_5
op_5:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
lwu t2,0(a1)
fmv.d.x ft0,t2
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfne.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_6
op_6:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
lwu t2,0(a1)
fmv.d.x ft0,t2
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmflt.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_7
op_7:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
lwu t2,0(a1)
fmv.d.x ft0,t2
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfle.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_8
op_8:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
lwu t2,0(a1)
fmv.d.x ft0,t2
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfgt.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
.global op_9
op_9:
csrr t5,fflags
vsetvli t0,a4,e32,mf2,tu,mu
vle32.v v8,(a0)
vle32.v v16,(a1)
vlm.v v24,(a2)
vlm.v v0,(a5)
lwu t2,0(a1)
fmv.d.x ft0,t2
vsetvli t0,a3,e32,mf2,tu,mu
csrw fflags,a7
vmfge.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,mf2,tu,mu
vsm.v v24,(a2)
ret
