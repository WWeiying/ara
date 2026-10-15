.text
.global run_case
.type run_case,@function
run_case:
li t0,-1
csrwi vstart,0
csrwi fflags,0
vsetvli t1,t0,e16,m1,tu,mu
vle16.v v8,(a0)
vle16.v v24,(a2)
vlm.v v0,(a3)
vsetivli t1,2,e16,m1,tu,mu
li t3,0
csrwi vstart,1
.global repro_target
repro_target:
vrgather.vx v24,v8,t3,v0.t
.global repro_after_target
repro_after_target:
csrr t1,vstart
.global repro_after_vstart
repro_after_vstart:
sd t1,0(a5)
csrr t1,fflags
sd t1,8(a5)
csrr t1,vl
sd t1,16(a5)
vsetvli t1,t0,e16,m1,tu,mu
vse16.v v24,(a2)
ret
.size run_case,.-run_case
