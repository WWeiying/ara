#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

static void need(bool ok,const char *why) {
    if (!ok) {std::fprintf(stderr,"TRACE_CONTEXT_MODEL_FAIL reason=%s\n",why);std::exit(1);}
}
static void read(FILE *f,void *data,size_t size) {need(std::fread(data,1,size,f)==size,"record_read");}
static void compare(const char *baseline,const char *candidate) {
    static_assert(sizeof(uintptr_t)==8,"The model records use RV64 uintptr_t");
    FILE *a=std::fopen(baseline,"rb"),*b=std::fopen(candidate,"rb");need(a && b,"paired_files");
    uint32_t na,nb;read(a,&na,4);read(b,&nb,4);need(na==151936 && nb==na,"vocabulary");
    std::vector<float> va(na),vb(nb);
    for (unsigned record=0;record<4;++record) {
        int32_t ta,tb;uint64_t fa,fb,ca,cb;
        read(a,&ta,4);read(b,&tb,4);read(a,&fa,8);read(b,&fb,8);read(a,&ca,8);read(b,&cb,8);
        read(a,va.data(),na*4);read(b,vb.data(),nb*4);
        need(ta>=0 && uint32_t(ta)<na && ta==tb && fa==fb && ca==cb,"token_csr_equal");
        need(fa<=31 && (fa&8) && ca<=7,"csr_range");
        for (unsigned i=0;i<na;++i) need(std::isfinite(va[i]) && std::isfinite(vb[i]),"finite_logits");
        need(!std::memcmp(va.data(),vb.data(),na*4),"paired_logits");
        std::printf("TRACE_CONTEXT_COMPARE kind=%u step=%u outputs=151936 bitwise=1 csr_equal=1 token_equal=1\n",
            record/2,record%2);
    }
    need(std::fgetc(a)==EOF && std::fgetc(b)==EOF && !std::ferror(a) && !std::ferror(b),"extra_records");
    need(!std::fclose(a) && !std::fclose(b),"close");
    std::puts("TRACE_CONTEXT_SUITE_PASS variants=2 comparisons=4 logits=607744 bytes_per_variant=2431060 performance=not_measured");
}
int main(int argc,char **argv) {
    std::setvbuf(stdout,nullptr,_IONBF,0);std::setvbuf(stderr,nullptr,_IONBF,0);
    if (argc==4 && !std::strcmp(argv[1],"--compare-only")) {compare(argv[2],argv[3]);return 0;}
    need(argc==1,"arguments");
    const char *programs[]={"/base","/candidate"};
    const char *outputs[]={"/tmp/trace-base.bin","/tmp/trace-candidate.bin"};
    // Separate execs prevent cached environment/backend state crossing library variants.
    for (unsigned variant=0;variant<2;++variant) {
        std::printf("TRACE_CONTEXT_VARIANT_BEGIN variant=%u\n",variant);
        const pid_t child=fork();need(child>=0,"fork");
        if (!child) {execl(programs[variant],programs[variant],outputs[variant],static_cast<char *>(nullptr));_exit(127);}
        int status=0;need(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0,"variant_exit");
        std::printf("TRACE_CONTEXT_VARIANT_END variant=%u\n",variant);
    }
    compare(outputs[0],outputs[1]);return 0;
}
