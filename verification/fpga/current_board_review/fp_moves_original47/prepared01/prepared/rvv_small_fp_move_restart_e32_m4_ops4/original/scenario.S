.text
.global capacity
capacity:
li t0,-1
vsetvli a0,t0,e32,m4,tu,mu
ret
.global op_0
op_0:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfmerge.vfm v24,v8,ft0,v0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
.global op_1
op_1:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfmv.v.f v24,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
.global op_2
op_2:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfslide1up.vf v24,v8,ft0,v0.t
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
.global op_3
op_3:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfslide1down.vf v24,v8,ft0,v0.t
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
.global op_4
op_4:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfslide1up.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
.global op_5
op_5:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfslide1down.vf v24,v8,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
.global op_6
op_6:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfmv.s.f v24,ft0
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
.global op_7
op_7:
csrr t5,fflags
vsetvli t0,a4,e32,m4,tu,mu
vle32.v v8,(a0)
vle32.v v24,(a2)
vlm.v v0,(a5)
fld ft0,0(a1)
vsetvli t0,a3,e32,m4,tu,mu
srli t2,a6,32
csrw fflags,t2
slli t2,a6,32
srli t2,t2,32
csrw vstart,t2
vfmv.f.s ft1,v8
fmv.x.d t2,ft1
sd t2,0(a7)
csrr a0,vstart
csrr t1,fflags
slli t1,t1,32
or a0,a0,t1
csrw fflags,t5
vsetvli t0,a4,e32,m4,tu,mu
vse32.v v24,(a2)
ret
