#include <limits.h>
#include <sys/resource.h>
int main(int argc,char **argv) {
    (void)argv;
    struct rlimit limit={0,0};
    if(setrlimit(RLIMIT_CORE,&limit)) return 91;
    volatile int maximum=INT_MAX;
    return maximum+argc;
}
