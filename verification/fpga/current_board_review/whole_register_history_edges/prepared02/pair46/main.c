extern int whole_original_main(void);
extern void replay_text(const char*);
int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}if(whole_original_main()){replay_text("BOARD_CASE_FAIL\n");return 1;}replay_text("BOARD_CASE_PASS whole_edge46\nBOARD_REPLAY_PASS\n");return 0;}
