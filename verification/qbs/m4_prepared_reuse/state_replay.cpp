#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>

extern "C" bool m4_produce(const float *,void *,int64_t);
extern "C" const float real_input[];
extern "C" const unsigned char golden_packed[];
static constexpr size_t Bytes=7008;
alignas(64) static unsigned char cached[Bytes],baseline[Bytes+128],replayed[Bytes+128];
alignas(64) static unsigned char saved_input[4*1536*4];
static unsigned raised_flags;

static void need(bool ok,const char *why) {
    if(!ok) {std::printf("M4_STATE_REPLAY_FAIL reason=%s\n",why);std::exit(1);}
}
static unsigned read_fc() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned read_vc() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static void state(unsigned fc,unsigned vc) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0"::"r"(fc),"r"(vc):"memory");
}
// This proves only byte/exception replay, not graph identity or cache admission.
__attribute__((noinline)) static bool replay(void *destination) {
    unsigned fc=read_fc(),vs;
    asm volatile("csrr %0,vstart":"=r"(vs)::"memory");
    if((fc>>5)!=0 || vs!=0) return false;
    std::memcpy(destination,cached,Bytes);
    unsigned now;
    asm volatile("frflags %0":"=r"(now)::"memory");
    now|=raised_flags;
    asm volatile("fsflags %0"::"r"(now):"memory");
    return true;
}
int main() {
    unsigned checks=0;
    std::memcpy(saved_input,real_input,sizeof(saved_input));
    state(17,5);
    unsigned before=read_fc(),vc=read_vc();
    // Capture generated exceptions independently of incoming sticky flags.
    asm volatile("fsflags zero":::"memory");
    need(m4_produce(real_input,cached,1536),"real_input_not_vector_eligible");
    asm volatile("frflags %0":"=r"(raised_flags)::"memory");
    unsigned restored=(before&31)|raised_flags;
    asm volatile("fsflags %0"::"r"(restored):"memory");
    need(read_fc()==restored && read_vc()==vc,"capture_state");
    need(std::memcmp(cached,golden_packed,Bytes)==0,"capture_bytes");++checks;
    for(unsigned flags=0;flags<32;++flags) {
        for(unsigned vector_state=0;vector_state<8;++vector_state) {
            std::memset(baseline,0xa5,sizeof(baseline));
            std::memset(replayed,0xa5,sizeof(replayed));
            state(flags,vector_state);
            need(m4_produce(real_input,baseline+64,1536),"baseline_domain");
            unsigned ef=read_fc(),ev=read_vc();
            state(flags,vector_state);
            need(replay(replayed+64),"eligible_replay_rejected");
            unsigned af=read_fc(),av=read_vc();
            need(ef==af && ev==av,"sticky_or_vector_state");
            need(std::memcmp(baseline,replayed,sizeof(baseline))==0,"bytes_or_canary");
            ++checks;
        }
    }
    for(unsigned frm=1;frm<=4;++frm) {
        std::memset(replayed,0xa5,sizeof(replayed));
        state((frm<<5)|8,3);
        need(!replay(replayed+64),"non_rne_admitted");
        need(read_fc()==((frm<<5)|8) && read_vc()==3,"rejected_rounding_state_changed");
        for(auto x:replayed) {need(x==0xa5,"rejected_replay_wrote_output");}
        ++checks;
    }
    state(8,3);asm volatile("csrwi vstart,1":::"memory");
    bool admitted=replay(replayed+64);unsigned vs;
    asm volatile("csrr %0,vstart;csrwi vstart,0":"=r"(vs)::"memory");
    need(!admitted && vs==1 && read_fc()==8 && read_vc()==3,"restart_state");++checks;
    need(std::memcmp(saved_input,real_input,sizeof(saved_input))==0,"input_modified");
    std::printf("M4_STATE_REPLAY_PASS checks=%u bytes=7008 raised_flags=%u\n",checks,raised_flags);
    return checks==262 ? 0:2;
}
