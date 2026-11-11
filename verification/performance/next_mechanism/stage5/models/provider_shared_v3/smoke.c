#define _GNU_SOURCE
#include "entry.h"
#include "execution_contract.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

struct sample { uintptr_t before[3],after[3],result,restored[3]; };
_Static_assert(sizeof(struct sample)==80,"assembly layout");
extern int stage5_provider_setup_v2(void);
extern void provider_measure_call(void (*)(void),void *,uintptr_t,uintptr_t,uintptr_t,uintptr_t,struct sample *);
static const akv_resident_platform_provider_v1 *provider;
static unsigned failures,calls;

static uintptr_t measure(const char *name,void (*fn)(void),uintptr_t arg,
                         uintptr_t start,uintptr_t vc,uintptr_t fc,int expected) {
    struct sample s;
    asm volatile("csrwi vstart,0;csrwi vcsr,3;csrwi fcsr,8" ::: "memory");
    provider_measure_call(fn,provider->context,arg,start,vc,fc,&s);
    int ok=s.before[0]==start && s.before[1]==vc && s.before[2]==fc &&
           s.after[0]==start && s.after[1]==vc && s.after[2]==fc &&
           s.restored[0]==0 && s.restored[1]==3 && s.restored[2]==8;
    if(expected==1) ok=ok && s.result>0;
    if(expected==0) ok=ok && s.result==0;
    if(expected==-1) ok=ok && (intptr_t)s.result==-1;
    ++calls;if(!ok)++failures;
    printf("PROVIDER_CALL name=%s result=%ld before0=%lu before1=%lu before2=%lu after0=%lu after1=%lu after2=%lu restored0=%lu restored1=%lu restored2=%lu ok=%d\n",
        name,(long)s.result,s.before[0],s.before[1],s.before[2],s.after[0],s.after[1],s.after[2],
        s.restored[0],s.restored[1],s.restored[2],ok);
    return s.result;
}

static void maps(const char *stage) {
    printf("PROVIDER_MAPS_BEGIN stage=%s\n",stage);
    FILE *f=fopen("/proc/self/maps","r");char line[1024];
    if(!f){++failures;perror("maps");}
    else {while(fgets(line,sizeof(line),f))fputs(line,stdout);if(ferror(f))++failures;fclose(f);}
    printf("PROVIDER_MAPS_END stage=%s\n",stage);
}

static uintptr_t acquire(const char *name,akv_platform_span_v1 *spans,size_t count,int expected) {
    akv_platform_request_v1 request={.abi_version=1,.struct_bytes=sizeof(request),.requested=1,
        .workers=1,.decode_head_rows=1,.query_tokens=1,.groups=1,.refill_overlap=0,.spans=spans,.span_count=count};
    for(size_t i=0;i<count;++i)printf("PROVIDER_SPAN name=%s index=%zu base=0x%lx bytes=%zu writable=%u\n",
        name,i,(unsigned long)spans[i].base,spans[i].bytes,spans[i].writable);
    return measure(name,(void (*)(void))provider->acquire,(uintptr_t)&request,0,5,9,expected);
}

static void release(const char *name,uintptr_t cookie,uintptr_t start) {
    if(!cookie){printf("PROVIDER_SKIPPED name=%s missing_lease=1\n",name);++failures;return;}
    measure(name,(void (*)(void))provider->release,cookie,start,start?7:5,start?65:9,2);
}

static int test(void) {
    const int setup=stage5_provider_setup_v2();printf("PROVIDER_SETUP result=%d\n",setup);
    provider=akv_resident_platform_current_v1();
    if(setup!=1 || !provider)return 2;
    akv_platform_thread_state_v1 state={0};
    measure("state_ready",(void (*)(void))provider->read_state,(uintptr_t)&state,0,5,9,1);
    if(state.vstart || state.vlenb!=128 || state.vcsr!=5 || state.fcsr!=9)++failures;
    printf("PROVIDER_STATE vlenb=%lu vstart=%lu vcsr=%lu fcsr=%lu\n",state.vlenb,state.vstart,state.vcsr,state.fcsr);

    void *small=malloc(4096);if(!small)return 3;
    ((volatile unsigned char *)small)[0]=1;((volatile unsigned char *)small)[4095]=2;
    akv_platform_span_v1 spans[2]={{small,4096,1},{0,0,0}};
    maps("small");release("small_release",acquire("small_acquire",spans,1,1),0);
    void *large=malloc(8*1024*1024);if(!large)return 4;
    ((volatile unsigned char *)large)[0]=3;((volatile unsigned char *)large)[8*1024*1024-1]=4;
    spans[1]=(akv_platform_span_v1){large,8*1024*1024,1};
    maps("large");release("large_release",acquire("large_acquire",spans,2,1),0);
    free(large);

    int fd=open(STAGE5_MODEL_PATH,O_RDONLY);if(fd<0)return 5;
    void *ro=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0);close(fd);if(ro==MAP_FAILED)return 6;
    spans[1]=(akv_platform_span_v1){ro,4096,0};
    maps("readonly");release("readonly_release",acquire("readonly_acquire",spans,2,1),0);
    spans[1].writable=1;acquire("readonly_write_denied",spans,2,0);munmap(ro,4096);
    fd=open("/unapproved.bin",O_RDONLY);if(fd<0)return 7;
    ro=mmap(NULL,4096,PROT_READ,MAP_PRIVATE,fd,0);close(fd);if(ro==MAP_FAILED)return 8;
    spans[1]=(akv_platform_span_v1){ro,4096,0};maps("unapproved");
    acquire("unknown_file_denied",spans,2,0);munmap(ro,4096);

    void *hole=mmap(NULL,12288,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(hole==MAP_FAILED || munmap((char*)hole+4096,4096))return 9;
    spans[1]=(akv_platform_span_v1){hole,12288,1};maps("hole");
    acquire("hole_denied",spans,2,0);munmap(hole,4096);munmap((char*)hole+8192,4096);
    measure("state_bad_vstart",(void (*)(void))provider->read_state,1,1,6,104,-1);
    measure("acquire_bad_vstart",(void (*)(void))provider->acquire,1,7,7,65,0);
    maps("cleanup");release("release_bad_vstart",acquire("cleanup_acquire",spans,1,1),7);
    release("final_release",acquire("final_acquire",spans,1,1),0);
    free(small);
    printf("PROVIDER_COMPLETE failures=%u calls=%u native_akv=0 model=0\n",failures,calls);
    return failures?1:0;
}

int main(void) {
    setvbuf(stdout,NULL,_IONBF,0);setvbuf(stderr,NULL,_IONBF,0);
    if(getpid()!=1)return test();
    int result=127;
    if(mount("proc","/proc","proc",MS_NOSUID|MS_NOEXEC|MS_NODEV,NULL))perror("mount proc");
    else {
        pid_t child=fork();
        if(!child){char *const argv[]={"/test",NULL},*const env[]={"PATH=/bin:/usr/bin","LC_ALL=C",NULL};
            execve("/test",argv,env);_exit(127);}
        int status;pid_t waited;
        do{waited=waitpid(child,&status,0);}while(waited<0 && errno==EINTR);
        if(child>0 && waited==child)result=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
    }
    printf("PROVIDER_CHILD_EXIT=%d\n",result);sync();reboot(RB_POWER_OFF);for(;;)pause();
}
