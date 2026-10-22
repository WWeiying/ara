extern void replay_text(const char*);
extern int unboxed_unmasked_alias_v16_e32_m1_t0_ctx1_main(void);
int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){return 90;}
replay_text("BOARD_CASE_BEGIN unboxed_unmasked_alias_v16_e32_m1_t0_ctx1\n");
if(unboxed_unmasked_alias_v16_e32_m1_t0_ctx1_main()){return 1;}
replay_text("BOARD_REPLAY_PASS\n");return 0;}
