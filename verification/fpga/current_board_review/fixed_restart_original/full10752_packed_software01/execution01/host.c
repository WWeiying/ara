#define _GNU_SOURCE
#include "host_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define NEED(C) do { if(!(C)) { fprintf(stderr,"HOST_REJECT line=%d condition=%s calls=%u\n",__LINE__,#C,calls); exit(90); } } while(0)
typedef struct { char bank; unsigned offset,value; } Event;
typedef struct { unsigned seed,op,vl,mode,si,start,control; } Tuple;
static Event source_events[4416], mask_events[4][512];
static unsigned n_source, n_mask[4], collecting_mask, selected_mode, clear_notes;
static uint8_t source_a[3][512],source_b[3][512],source_mask[4][128];
static unsigned calls, packed_run, mutation, lifecycle_mutation, injected;
static unsigned source_cursor, mask_epoch, mask_clear, mask_selected;
static unsigned init_index,init_calls,read_index,read_calls;
static uint64_t gold_bytes, gold_sat, total_selected;
static char uart[2][65536];
static size_t uart_size[2];
static State state;
static uint8_t *probe;
static unsigned probe_init,probe_reads;

static Tuple tuple(unsigned n) {
    static const unsigned lengths[]={0,1,2,3,256,511,512};
    Tuple t;
    t.control=n%8;n/=8;t.si=n%4;n/=4;t.mode=n%4;n/=4;
    t.vl=lengths[n%7];n/=7;t.op=n%4;t.seed=n/4;
    t.start=t.si==0 ? 1:t.si==1 ? t.vl/2:t.si==2 ? t.vl:511;
    return t;
}
void source_note(char bank,unsigned offset,unsigned value) {
    if(!collecting_mask) {
        NEED(bank=='a' || bank=='b'); NEED(n_source<4416);
        source_events[n_source++]=(Event){bank,offset,value};
    } else if(bank=='z') {
        NEED(offset==clear_notes && value==0); ++clear_notes;
    } else {
        NEED(bank=='m' && n_mask[selected_mode]<512);
        mask_events[selected_mode][n_mask[selected_mode]++]=(Event){bank,offset,value};
    }
}
static void original_evidence(void) {
    original_reset();
    for(unsigned seed=0;seed<3;++seed) {
        original_seed(seed); State s=original_state();
        memcpy(source_a[seed],s.a,512); memcpy(source_b[seed],s.b,512);
    }
    NEED(n_source==4416);
    collecting_mask=1;
    for(selected_mode=0;selected_mode<4;++selected_mode) {
        clear_notes=0; original_mask(selected_mode);
        NEED(clear_notes==128);
        memcpy(source_mask[selected_mode],original_state().mask,128);
    }
    NEED(n_mask[0]==512 && n_mask[1]==256 && n_mask[2]==73 && n_mask[3]==0);
    original_reset();
}

static int inside(const void *p,const void *base,size_t size) {
    uintptr_t v=(uintptr_t)p,b=(uintptr_t)base;
    return v>=b && v-b<size;
}
static uint64_t load_value(const void *p,size_t n) {
    uint64_t v=0; NEED(n==1 || n==2 || n==8); memcpy(&v,p,n); return v;
}
void *host_copy(void *dst,const void *src,size_t n) {
    if(probe) {
        if(inside(dst,probe,514)) {
            size_t off=(uintptr_t)dst-(uintptr_t)probe;
            NEED(off==(probe_init<64 ? probe_init*8:512));
            NEED(n==(probe_init<64 ? 8:2) && off+n<=514);
            ++probe_init;
        }
        if(inside(src,probe,514)) {
            size_t off=(uintptr_t)src-(uintptr_t)probe;
            NEED(off==(probe_reads%65<64 ? (probe_reads%65)*8:512));
            NEED(n==(probe_reads%65<64 ? 8:2) && off+n<=514);
            ++probe_reads;
        }
        return memcpy(dst,src,n);
    }
    NEED(packed_run);
    if(inside(dst,state.a,1024) || inside(dst,state.b,1024)) {
        char bank=inside(dst,state.a,1024) ? 'a':'b';
        unsigned off=(unsigned)((uintptr_t)dst-(uintptr_t)(bank=='a' ? state.a:state.b));
        if(lifecycle_mutation==1 && !injected && n==1 && *(uint8_t *)dst==load_value(src,n)) { injected=1; return dst; }
        NEED(n==1 && source_cursor<4416);
        Event e=source_events[source_cursor++];
        NEED(e.bank==bank && e.offset==off && e.value==load_value(src,n));
    } else if(inside(dst,state.mask,128)) {
        NEED(calls<10752 && calls%32==0 && mask_epoch==calls/32);
        unsigned off=(unsigned)((uintptr_t)dst-(uintptr_t)state.mask);
        unsigned mode=tuple(calls).mode;
        if(n==8) {
            NEED(mask_clear<16 && mask_selected==0 && off==mask_clear*8);
            NEED(load_value(src,n)==0); ++mask_clear;
        } else {
            if(lifecycle_mutation==2 && !injected && mask_selected==1) { injected=1; return dst; }
            NEED(n==1 && mask_clear==16 && mask_selected<n_mask[mode]);
            Event e=mask_events[mode][mask_selected++];
            NEED(off==e.offset && load_value(src,n)==e.value); ++total_selected;
        }
        if(mask_clear==16 && mask_selected==n_mask[mode]) {
            ++mask_epoch; mask_clear=mask_selected=0;
        }
    } else if(inside(dst,state.out,1026)) {
        if(lifecycle_mutation==3 && !injected && calls==1 && init_index==1) { injected=1; return dst; }
        unsigned off=(unsigned)((uintptr_t)dst-(uintptr_t)state.out);
        NEED(calls<10752 && read_calls==calls && init_calls==calls && init_index<65);
        NEED(off==(init_index<64 ? init_index*8:512));
        NEED(n==(init_index<64 ? 8:2));
        NEED(load_value(src,n)==(n==8 ? UINT64_C(0x5b5b5b5b5b5b5b5b):UINT64_C(0x5b5b)));
        if(++init_index==65) { init_index=0; ++init_calls; }
    } else if(inside(src,state.out,1026)) {
        if(lifecycle_mutation==4 && !injected && read_index==3) { injected=1; return memcpy(dst,src,n); }
        unsigned off=(unsigned)((uintptr_t)src-(uintptr_t)state.out);
        NEED(calls>0 && read_calls==calls-1 && read_index<65);
        NEED(off==(read_index<64 ? read_index*8:512));
        NEED(n==(read_index<64 ? 8:2));
        if(++read_index==65) { read_index=0; ++read_calls; }
    } else {
        NEED(0);
    }
    return memcpy(dst,src,n);
}

unsigned long capacity(void) { return 512; }
unsigned long fixed_host_vlenb(void) { return 128; }
long replay_write(long n,long fd,long p,long len) {
    NEED(n==64 && fd==1 && len>=0);
    size_t *used=&uart_size[packed_run];
    NEED(*used+(size_t)len<sizeof uart[0]);
    memcpy(uart[packed_run]+*used,(void *)p,(size_t)len); *used+=(size_t)len;
    uart[packed_run][*used]=0; return len;
}

static unsigned long helper(unsigned op,const uint8_t *a,const uint8_t *b,uint8_t *out,
    unsigned long vl,unsigned long cap,const uint8_t *mask,unsigned long start,unsigned long control) {
    NEED(calls<10752); Tuple t=tuple(calls);
    NEED(t.op==op && t.vl==vl && t.start==start && t.control==control && cap==512);
    NEED(a==state.a && b==state.b && out==state.out+1 && mask==state.mask);
    NEED(!memcmp(a,source_a[t.seed],512) && !memcmp(b,source_b[t.seed],512));
    NEED(!memcmp(mask,source_mask[t.mode],128));
    for(unsigned i=512;i<1024;++i) NEED(a[i]==0 && b[i]==0);
    for(unsigned i=0;i<514;++i) NEED(state.out[i]==0x5b);
    for(unsigned i=514;i<1026;++i) NEED(state.out[i]==0);
    if(packed_run) {
        NEED(init_calls==calls+1 && init_index==0);
        NEED(source_cursor==(t.seed+1)*1472 && mask_epoch==calls/32+1);
    }
    unsigned sat=control>>2;
    uint8_t wanted[514]; memset(wanted,0x5b,sizeof wanted);
    for(unsigned i=0;i<512;++i)
        if(i>=start && i<vl && original_selected(t.mode,i))
            wanted[i+1]=original_value(op,a[i],b[i],control,&sat);
    if(packed_run && mutation==0) {
        for(unsigned i=0;i<514;++i) { NEED(packed_gold_byte(calls,i)==wanted[i]); ++gold_bytes; }
        NEED(packed_gold_sat(calls)==sat); ++gold_sat;
    }
    /* The model result comes only from original C, never from packed_gold*. */
    memcpy(out,wanted+1,512);
    uint32_t vs=0;
    if(mutation>=1 && mutation<=3 && calls==(mutation==1 ? 0:mutation==2 ? 5376:10751)) {
        out[mutation==1 ? 0:mutation==2 ? 255:511]^=1; ++injected;
    } else if(mutation==4 && calls==0) { out[-1]^=1; ++injected;
    } else if(mutation==5 && calls==0) { out[512]^=1; ++injected;
    } else if(mutation==6 && calls==0) { vs=UINT32_C(0x80000000); ++injected;
    } else if(mutation==7 && calls==768) {
        NEED(t.seed==0 && op==0 && vl==512 && t.mode==0 && start==1 && wanted[9]==0);
        sat^=2; ++injected;
    } else if(mutation==8 && calls>=768 && calls<775) {
        NEED(t.seed==0 && op==0 && vl==512 && t.mode==0 && start==1 && wanted[9]==0);
        vs=1; out[0]^=1; out[511]^=1; sat^=2;
        out[-1]^=1; out[512]^=1; ++injected;
    }
    ++calls;
    return ((uint64_t)sat<<32)|vs;
}
#define OP(N) unsigned long op_##N(const uint8_t *a,const uint8_t *b,uint8_t *o,unsigned long v,unsigned long c,const uint8_t *m,unsigned long s,unsigned long rm) { return helper(N,a,b,o,v,c,m,s,rm); }
OP(0) OP(1) OP(2) OP(3)

static unsigned occurrences(const char *s,const char *needle) {
    unsigned n=0; while((s=strstr(s,needle))) { ++n; s+=strlen(needle); } return n;
}
static void dump(const char *dir,const char *name,const char *s) {
    char path[4096]; NEED(snprintf(path,sizeof path,"%s/%s",dir,name)>0);
    FILE *f=fopen(path,"wx"); NEED(f!=NULL);
    NEED(fwrite(s,1,strlen(s),f)==strlen(s)); NEED(fclose(f)==0);
}
static void footprint(void) {
    size_t page=(size_t)sysconf(_SC_PAGESIZE);
    uint8_t *p=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    NEED(p!=MAP_FAILED && mprotect(p+page,page,PROT_NONE)==0);
    probe=p+page-514; probe_init=probe_reads=0;
    packed_probe_init(probe); NEED(probe_init==65);
    NEED(packed_probe_check(0,probe)==0 && probe_reads==65);
    probe[0]^=1; probe[513]^=1;
    NEED(packed_probe_check(0,probe)==1 && probe_reads==130);
    probe=NULL; NEED(munmap(p,page*2)==0);
}
int main(int argc,char **argv) {
    NEED(argc==4); mutation=(unsigned)strtoul(argv[1],0,0);
    lifecycle_mutation=(unsigned)strtoul(argv[2],0,0);
    NEED(mutation<=8 && lifecycle_mutation<=4);
    original_evidence();
    uint64_t expected_errors=mutation==8 ? 35:mutation ? 1:0;
    unsigned results[2];
    for(packed_run=0;packed_run<2;++packed_run) {
        calls=injected=0; source_cursor=mask_epoch=mask_clear=mask_selected=0;
        init_index=init_calls=read_index=read_calls=0; total_selected=0;
        if(packed_run) { packed_reset(); state=packed_state(); }
        else { original_reset(); state=original_state(); }
        results[packed_run]=packed_run ? packed_main():original_main();
        state=packed_run ? packed_state():original_state();
        NEED(calls==10752 && state.checks==10752 && state.elements==5505024);
        NEED(state.errors==expected_errors && results[packed_run]==(expected_errors ? 1:0));
        NEED(injected==(mutation==8 ? 7:mutation ? 1:0));
        NEED(occurrences(uart[packed_run],"RVV_TRIAL ")==28);
        NEED(occurrences(uart[packed_run],"RVV_MATRIX_FAIL op=")==(expected_errors<20 ? expected_errors:20));
        if(packed_run) {
            NEED(source_cursor==4416 && mask_epoch==336 && mask_clear==0 && mask_selected==0);
            NEED(total_selected==70644 && init_calls==10752 && read_calls==10752);
            NEED(init_index==0 && read_index==0);
        }
    }
    NEED(uart_size[0]==uart_size[1] && !memcmp(uart[0],uart[1],uart_size[0]));
    dump(argv[3],"original.uart",uart[0]); dump(argv[3],"packed.uart",uart[1]);
    if(mutation==0) { NEED(gold_bytes==5526528 && gold_sat==10752); footprint(); }
    printf("HOST_ACCEPT full10752 mutation=%u errors=%llu diagnostics=%u original_C_gold_bytes=%llu sat=%llu sourceSB=4416 maskepochs=336 maskSB=70644 init=698880 reads=698880\n",
        mutation,(unsigned long long)expected_errors,occurrences(uart[0],"RVV_MATRIX_FAIL op="),
        (unsigned long long)gold_bytes,(unsigned long long)gold_sat);
    return 0;
}
