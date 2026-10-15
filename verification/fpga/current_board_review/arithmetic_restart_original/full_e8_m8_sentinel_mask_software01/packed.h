/* Sole delta: fixed straight-line scalar initialization and comparison. */
static uint64_t raw_word(const uint8_t *p) {
    uint64_t value;
    __builtin_memcpy(&value,p,8);
    return value;
}
static void initialize_output(uint8_t *p) {
    const uint64_t value=UINT64_C(0x5b5b5b5b5b5b5b5b);
    __builtin_memcpy(p+0,&value,8);
    __builtin_memcpy(p+8,&value,8);
    __builtin_memcpy(p+16,&value,8);
    __builtin_memcpy(p+24,&value,8);
    __builtin_memcpy(p+32,&value,8);
    __builtin_memcpy(p+40,&value,8);
    __builtin_memcpy(p+48,&value,8);
    __builtin_memcpy(p+56,&value,8);
    __builtin_memcpy(p+64,&value,8);
    __builtin_memcpy(p+72,&value,8);
    __builtin_memcpy(p+80,&value,8);
    __builtin_memcpy(p+88,&value,8);
    __builtin_memcpy(p+96,&value,8);
    __builtin_memcpy(p+104,&value,8);
    __builtin_memcpy(p+112,&value,8);
    __builtin_memcpy(p+120,&value,8);
    __builtin_memcpy(p+128,&value,8);
    __builtin_memcpy(p+136,&value,8);
    __builtin_memcpy(p+144,&value,8);
    __builtin_memcpy(p+152,&value,8);
    __builtin_memcpy(p+160,&value,8);
    __builtin_memcpy(p+168,&value,8);
    __builtin_memcpy(p+176,&value,8);
    __builtin_memcpy(p+184,&value,8);
    __builtin_memcpy(p+192,&value,8);
    __builtin_memcpy(p+200,&value,8);
    __builtin_memcpy(p+208,&value,8);
    __builtin_memcpy(p+216,&value,8);
    __builtin_memcpy(p+224,&value,8);
    __builtin_memcpy(p+232,&value,8);
    __builtin_memcpy(p+240,&value,8);
    __builtin_memcpy(p+248,&value,8);
    __builtin_memcpy(p+256,&value,8);
    __builtin_memcpy(p+264,&value,8);
    __builtin_memcpy(p+272,&value,8);
    __builtin_memcpy(p+280,&value,8);
    __builtin_memcpy(p+288,&value,8);
    __builtin_memcpy(p+296,&value,8);
    __builtin_memcpy(p+304,&value,8);
    __builtin_memcpy(p+312,&value,8);
    __builtin_memcpy(p+320,&value,8);
    __builtin_memcpy(p+328,&value,8);
    __builtin_memcpy(p+336,&value,8);
    __builtin_memcpy(p+344,&value,8);
    __builtin_memcpy(p+352,&value,8);
    __builtin_memcpy(p+360,&value,8);
    __builtin_memcpy(p+368,&value,8);
    __builtin_memcpy(p+376,&value,8);
    __builtin_memcpy(p+384,&value,8);
    __builtin_memcpy(p+392,&value,8);
    __builtin_memcpy(p+400,&value,8);
    __builtin_memcpy(p+408,&value,8);
    __builtin_memcpy(p+416,&value,8);
    __builtin_memcpy(p+424,&value,8);
    __builtin_memcpy(p+432,&value,8);
    __builtin_memcpy(p+440,&value,8);
    __builtin_memcpy(p+448,&value,8);
    __builtin_memcpy(p+456,&value,8);
    __builtin_memcpy(p+464,&value,8);
    __builtin_memcpy(p+472,&value,8);
    __builtin_memcpy(p+480,&value,8);
    __builtin_memcpy(p+488,&value,8);
    __builtin_memcpy(p+496,&value,8);
    __builtin_memcpy(p+504,&value,8);
    __builtin_memcpy(p+512,&value,8);
    __builtin_memcpy(p+520,&value,8);
    __builtin_memcpy(p+528,&value,8);
    __builtin_memcpy(p+536,&value,8);
    __builtin_memcpy(p+544,&value,8);
    __builtin_memcpy(p+552,&value,8);
    __builtin_memcpy(p+560,&value,8);
    __builtin_memcpy(p+568,&value,8);
    __builtin_memcpy(p+576,&value,8);
    __builtin_memcpy(p+584,&value,8);
    __builtin_memcpy(p+592,&value,8);
    __builtin_memcpy(p+600,&value,8);
    __builtin_memcpy(p+608,&value,8);
    __builtin_memcpy(p+616,&value,8);
    __builtin_memcpy(p+624,&value,8);
    __builtin_memcpy(p+632,&value,8);
    __builtin_memcpy(p+640,&value,8);
    __builtin_memcpy(p+648,&value,8);
    __builtin_memcpy(p+656,&value,8);
    __builtin_memcpy(p+664,&value,8);
    __builtin_memcpy(p+672,&value,8);
    __builtin_memcpy(p+680,&value,8);
    __builtin_memcpy(p+688,&value,8);
    __builtin_memcpy(p+696,&value,8);
    __builtin_memcpy(p+704,&value,8);
    __builtin_memcpy(p+712,&value,8);
    __builtin_memcpy(p+720,&value,8);
    __builtin_memcpy(p+728,&value,8);
    __builtin_memcpy(p+736,&value,8);
    __builtin_memcpy(p+744,&value,8);
    __builtin_memcpy(p+752,&value,8);
    __builtin_memcpy(p+760,&value,8);
    __builtin_memcpy(p+768,&value,8);
    __builtin_memcpy(p+776,&value,8);
    __builtin_memcpy(p+784,&value,8);
    __builtin_memcpy(p+792,&value,8);
    __builtin_memcpy(p+800,&value,8);
    __builtin_memcpy(p+808,&value,8);
    __builtin_memcpy(p+816,&value,8);
    __builtin_memcpy(p+824,&value,8);
    __builtin_memcpy(p+832,&value,8);
    __builtin_memcpy(p+840,&value,8);
    __builtin_memcpy(p+848,&value,8);
    __builtin_memcpy(p+856,&value,8);
    __builtin_memcpy(p+864,&value,8);
    __builtin_memcpy(p+872,&value,8);
    __builtin_memcpy(p+880,&value,8);
    __builtin_memcpy(p+888,&value,8);
    __builtin_memcpy(p+896,&value,8);
    __builtin_memcpy(p+904,&value,8);
    __builtin_memcpy(p+912,&value,8);
    __builtin_memcpy(p+920,&value,8);
    __builtin_memcpy(p+928,&value,8);
    __builtin_memcpy(p+936,&value,8);
    __builtin_memcpy(p+944,&value,8);
    __builtin_memcpy(p+952,&value,8);
    __builtin_memcpy(p+960,&value,8);
    __builtin_memcpy(p+968,&value,8);
    __builtin_memcpy(p+976,&value,8);
    __builtin_memcpy(p+984,&value,8);
    __builtin_memcpy(p+992,&value,8);
    __builtin_memcpy(p+1000,&value,8);
    __builtin_memcpy(p+1008,&value,8);
    __builtin_memcpy(p+1016,&value,8);
    const uint16_t tail=0x5b5b;
    __builtin_memcpy(p+1024,&tail,2);
}
static void initialize_mask(uint8_t *p,unsigned mode) {
    __builtin_memcpy(p+0,physical_masks[mode]+0,8);
    __builtin_memcpy(p+8,physical_masks[mode]+8,8);
    __builtin_memcpy(p+16,physical_masks[mode]+16,8);
    __builtin_memcpy(p+24,physical_masks[mode]+24,8);
    __builtin_memcpy(p+32,physical_masks[mode]+32,8);
    __builtin_memcpy(p+40,physical_masks[mode]+40,8);
    __builtin_memcpy(p+48,physical_masks[mode]+48,8);
    __builtin_memcpy(p+56,physical_masks[mode]+56,8);
    __builtin_memcpy(p+64,physical_masks[mode]+64,8);
    __builtin_memcpy(p+72,physical_masks[mode]+72,8);
    __builtin_memcpy(p+80,physical_masks[mode]+80,8);
    __builtin_memcpy(p+88,physical_masks[mode]+88,8);
    __builtin_memcpy(p+96,physical_masks[mode]+96,8);
    __builtin_memcpy(p+104,physical_masks[mode]+104,8);
    __builtin_memcpy(p+112,physical_masks[mode]+112,8);
    __builtin_memcpy(p+120,physical_masks[mode]+120,8);
}
static unsigned packed_mismatch(const uint8_t *p,uint64_t ordinal) {
    const uint16_t *indices=expected_indices[ordinal];
    const uint64_t sentinel=UINT64_C(0x5b5b5b5b5b5b5b5b);
    if(indices[0]==0) {
        if(raw_word(p+0)!=sentinel)return 1;
        if(raw_word(p+8)!=sentinel)return 1;
        if(raw_word(p+16)!=sentinel)return 1;
        if(raw_word(p+24)!=sentinel)return 1;
        if(raw_word(p+32)!=sentinel)return 1;
        if(raw_word(p+40)!=sentinel)return 1;
        if(raw_word(p+48)!=sentinel)return 1;
        if(raw_word(p+56)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[0];
        if(raw_word(p+0)!=expected[0])return 1;
        if(raw_word(p+8)!=expected[1])return 1;
        if(raw_word(p+16)!=expected[2])return 1;
        if(raw_word(p+24)!=expected[3])return 1;
        if(raw_word(p+32)!=expected[4])return 1;
        if(raw_word(p+40)!=expected[5])return 1;
        if(raw_word(p+48)!=expected[6])return 1;
        if(raw_word(p+56)!=expected[7])return 1;
    }
    if(indices[1]==0) {
        if(raw_word(p+64)!=sentinel)return 1;
        if(raw_word(p+72)!=sentinel)return 1;
        if(raw_word(p+80)!=sentinel)return 1;
        if(raw_word(p+88)!=sentinel)return 1;
        if(raw_word(p+96)!=sentinel)return 1;
        if(raw_word(p+104)!=sentinel)return 1;
        if(raw_word(p+112)!=sentinel)return 1;
        if(raw_word(p+120)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[1];
        if(raw_word(p+64)!=expected[0])return 1;
        if(raw_word(p+72)!=expected[1])return 1;
        if(raw_word(p+80)!=expected[2])return 1;
        if(raw_word(p+88)!=expected[3])return 1;
        if(raw_word(p+96)!=expected[4])return 1;
        if(raw_word(p+104)!=expected[5])return 1;
        if(raw_word(p+112)!=expected[6])return 1;
        if(raw_word(p+120)!=expected[7])return 1;
    }
    if(indices[2]==0) {
        if(raw_word(p+128)!=sentinel)return 1;
        if(raw_word(p+136)!=sentinel)return 1;
        if(raw_word(p+144)!=sentinel)return 1;
        if(raw_word(p+152)!=sentinel)return 1;
        if(raw_word(p+160)!=sentinel)return 1;
        if(raw_word(p+168)!=sentinel)return 1;
        if(raw_word(p+176)!=sentinel)return 1;
        if(raw_word(p+184)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[2];
        if(raw_word(p+128)!=expected[0])return 1;
        if(raw_word(p+136)!=expected[1])return 1;
        if(raw_word(p+144)!=expected[2])return 1;
        if(raw_word(p+152)!=expected[3])return 1;
        if(raw_word(p+160)!=expected[4])return 1;
        if(raw_word(p+168)!=expected[5])return 1;
        if(raw_word(p+176)!=expected[6])return 1;
        if(raw_word(p+184)!=expected[7])return 1;
    }
    if(indices[3]==0) {
        if(raw_word(p+192)!=sentinel)return 1;
        if(raw_word(p+200)!=sentinel)return 1;
        if(raw_word(p+208)!=sentinel)return 1;
        if(raw_word(p+216)!=sentinel)return 1;
        if(raw_word(p+224)!=sentinel)return 1;
        if(raw_word(p+232)!=sentinel)return 1;
        if(raw_word(p+240)!=sentinel)return 1;
        if(raw_word(p+248)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[3];
        if(raw_word(p+192)!=expected[0])return 1;
        if(raw_word(p+200)!=expected[1])return 1;
        if(raw_word(p+208)!=expected[2])return 1;
        if(raw_word(p+216)!=expected[3])return 1;
        if(raw_word(p+224)!=expected[4])return 1;
        if(raw_word(p+232)!=expected[5])return 1;
        if(raw_word(p+240)!=expected[6])return 1;
        if(raw_word(p+248)!=expected[7])return 1;
    }
    if(indices[4]==0) {
        if(raw_word(p+256)!=sentinel)return 1;
        if(raw_word(p+264)!=sentinel)return 1;
        if(raw_word(p+272)!=sentinel)return 1;
        if(raw_word(p+280)!=sentinel)return 1;
        if(raw_word(p+288)!=sentinel)return 1;
        if(raw_word(p+296)!=sentinel)return 1;
        if(raw_word(p+304)!=sentinel)return 1;
        if(raw_word(p+312)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[4];
        if(raw_word(p+256)!=expected[0])return 1;
        if(raw_word(p+264)!=expected[1])return 1;
        if(raw_word(p+272)!=expected[2])return 1;
        if(raw_word(p+280)!=expected[3])return 1;
        if(raw_word(p+288)!=expected[4])return 1;
        if(raw_word(p+296)!=expected[5])return 1;
        if(raw_word(p+304)!=expected[6])return 1;
        if(raw_word(p+312)!=expected[7])return 1;
    }
    if(indices[5]==0) {
        if(raw_word(p+320)!=sentinel)return 1;
        if(raw_word(p+328)!=sentinel)return 1;
        if(raw_word(p+336)!=sentinel)return 1;
        if(raw_word(p+344)!=sentinel)return 1;
        if(raw_word(p+352)!=sentinel)return 1;
        if(raw_word(p+360)!=sentinel)return 1;
        if(raw_word(p+368)!=sentinel)return 1;
        if(raw_word(p+376)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[5];
        if(raw_word(p+320)!=expected[0])return 1;
        if(raw_word(p+328)!=expected[1])return 1;
        if(raw_word(p+336)!=expected[2])return 1;
        if(raw_word(p+344)!=expected[3])return 1;
        if(raw_word(p+352)!=expected[4])return 1;
        if(raw_word(p+360)!=expected[5])return 1;
        if(raw_word(p+368)!=expected[6])return 1;
        if(raw_word(p+376)!=expected[7])return 1;
    }
    if(indices[6]==0) {
        if(raw_word(p+384)!=sentinel)return 1;
        if(raw_word(p+392)!=sentinel)return 1;
        if(raw_word(p+400)!=sentinel)return 1;
        if(raw_word(p+408)!=sentinel)return 1;
        if(raw_word(p+416)!=sentinel)return 1;
        if(raw_word(p+424)!=sentinel)return 1;
        if(raw_word(p+432)!=sentinel)return 1;
        if(raw_word(p+440)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[6];
        if(raw_word(p+384)!=expected[0])return 1;
        if(raw_word(p+392)!=expected[1])return 1;
        if(raw_word(p+400)!=expected[2])return 1;
        if(raw_word(p+408)!=expected[3])return 1;
        if(raw_word(p+416)!=expected[4])return 1;
        if(raw_word(p+424)!=expected[5])return 1;
        if(raw_word(p+432)!=expected[6])return 1;
        if(raw_word(p+440)!=expected[7])return 1;
    }
    if(indices[7]==0) {
        if(raw_word(p+448)!=sentinel)return 1;
        if(raw_word(p+456)!=sentinel)return 1;
        if(raw_word(p+464)!=sentinel)return 1;
        if(raw_word(p+472)!=sentinel)return 1;
        if(raw_word(p+480)!=sentinel)return 1;
        if(raw_word(p+488)!=sentinel)return 1;
        if(raw_word(p+496)!=sentinel)return 1;
        if(raw_word(p+504)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[7];
        if(raw_word(p+448)!=expected[0])return 1;
        if(raw_word(p+456)!=expected[1])return 1;
        if(raw_word(p+464)!=expected[2])return 1;
        if(raw_word(p+472)!=expected[3])return 1;
        if(raw_word(p+480)!=expected[4])return 1;
        if(raw_word(p+488)!=expected[5])return 1;
        if(raw_word(p+496)!=expected[6])return 1;
        if(raw_word(p+504)!=expected[7])return 1;
    }
    if(indices[8]==0) {
        if(raw_word(p+512)!=sentinel)return 1;
        if(raw_word(p+520)!=sentinel)return 1;
        if(raw_word(p+528)!=sentinel)return 1;
        if(raw_word(p+536)!=sentinel)return 1;
        if(raw_word(p+544)!=sentinel)return 1;
        if(raw_word(p+552)!=sentinel)return 1;
        if(raw_word(p+560)!=sentinel)return 1;
        if(raw_word(p+568)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[8];
        if(raw_word(p+512)!=expected[0])return 1;
        if(raw_word(p+520)!=expected[1])return 1;
        if(raw_word(p+528)!=expected[2])return 1;
        if(raw_word(p+536)!=expected[3])return 1;
        if(raw_word(p+544)!=expected[4])return 1;
        if(raw_word(p+552)!=expected[5])return 1;
        if(raw_word(p+560)!=expected[6])return 1;
        if(raw_word(p+568)!=expected[7])return 1;
    }
    if(indices[9]==0) {
        if(raw_word(p+576)!=sentinel)return 1;
        if(raw_word(p+584)!=sentinel)return 1;
        if(raw_word(p+592)!=sentinel)return 1;
        if(raw_word(p+600)!=sentinel)return 1;
        if(raw_word(p+608)!=sentinel)return 1;
        if(raw_word(p+616)!=sentinel)return 1;
        if(raw_word(p+624)!=sentinel)return 1;
        if(raw_word(p+632)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[9];
        if(raw_word(p+576)!=expected[0])return 1;
        if(raw_word(p+584)!=expected[1])return 1;
        if(raw_word(p+592)!=expected[2])return 1;
        if(raw_word(p+600)!=expected[3])return 1;
        if(raw_word(p+608)!=expected[4])return 1;
        if(raw_word(p+616)!=expected[5])return 1;
        if(raw_word(p+624)!=expected[6])return 1;
        if(raw_word(p+632)!=expected[7])return 1;
    }
    if(indices[10]==0) {
        if(raw_word(p+640)!=sentinel)return 1;
        if(raw_word(p+648)!=sentinel)return 1;
        if(raw_word(p+656)!=sentinel)return 1;
        if(raw_word(p+664)!=sentinel)return 1;
        if(raw_word(p+672)!=sentinel)return 1;
        if(raw_word(p+680)!=sentinel)return 1;
        if(raw_word(p+688)!=sentinel)return 1;
        if(raw_word(p+696)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[10];
        if(raw_word(p+640)!=expected[0])return 1;
        if(raw_word(p+648)!=expected[1])return 1;
        if(raw_word(p+656)!=expected[2])return 1;
        if(raw_word(p+664)!=expected[3])return 1;
        if(raw_word(p+672)!=expected[4])return 1;
        if(raw_word(p+680)!=expected[5])return 1;
        if(raw_word(p+688)!=expected[6])return 1;
        if(raw_word(p+696)!=expected[7])return 1;
    }
    if(indices[11]==0) {
        if(raw_word(p+704)!=sentinel)return 1;
        if(raw_word(p+712)!=sentinel)return 1;
        if(raw_word(p+720)!=sentinel)return 1;
        if(raw_word(p+728)!=sentinel)return 1;
        if(raw_word(p+736)!=sentinel)return 1;
        if(raw_word(p+744)!=sentinel)return 1;
        if(raw_word(p+752)!=sentinel)return 1;
        if(raw_word(p+760)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[11];
        if(raw_word(p+704)!=expected[0])return 1;
        if(raw_word(p+712)!=expected[1])return 1;
        if(raw_word(p+720)!=expected[2])return 1;
        if(raw_word(p+728)!=expected[3])return 1;
        if(raw_word(p+736)!=expected[4])return 1;
        if(raw_word(p+744)!=expected[5])return 1;
        if(raw_word(p+752)!=expected[6])return 1;
        if(raw_word(p+760)!=expected[7])return 1;
    }
    if(indices[12]==0) {
        if(raw_word(p+768)!=sentinel)return 1;
        if(raw_word(p+776)!=sentinel)return 1;
        if(raw_word(p+784)!=sentinel)return 1;
        if(raw_word(p+792)!=sentinel)return 1;
        if(raw_word(p+800)!=sentinel)return 1;
        if(raw_word(p+808)!=sentinel)return 1;
        if(raw_word(p+816)!=sentinel)return 1;
        if(raw_word(p+824)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[12];
        if(raw_word(p+768)!=expected[0])return 1;
        if(raw_word(p+776)!=expected[1])return 1;
        if(raw_word(p+784)!=expected[2])return 1;
        if(raw_word(p+792)!=expected[3])return 1;
        if(raw_word(p+800)!=expected[4])return 1;
        if(raw_word(p+808)!=expected[5])return 1;
        if(raw_word(p+816)!=expected[6])return 1;
        if(raw_word(p+824)!=expected[7])return 1;
    }
    if(indices[13]==0) {
        if(raw_word(p+832)!=sentinel)return 1;
        if(raw_word(p+840)!=sentinel)return 1;
        if(raw_word(p+848)!=sentinel)return 1;
        if(raw_word(p+856)!=sentinel)return 1;
        if(raw_word(p+864)!=sentinel)return 1;
        if(raw_word(p+872)!=sentinel)return 1;
        if(raw_word(p+880)!=sentinel)return 1;
        if(raw_word(p+888)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[13];
        if(raw_word(p+832)!=expected[0])return 1;
        if(raw_word(p+840)!=expected[1])return 1;
        if(raw_word(p+848)!=expected[2])return 1;
        if(raw_word(p+856)!=expected[3])return 1;
        if(raw_word(p+864)!=expected[4])return 1;
        if(raw_word(p+872)!=expected[5])return 1;
        if(raw_word(p+880)!=expected[6])return 1;
        if(raw_word(p+888)!=expected[7])return 1;
    }
    if(indices[14]==0) {
        if(raw_word(p+896)!=sentinel)return 1;
        if(raw_word(p+904)!=sentinel)return 1;
        if(raw_word(p+912)!=sentinel)return 1;
        if(raw_word(p+920)!=sentinel)return 1;
        if(raw_word(p+928)!=sentinel)return 1;
        if(raw_word(p+936)!=sentinel)return 1;
        if(raw_word(p+944)!=sentinel)return 1;
        if(raw_word(p+952)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[14];
        if(raw_word(p+896)!=expected[0])return 1;
        if(raw_word(p+904)!=expected[1])return 1;
        if(raw_word(p+912)!=expected[2])return 1;
        if(raw_word(p+920)!=expected[3])return 1;
        if(raw_word(p+928)!=expected[4])return 1;
        if(raw_word(p+936)!=expected[5])return 1;
        if(raw_word(p+944)!=expected[6])return 1;
        if(raw_word(p+952)!=expected[7])return 1;
    }
    if(indices[15]==0) {
        if(raw_word(p+960)!=sentinel)return 1;
        if(raw_word(p+968)!=sentinel)return 1;
        if(raw_word(p+976)!=sentinel)return 1;
        if(raw_word(p+984)!=sentinel)return 1;
        if(raw_word(p+992)!=sentinel)return 1;
        if(raw_word(p+1000)!=sentinel)return 1;
        if(raw_word(p+1008)!=sentinel)return 1;
        if(raw_word(p+1016)!=sentinel)return 1;
    } else {
        const uint64_t *expected=expected_dictionary+8*(unsigned)indices[15];
        if(raw_word(p+960)!=expected[0])return 1;
        if(raw_word(p+968)!=expected[1])return 1;
        if(raw_word(p+976)!=expected[2])return 1;
        if(raw_word(p+984)!=expected[3])return 1;
        if(raw_word(p+992)!=expected[4])return 1;
        if(raw_word(p+1000)!=expected[5])return 1;
        if(raw_word(p+1008)!=expected[6])return 1;
        if(raw_word(p+1016)!=expected[7])return 1;
    }
    uint16_t tail;
    __builtin_memcpy(&tail,p+1024,2);
    return tail!=(uint16_t)expected_dictionary[8*(unsigned)indices[16]];
}
