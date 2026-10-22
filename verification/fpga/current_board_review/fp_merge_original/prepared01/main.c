extern int fp_merge_prefix195_main(void);
extern void replay_text(const char*);
int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}if(fp_merge_prefix195_main()){replay_text("BOARD_CASE_FAIL fp_merge_prefix195\n");return 1;}replay_text("BOARD_CASE_PASS fp_merge_prefix195\nBOARD_REPLAY_PASS\n");return 0;}
