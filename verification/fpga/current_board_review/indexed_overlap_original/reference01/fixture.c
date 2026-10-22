// Original scalar program and ASM remain separate immutable inputs.
#define _start original_start
#define gather32 io_gather
#define masked_restart32 io_masked
#ifdef IO_HOST
#include "host_original.c"
#else
#include "original.c"
#endif
#undef _start
#undef gather32
#undef masked_restart32

#ifdef IO_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned rounds, masked;
static long minor;
static long call(long n,long x,long y,long z,long u,long v,long w) {
    (void)u; (void)v; (void)w;
    if(n==279) return 3;
    if(n==64) { if(x==1) fwrite((void*)y,1,z,stdout); return z; }
    if(n==222) return (long)pages;
    if(n==165) { ((struct rusage*)y)->ru_minflt=minor; return 0; }
    if(n==215) return 0;
    if(n==94) { if(!x && (rounds!=50 || masked!=(
#ifdef FAULT_PAGES
        0
#else
        1
#endif
        ))) exit(100); exit(x); }
    abort();
}
long io_gather(const index_type *idx,const void *p,data_type *o,long overlap) {
    if(overlap!=OVERLAP) abort();
    for(unsigned i=0;i<32;++i) {
        if(idx[i]!=((i*13u+7u)%32u)*4096u) abort();
        uint32_t v; memcpy(&v,(const char*)p+idx[i],4); o[i]=v;
        printf("HOST_VALUE %u %u %08x\n",rounds,i,v);
    }
    ++rounds; minor+=32;
    return 32;
}
long io_masked(const index_type *idx,const void *p,data_type *o) {
    for(unsigned i=0;i<32;++i) {
        uint32_t v; memcpy(&v,(const char*)p+idx[i],4);
        o[i]=(i>=7 && i<17 && (i&1)) ? v:(uint32_t)-7;
        printf("HOST_MASK %u %08x\n",i,o[i]);
    }
    ++masked; return 32;
}
int main(void) { original_start(); return 100; }
#else
#define READ(c,x) asm volatile("csrr %0," #c : "=r"(x) : : "memory")
#define WRITE(c,x) asm volatile("csrw " #c ",%0" : : "r"((uint64_t)(x)) : "memory")
#define VA UINT64_C(0x40000000)
extern long gather32(const index_type*,const void*,data_type*,long);
extern long masked_restart32(const index_type*,const void*,data_type*);
extern void io_handler(void),io_enter_s(uint64_t,uint64_t);
extern void replay_text(const char*);
extern long replay_write(long,long,long,long);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
volatile uint64_t io_pt[3][512] __attribute__((aligned(4096)));
volatile uint64_t io_errors,io_checks,io_round,io_mask_count,io_minor,io_maps,io_unmaps;
volatile uint64_t io_exit_code=UINT64_MAX,io_done,io_target_pc,io_satp;
volatile uint64_t io_records[50][32][7],io_fault_count[50];
volatile uint64_t io_result[51][39];
static void check(uint64_t got,uint64_t want) {
    ++io_checks;
    if(got!=want) {
        if(!io_errors) replay_mismatch(io_round,io_checks,want,got);
        ++io_errors;
    }
}
static uint64_t pte(const void *p) { return ((uint64_t)p>>12<<10)|0xc3; }
__attribute__((noinline)) void io_checkpoint(void) { asm volatile("" : : : "memory"); }
static void post(data_type *out,long got,unsigned masked) {
    unsigned r=masked ? 50:io_round;
    uint64_t vl,vt,vs,fc,vc;
    READ(vl,vl); READ(vtype,vt); READ(vstart,vs); READ(fcsr,fc); READ(vcsr,vc);
    check(got,32); check(vl,32); check(vt,17); check(vs,0); check(fc,117); check(vc,5);
    io_result[r][0]=vl; io_result[r][1]=vt; io_result[r][2]=vs;
    io_result[r][3]=fc; io_result[r][4]=vc;
    for(unsigned i=0;i<32;++i) {
        check(indices[i],((i*13u+7u)%32u)*4096u);
        uint32_t want=masked && !(i>=7 && i<17 && (i&1)) ? (uint32_t)-7:expected(indices[i]);
        check(out[i],want); io_result[r][5+i]=out[i];
    }
    check(output[0],0x5b12); check(output[33],0x5b12);
    io_result[r][37]=output[0]; io_result[r][38]=output[33];
    io_checkpoint();
}
long io_gather(const index_type *idx,const void *p,data_type *out,long overlap) {
    long vl=gather32(idx,p,out,overlap);
    post(out,vl,0); ++io_round; return vl;
}
long io_masked(const index_type *idx,const void *p,data_type *out) {
    long vl=masked_restart32(idx,p,out);
    post(out,vl,1); ++io_mask_count; return vl;
}
// Scalar-only handler: never writes vstart/vtype or executes a vector instruction.
int io_trap(uint64_t *x) {
    uint64_t cause,pc,tval,vs,vl,vt,fc,vc;
    READ(mcause,cause); READ(mepc,pc); READ(mtval,tval); READ(vstart,vs);
    READ(vl,vl); READ(vtype,vt); READ(fcsr,fc); READ(vcsr,vc);
    if(cause==13) {
        if(io_round>=50 || vs>=32) { ++io_errors; return 1; }
        unsigned r=io_round,n=io_fault_count[r]++;
        if(n>=32) { ++io_errors; return 1; }
        uint64_t record[7]={pc,tval,vs,vl,vt,fc,vc};
        for(unsigned j=0;j<7;++j) io_records[r][n][j]=record[j];
        check(n,vs); check(vl,32); check(vt,17); check(fc,117); check(vc,5);
        check(*(const uint32_t*)pc,OVERLAP ? 0x0645f207:0x0645f807);
        if(!io_target_pc) io_target_pc=pc;
        check(pc,io_target_pc); check(tval,VA+indices[vs]);
        if(io_errors) return 1;
        unsigned page=(tval-VA)>>12;
        check(io_pt[2][page],0);
        io_pt[2][page]=pte((const char*)pages+page*4096);
        asm volatile("fence rw,rw\n.global io_repair_sfence\nio_repair_sfence:\n"
                     "sfence.vma %0,zero" : : "r"(tval) : "memory");
        ++io_minor;
        return 0; // mepc unchanged: retry, no index reload or CSR reconstruction.
    }
    if(cause!=9) { ++io_errors; return 1; }
    long n=x[17],a=x[10],b=x[11],c=x[12];
    long result=0;
    switch(n) {
    case 279: result=3; break;
    case 64:
        if(a==3) { check(b,(uint64_t)pages); check(c,sizeof(pages)); result=c; }
        else result=replay_write(n,a,b,c);
        break;
    case 222:
        check(a,0); check(b,sizeof(pages)); check(c,1);
        check(x[13],2); check(x[14],3); check(x[15],0);
        for(unsigned i=0;i<32;++i) io_pt[2][i]=0;
        asm volatile("sfence.vma zero,zero" : : : "memory");
        ++io_maps; result=VA; break;
    case 165: ((struct rusage*)b)->ru_minflt=io_minor; break;
    case 215:
        check(a,VA); check(b,sizeof(pages)); check(io_fault_count[io_round-1],32);
        for(unsigned i=0;i<32;++i) check(io_pt[2][i],pte((const char*)pages+i*4096));
        for(unsigned i=0;i<32;++i) io_pt[2][i]=0;
        asm volatile("sfence.vma zero,zero" : : : "memory");
        ++io_unmaps; break;
    case 94: io_exit_code=a; return 1;
    default: ++io_errors; return 1;
    }
    x[10]=result; WRITE(mepc,pc+4); return io_errors!=0;
}
int main(void) {
    uint64_t status; READ(mstatus,status);
    WRITE(mie,0); WRITE(medeleg,0); WRITE(mideleg,0);
    WRITE(fcsr,117); WRITE(vcsr,5); WRITE(vstart,0); WRITE(mtvec,io_handler);
    io_pt[0][1]=((uint64_t)io_pt[1]>>12<<10)|1;
    io_pt[0][2]=0x200000cf; // Proven fixture identity-mapped S-mode code/data.
    io_pt[1][0]=((uint64_t)io_pt[2]>>12<<10)|1;
    io_satp=(UINT64_C(8)<<60)|((uint64_t)io_pt[0]>>12);
    io_enter_s((status&~UINT64_C(0x8000031888))|0x2a00,io_satp);
    WRITE(satp,0); asm volatile("sfence.vma zero,zero" : : : "memory");
    check(io_exit_code,0); check(io_round,50);
#ifdef FAULT_PAGES
    check(io_mask_count,0); check(io_minor,1600); check(io_maps,50); check(io_unmaps,50);
#else
    check(io_mask_count,1); check(io_minor,0); check(io_maps,0); check(io_unmaps,0);
#endif
    uint64_t diff=0;
    for(unsigned i=0;i<32768;++i) diff|=pages[i]^((i*7919u)^0xa5a50f0fu);
    check(diff,0);
    for(unsigned i=0;i<512;++i) {
        check(io_pt[0][i],i==1 ? ((uint64_t)io_pt[1]>>12<<10)|1:i==2 ? 0x200000cf:0);
        check(io_pt[1][i],i==0 ? ((uint64_t)io_pt[2]>>12<<10)|1:0);
        check(io_pt[2][i],0);
    }
    io_done=UINT64_C(0x525656303146494e);
    replay_text(io_errors ? "INDEXED_ORIGINAL_FAIL\n":"INDEXED_ORIGINAL_PASS\n");
    return io_errors!=0;
}
#endif
