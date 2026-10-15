extern void replay_text(const char*);
extern int restart_unmasked_e16m2_prefix130_main(void);
int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}
if(restart_unmasked_e16m2_prefix130_main()){replay_text("BOARD_CASE_FAIL restart_unmasked_e16m2_prefix130\n");return 1;}replay_text("BOARD_CASE_PASS restart_unmasked_e16m2_prefix130\nBOARD_REPLAY_PASS\n");return 0;}
