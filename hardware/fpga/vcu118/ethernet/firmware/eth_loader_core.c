#include "eth_loader_core.h"

#include <string.h>

const uint32_t eth_loader_crc32_table[4][256] = {
    {
        UINT32_C(0x00000000), UINT32_C(0x77073096), UINT32_C(0xee0e612c), UINT32_C(0x990951ba),
        UINT32_C(0x076dc419), UINT32_C(0x706af48f), UINT32_C(0xe963a535), UINT32_C(0x9e6495a3),
        UINT32_C(0x0edb8832), UINT32_C(0x79dcb8a4), UINT32_C(0xe0d5e91e), UINT32_C(0x97d2d988),
        UINT32_C(0x09b64c2b), UINT32_C(0x7eb17cbd), UINT32_C(0xe7b82d07), UINT32_C(0x90bf1d91),
        UINT32_C(0x1db71064), UINT32_C(0x6ab020f2), UINT32_C(0xf3b97148), UINT32_C(0x84be41de),
        UINT32_C(0x1adad47d), UINT32_C(0x6ddde4eb), UINT32_C(0xf4d4b551), UINT32_C(0x83d385c7),
        UINT32_C(0x136c9856), UINT32_C(0x646ba8c0), UINT32_C(0xfd62f97a), UINT32_C(0x8a65c9ec),
        UINT32_C(0x14015c4f), UINT32_C(0x63066cd9), UINT32_C(0xfa0f3d63), UINT32_C(0x8d080df5),
        UINT32_C(0x3b6e20c8), UINT32_C(0x4c69105e), UINT32_C(0xd56041e4), UINT32_C(0xa2677172),
        UINT32_C(0x3c03e4d1), UINT32_C(0x4b04d447), UINT32_C(0xd20d85fd), UINT32_C(0xa50ab56b),
        UINT32_C(0x35b5a8fa), UINT32_C(0x42b2986c), UINT32_C(0xdbbbc9d6), UINT32_C(0xacbcf940),
        UINT32_C(0x32d86ce3), UINT32_C(0x45df5c75), UINT32_C(0xdcd60dcf), UINT32_C(0xabd13d59),
        UINT32_C(0x26d930ac), UINT32_C(0x51de003a), UINT32_C(0xc8d75180), UINT32_C(0xbfd06116),
        UINT32_C(0x21b4f4b5), UINT32_C(0x56b3c423), UINT32_C(0xcfba9599), UINT32_C(0xb8bda50f),
        UINT32_C(0x2802b89e), UINT32_C(0x5f058808), UINT32_C(0xc60cd9b2), UINT32_C(0xb10be924),
        UINT32_C(0x2f6f7c87), UINT32_C(0x58684c11), UINT32_C(0xc1611dab), UINT32_C(0xb6662d3d),
        UINT32_C(0x76dc4190), UINT32_C(0x01db7106), UINT32_C(0x98d220bc), UINT32_C(0xefd5102a),
        UINT32_C(0x71b18589), UINT32_C(0x06b6b51f), UINT32_C(0x9fbfe4a5), UINT32_C(0xe8b8d433),
        UINT32_C(0x7807c9a2), UINT32_C(0x0f00f934), UINT32_C(0x9609a88e), UINT32_C(0xe10e9818),
        UINT32_C(0x7f6a0dbb), UINT32_C(0x086d3d2d), UINT32_C(0x91646c97), UINT32_C(0xe6635c01),
        UINT32_C(0x6b6b51f4), UINT32_C(0x1c6c6162), UINT32_C(0x856530d8), UINT32_C(0xf262004e),
        UINT32_C(0x6c0695ed), UINT32_C(0x1b01a57b), UINT32_C(0x8208f4c1), UINT32_C(0xf50fc457),
        UINT32_C(0x65b0d9c6), UINT32_C(0x12b7e950), UINT32_C(0x8bbeb8ea), UINT32_C(0xfcb9887c),
        UINT32_C(0x62dd1ddf), UINT32_C(0x15da2d49), UINT32_C(0x8cd37cf3), UINT32_C(0xfbd44c65),
        UINT32_C(0x4db26158), UINT32_C(0x3ab551ce), UINT32_C(0xa3bc0074), UINT32_C(0xd4bb30e2),
        UINT32_C(0x4adfa541), UINT32_C(0x3dd895d7), UINT32_C(0xa4d1c46d), UINT32_C(0xd3d6f4fb),
        UINT32_C(0x4369e96a), UINT32_C(0x346ed9fc), UINT32_C(0xad678846), UINT32_C(0xda60b8d0),
        UINT32_C(0x44042d73), UINT32_C(0x33031de5), UINT32_C(0xaa0a4c5f), UINT32_C(0xdd0d7cc9),
        UINT32_C(0x5005713c), UINT32_C(0x270241aa), UINT32_C(0xbe0b1010), UINT32_C(0xc90c2086),
        UINT32_C(0x5768b525), UINT32_C(0x206f85b3), UINT32_C(0xb966d409), UINT32_C(0xce61e49f),
        UINT32_C(0x5edef90e), UINT32_C(0x29d9c998), UINT32_C(0xb0d09822), UINT32_C(0xc7d7a8b4),
        UINT32_C(0x59b33d17), UINT32_C(0x2eb40d81), UINT32_C(0xb7bd5c3b), UINT32_C(0xc0ba6cad),
        UINT32_C(0xedb88320), UINT32_C(0x9abfb3b6), UINT32_C(0x03b6e20c), UINT32_C(0x74b1d29a),
        UINT32_C(0xead54739), UINT32_C(0x9dd277af), UINT32_C(0x04db2615), UINT32_C(0x73dc1683),
        UINT32_C(0xe3630b12), UINT32_C(0x94643b84), UINT32_C(0x0d6d6a3e), UINT32_C(0x7a6a5aa8),
        UINT32_C(0xe40ecf0b), UINT32_C(0x9309ff9d), UINT32_C(0x0a00ae27), UINT32_C(0x7d079eb1),
        UINT32_C(0xf00f9344), UINT32_C(0x8708a3d2), UINT32_C(0x1e01f268), UINT32_C(0x6906c2fe),
        UINT32_C(0xf762575d), UINT32_C(0x806567cb), UINT32_C(0x196c3671), UINT32_C(0x6e6b06e7),
        UINT32_C(0xfed41b76), UINT32_C(0x89d32be0), UINT32_C(0x10da7a5a), UINT32_C(0x67dd4acc),
        UINT32_C(0xf9b9df6f), UINT32_C(0x8ebeeff9), UINT32_C(0x17b7be43), UINT32_C(0x60b08ed5),
        UINT32_C(0xd6d6a3e8), UINT32_C(0xa1d1937e), UINT32_C(0x38d8c2c4), UINT32_C(0x4fdff252),
        UINT32_C(0xd1bb67f1), UINT32_C(0xa6bc5767), UINT32_C(0x3fb506dd), UINT32_C(0x48b2364b),
        UINT32_C(0xd80d2bda), UINT32_C(0xaf0a1b4c), UINT32_C(0x36034af6), UINT32_C(0x41047a60),
        UINT32_C(0xdf60efc3), UINT32_C(0xa867df55), UINT32_C(0x316e8eef), UINT32_C(0x4669be79),
        UINT32_C(0xcb61b38c), UINT32_C(0xbc66831a), UINT32_C(0x256fd2a0), UINT32_C(0x5268e236),
        UINT32_C(0xcc0c7795), UINT32_C(0xbb0b4703), UINT32_C(0x220216b9), UINT32_C(0x5505262f),
        UINT32_C(0xc5ba3bbe), UINT32_C(0xb2bd0b28), UINT32_C(0x2bb45a92), UINT32_C(0x5cb36a04),
        UINT32_C(0xc2d7ffa7), UINT32_C(0xb5d0cf31), UINT32_C(0x2cd99e8b), UINT32_C(0x5bdeae1d),
        UINT32_C(0x9b64c2b0), UINT32_C(0xec63f226), UINT32_C(0x756aa39c), UINT32_C(0x026d930a),
        UINT32_C(0x9c0906a9), UINT32_C(0xeb0e363f), UINT32_C(0x72076785), UINT32_C(0x05005713),
        UINT32_C(0x95bf4a82), UINT32_C(0xe2b87a14), UINT32_C(0x7bb12bae), UINT32_C(0x0cb61b38),
        UINT32_C(0x92d28e9b), UINT32_C(0xe5d5be0d), UINT32_C(0x7cdcefb7), UINT32_C(0x0bdbdf21),
        UINT32_C(0x86d3d2d4), UINT32_C(0xf1d4e242), UINT32_C(0x68ddb3f8), UINT32_C(0x1fda836e),
        UINT32_C(0x81be16cd), UINT32_C(0xf6b9265b), UINT32_C(0x6fb077e1), UINT32_C(0x18b74777),
        UINT32_C(0x88085ae6), UINT32_C(0xff0f6a70), UINT32_C(0x66063bca), UINT32_C(0x11010b5c),
        UINT32_C(0x8f659eff), UINT32_C(0xf862ae69), UINT32_C(0x616bffd3), UINT32_C(0x166ccf45),
        UINT32_C(0xa00ae278), UINT32_C(0xd70dd2ee), UINT32_C(0x4e048354), UINT32_C(0x3903b3c2),
        UINT32_C(0xa7672661), UINT32_C(0xd06016f7), UINT32_C(0x4969474d), UINT32_C(0x3e6e77db),
        UINT32_C(0xaed16a4a), UINT32_C(0xd9d65adc), UINT32_C(0x40df0b66), UINT32_C(0x37d83bf0),
        UINT32_C(0xa9bcae53), UINT32_C(0xdebb9ec5), UINT32_C(0x47b2cf7f), UINT32_C(0x30b5ffe9),
        UINT32_C(0xbdbdf21c), UINT32_C(0xcabac28a), UINT32_C(0x53b39330), UINT32_C(0x24b4a3a6),
        UINT32_C(0xbad03605), UINT32_C(0xcdd70693), UINT32_C(0x54de5729), UINT32_C(0x23d967bf),
        UINT32_C(0xb3667a2e), UINT32_C(0xc4614ab8), UINT32_C(0x5d681b02), UINT32_C(0x2a6f2b94),
        UINT32_C(0xb40bbe37), UINT32_C(0xc30c8ea1), UINT32_C(0x5a05df1b), UINT32_C(0x2d02ef8d),
    },
    {
        UINT32_C(0x00000000), UINT32_C(0x191b3141), UINT32_C(0x32366282), UINT32_C(0x2b2d53c3),
        UINT32_C(0x646cc504), UINT32_C(0x7d77f445), UINT32_C(0x565aa786), UINT32_C(0x4f4196c7),
        UINT32_C(0xc8d98a08), UINT32_C(0xd1c2bb49), UINT32_C(0xfaefe88a), UINT32_C(0xe3f4d9cb),
        UINT32_C(0xacb54f0c), UINT32_C(0xb5ae7e4d), UINT32_C(0x9e832d8e), UINT32_C(0x87981ccf),
        UINT32_C(0x4ac21251), UINT32_C(0x53d92310), UINT32_C(0x78f470d3), UINT32_C(0x61ef4192),
        UINT32_C(0x2eaed755), UINT32_C(0x37b5e614), UINT32_C(0x1c98b5d7), UINT32_C(0x05838496),
        UINT32_C(0x821b9859), UINT32_C(0x9b00a918), UINT32_C(0xb02dfadb), UINT32_C(0xa936cb9a),
        UINT32_C(0xe6775d5d), UINT32_C(0xff6c6c1c), UINT32_C(0xd4413fdf), UINT32_C(0xcd5a0e9e),
        UINT32_C(0x958424a2), UINT32_C(0x8c9f15e3), UINT32_C(0xa7b24620), UINT32_C(0xbea97761),
        UINT32_C(0xf1e8e1a6), UINT32_C(0xe8f3d0e7), UINT32_C(0xc3de8324), UINT32_C(0xdac5b265),
        UINT32_C(0x5d5daeaa), UINT32_C(0x44469feb), UINT32_C(0x6f6bcc28), UINT32_C(0x7670fd69),
        UINT32_C(0x39316bae), UINT32_C(0x202a5aef), UINT32_C(0x0b07092c), UINT32_C(0x121c386d),
        UINT32_C(0xdf4636f3), UINT32_C(0xc65d07b2), UINT32_C(0xed705471), UINT32_C(0xf46b6530),
        UINT32_C(0xbb2af3f7), UINT32_C(0xa231c2b6), UINT32_C(0x891c9175), UINT32_C(0x9007a034),
        UINT32_C(0x179fbcfb), UINT32_C(0x0e848dba), UINT32_C(0x25a9de79), UINT32_C(0x3cb2ef38),
        UINT32_C(0x73f379ff), UINT32_C(0x6ae848be), UINT32_C(0x41c51b7d), UINT32_C(0x58de2a3c),
        UINT32_C(0xf0794f05), UINT32_C(0xe9627e44), UINT32_C(0xc24f2d87), UINT32_C(0xdb541cc6),
        UINT32_C(0x94158a01), UINT32_C(0x8d0ebb40), UINT32_C(0xa623e883), UINT32_C(0xbf38d9c2),
        UINT32_C(0x38a0c50d), UINT32_C(0x21bbf44c), UINT32_C(0x0a96a78f), UINT32_C(0x138d96ce),
        UINT32_C(0x5ccc0009), UINT32_C(0x45d73148), UINT32_C(0x6efa628b), UINT32_C(0x77e153ca),
        UINT32_C(0xbabb5d54), UINT32_C(0xa3a06c15), UINT32_C(0x888d3fd6), UINT32_C(0x91960e97),
        UINT32_C(0xded79850), UINT32_C(0xc7cca911), UINT32_C(0xece1fad2), UINT32_C(0xf5facb93),
        UINT32_C(0x7262d75c), UINT32_C(0x6b79e61d), UINT32_C(0x4054b5de), UINT32_C(0x594f849f),
        UINT32_C(0x160e1258), UINT32_C(0x0f152319), UINT32_C(0x243870da), UINT32_C(0x3d23419b),
        UINT32_C(0x65fd6ba7), UINT32_C(0x7ce65ae6), UINT32_C(0x57cb0925), UINT32_C(0x4ed03864),
        UINT32_C(0x0191aea3), UINT32_C(0x188a9fe2), UINT32_C(0x33a7cc21), UINT32_C(0x2abcfd60),
        UINT32_C(0xad24e1af), UINT32_C(0xb43fd0ee), UINT32_C(0x9f12832d), UINT32_C(0x8609b26c),
        UINT32_C(0xc94824ab), UINT32_C(0xd05315ea), UINT32_C(0xfb7e4629), UINT32_C(0xe2657768),
        UINT32_C(0x2f3f79f6), UINT32_C(0x362448b7), UINT32_C(0x1d091b74), UINT32_C(0x04122a35),
        UINT32_C(0x4b53bcf2), UINT32_C(0x52488db3), UINT32_C(0x7965de70), UINT32_C(0x607eef31),
        UINT32_C(0xe7e6f3fe), UINT32_C(0xfefdc2bf), UINT32_C(0xd5d0917c), UINT32_C(0xcccba03d),
        UINT32_C(0x838a36fa), UINT32_C(0x9a9107bb), UINT32_C(0xb1bc5478), UINT32_C(0xa8a76539),
        UINT32_C(0x3b83984b), UINT32_C(0x2298a90a), UINT32_C(0x09b5fac9), UINT32_C(0x10aecb88),
        UINT32_C(0x5fef5d4f), UINT32_C(0x46f46c0e), UINT32_C(0x6dd93fcd), UINT32_C(0x74c20e8c),
        UINT32_C(0xf35a1243), UINT32_C(0xea412302), UINT32_C(0xc16c70c1), UINT32_C(0xd8774180),
        UINT32_C(0x9736d747), UINT32_C(0x8e2de606), UINT32_C(0xa500b5c5), UINT32_C(0xbc1b8484),
        UINT32_C(0x71418a1a), UINT32_C(0x685abb5b), UINT32_C(0x4377e898), UINT32_C(0x5a6cd9d9),
        UINT32_C(0x152d4f1e), UINT32_C(0x0c367e5f), UINT32_C(0x271b2d9c), UINT32_C(0x3e001cdd),
        UINT32_C(0xb9980012), UINT32_C(0xa0833153), UINT32_C(0x8bae6290), UINT32_C(0x92b553d1),
        UINT32_C(0xddf4c516), UINT32_C(0xc4eff457), UINT32_C(0xefc2a794), UINT32_C(0xf6d996d5),
        UINT32_C(0xae07bce9), UINT32_C(0xb71c8da8), UINT32_C(0x9c31de6b), UINT32_C(0x852aef2a),
        UINT32_C(0xca6b79ed), UINT32_C(0xd37048ac), UINT32_C(0xf85d1b6f), UINT32_C(0xe1462a2e),
        UINT32_C(0x66de36e1), UINT32_C(0x7fc507a0), UINT32_C(0x54e85463), UINT32_C(0x4df36522),
        UINT32_C(0x02b2f3e5), UINT32_C(0x1ba9c2a4), UINT32_C(0x30849167), UINT32_C(0x299fa026),
        UINT32_C(0xe4c5aeb8), UINT32_C(0xfdde9ff9), UINT32_C(0xd6f3cc3a), UINT32_C(0xcfe8fd7b),
        UINT32_C(0x80a96bbc), UINT32_C(0x99b25afd), UINT32_C(0xb29f093e), UINT32_C(0xab84387f),
        UINT32_C(0x2c1c24b0), UINT32_C(0x350715f1), UINT32_C(0x1e2a4632), UINT32_C(0x07317773),
        UINT32_C(0x4870e1b4), UINT32_C(0x516bd0f5), UINT32_C(0x7a468336), UINT32_C(0x635db277),
        UINT32_C(0xcbfad74e), UINT32_C(0xd2e1e60f), UINT32_C(0xf9ccb5cc), UINT32_C(0xe0d7848d),
        UINT32_C(0xaf96124a), UINT32_C(0xb68d230b), UINT32_C(0x9da070c8), UINT32_C(0x84bb4189),
        UINT32_C(0x03235d46), UINT32_C(0x1a386c07), UINT32_C(0x31153fc4), UINT32_C(0x280e0e85),
        UINT32_C(0x674f9842), UINT32_C(0x7e54a903), UINT32_C(0x5579fac0), UINT32_C(0x4c62cb81),
        UINT32_C(0x8138c51f), UINT32_C(0x9823f45e), UINT32_C(0xb30ea79d), UINT32_C(0xaa1596dc),
        UINT32_C(0xe554001b), UINT32_C(0xfc4f315a), UINT32_C(0xd7626299), UINT32_C(0xce7953d8),
        UINT32_C(0x49e14f17), UINT32_C(0x50fa7e56), UINT32_C(0x7bd72d95), UINT32_C(0x62cc1cd4),
        UINT32_C(0x2d8d8a13), UINT32_C(0x3496bb52), UINT32_C(0x1fbbe891), UINT32_C(0x06a0d9d0),
        UINT32_C(0x5e7ef3ec), UINT32_C(0x4765c2ad), UINT32_C(0x6c48916e), UINT32_C(0x7553a02f),
        UINT32_C(0x3a1236e8), UINT32_C(0x230907a9), UINT32_C(0x0824546a), UINT32_C(0x113f652b),
        UINT32_C(0x96a779e4), UINT32_C(0x8fbc48a5), UINT32_C(0xa4911b66), UINT32_C(0xbd8a2a27),
        UINT32_C(0xf2cbbce0), UINT32_C(0xebd08da1), UINT32_C(0xc0fdde62), UINT32_C(0xd9e6ef23),
        UINT32_C(0x14bce1bd), UINT32_C(0x0da7d0fc), UINT32_C(0x268a833f), UINT32_C(0x3f91b27e),
        UINT32_C(0x70d024b9), UINT32_C(0x69cb15f8), UINT32_C(0x42e6463b), UINT32_C(0x5bfd777a),
        UINT32_C(0xdc656bb5), UINT32_C(0xc57e5af4), UINT32_C(0xee530937), UINT32_C(0xf7483876),
        UINT32_C(0xb809aeb1), UINT32_C(0xa1129ff0), UINT32_C(0x8a3fcc33), UINT32_C(0x9324fd72),
    },
    {
        UINT32_C(0x00000000), UINT32_C(0x01c26a37), UINT32_C(0x0384d46e), UINT32_C(0x0246be59),
        UINT32_C(0x0709a8dc), UINT32_C(0x06cbc2eb), UINT32_C(0x048d7cb2), UINT32_C(0x054f1685),
        UINT32_C(0x0e1351b8), UINT32_C(0x0fd13b8f), UINT32_C(0x0d9785d6), UINT32_C(0x0c55efe1),
        UINT32_C(0x091af964), UINT32_C(0x08d89353), UINT32_C(0x0a9e2d0a), UINT32_C(0x0b5c473d),
        UINT32_C(0x1c26a370), UINT32_C(0x1de4c947), UINT32_C(0x1fa2771e), UINT32_C(0x1e601d29),
        UINT32_C(0x1b2f0bac), UINT32_C(0x1aed619b), UINT32_C(0x18abdfc2), UINT32_C(0x1969b5f5),
        UINT32_C(0x1235f2c8), UINT32_C(0x13f798ff), UINT32_C(0x11b126a6), UINT32_C(0x10734c91),
        UINT32_C(0x153c5a14), UINT32_C(0x14fe3023), UINT32_C(0x16b88e7a), UINT32_C(0x177ae44d),
        UINT32_C(0x384d46e0), UINT32_C(0x398f2cd7), UINT32_C(0x3bc9928e), UINT32_C(0x3a0bf8b9),
        UINT32_C(0x3f44ee3c), UINT32_C(0x3e86840b), UINT32_C(0x3cc03a52), UINT32_C(0x3d025065),
        UINT32_C(0x365e1758), UINT32_C(0x379c7d6f), UINT32_C(0x35dac336), UINT32_C(0x3418a901),
        UINT32_C(0x3157bf84), UINT32_C(0x3095d5b3), UINT32_C(0x32d36bea), UINT32_C(0x331101dd),
        UINT32_C(0x246be590), UINT32_C(0x25a98fa7), UINT32_C(0x27ef31fe), UINT32_C(0x262d5bc9),
        UINT32_C(0x23624d4c), UINT32_C(0x22a0277b), UINT32_C(0x20e69922), UINT32_C(0x2124f315),
        UINT32_C(0x2a78b428), UINT32_C(0x2bbade1f), UINT32_C(0x29fc6046), UINT32_C(0x283e0a71),
        UINT32_C(0x2d711cf4), UINT32_C(0x2cb376c3), UINT32_C(0x2ef5c89a), UINT32_C(0x2f37a2ad),
        UINT32_C(0x709a8dc0), UINT32_C(0x7158e7f7), UINT32_C(0x731e59ae), UINT32_C(0x72dc3399),
        UINT32_C(0x7793251c), UINT32_C(0x76514f2b), UINT32_C(0x7417f172), UINT32_C(0x75d59b45),
        UINT32_C(0x7e89dc78), UINT32_C(0x7f4bb64f), UINT32_C(0x7d0d0816), UINT32_C(0x7ccf6221),
        UINT32_C(0x798074a4), UINT32_C(0x78421e93), UINT32_C(0x7a04a0ca), UINT32_C(0x7bc6cafd),
        UINT32_C(0x6cbc2eb0), UINT32_C(0x6d7e4487), UINT32_C(0x6f38fade), UINT32_C(0x6efa90e9),
        UINT32_C(0x6bb5866c), UINT32_C(0x6a77ec5b), UINT32_C(0x68315202), UINT32_C(0x69f33835),
        UINT32_C(0x62af7f08), UINT32_C(0x636d153f), UINT32_C(0x612bab66), UINT32_C(0x60e9c151),
        UINT32_C(0x65a6d7d4), UINT32_C(0x6464bde3), UINT32_C(0x662203ba), UINT32_C(0x67e0698d),
        UINT32_C(0x48d7cb20), UINT32_C(0x4915a117), UINT32_C(0x4b531f4e), UINT32_C(0x4a917579),
        UINT32_C(0x4fde63fc), UINT32_C(0x4e1c09cb), UINT32_C(0x4c5ab792), UINT32_C(0x4d98dda5),
        UINT32_C(0x46c49a98), UINT32_C(0x4706f0af), UINT32_C(0x45404ef6), UINT32_C(0x448224c1),
        UINT32_C(0x41cd3244), UINT32_C(0x400f5873), UINT32_C(0x4249e62a), UINT32_C(0x438b8c1d),
        UINT32_C(0x54f16850), UINT32_C(0x55330267), UINT32_C(0x5775bc3e), UINT32_C(0x56b7d609),
        UINT32_C(0x53f8c08c), UINT32_C(0x523aaabb), UINT32_C(0x507c14e2), UINT32_C(0x51be7ed5),
        UINT32_C(0x5ae239e8), UINT32_C(0x5b2053df), UINT32_C(0x5966ed86), UINT32_C(0x58a487b1),
        UINT32_C(0x5deb9134), UINT32_C(0x5c29fb03), UINT32_C(0x5e6f455a), UINT32_C(0x5fad2f6d),
        UINT32_C(0xe1351b80), UINT32_C(0xe0f771b7), UINT32_C(0xe2b1cfee), UINT32_C(0xe373a5d9),
        UINT32_C(0xe63cb35c), UINT32_C(0xe7fed96b), UINT32_C(0xe5b86732), UINT32_C(0xe47a0d05),
        UINT32_C(0xef264a38), UINT32_C(0xeee4200f), UINT32_C(0xeca29e56), UINT32_C(0xed60f461),
        UINT32_C(0xe82fe2e4), UINT32_C(0xe9ed88d3), UINT32_C(0xebab368a), UINT32_C(0xea695cbd),
        UINT32_C(0xfd13b8f0), UINT32_C(0xfcd1d2c7), UINT32_C(0xfe976c9e), UINT32_C(0xff5506a9),
        UINT32_C(0xfa1a102c), UINT32_C(0xfbd87a1b), UINT32_C(0xf99ec442), UINT32_C(0xf85cae75),
        UINT32_C(0xf300e948), UINT32_C(0xf2c2837f), UINT32_C(0xf0843d26), UINT32_C(0xf1465711),
        UINT32_C(0xf4094194), UINT32_C(0xf5cb2ba3), UINT32_C(0xf78d95fa), UINT32_C(0xf64fffcd),
        UINT32_C(0xd9785d60), UINT32_C(0xd8ba3757), UINT32_C(0xdafc890e), UINT32_C(0xdb3ee339),
        UINT32_C(0xde71f5bc), UINT32_C(0xdfb39f8b), UINT32_C(0xddf521d2), UINT32_C(0xdc374be5),
        UINT32_C(0xd76b0cd8), UINT32_C(0xd6a966ef), UINT32_C(0xd4efd8b6), UINT32_C(0xd52db281),
        UINT32_C(0xd062a404), UINT32_C(0xd1a0ce33), UINT32_C(0xd3e6706a), UINT32_C(0xd2241a5d),
        UINT32_C(0xc55efe10), UINT32_C(0xc49c9427), UINT32_C(0xc6da2a7e), UINT32_C(0xc7184049),
        UINT32_C(0xc25756cc), UINT32_C(0xc3953cfb), UINT32_C(0xc1d382a2), UINT32_C(0xc011e895),
        UINT32_C(0xcb4dafa8), UINT32_C(0xca8fc59f), UINT32_C(0xc8c97bc6), UINT32_C(0xc90b11f1),
        UINT32_C(0xcc440774), UINT32_C(0xcd866d43), UINT32_C(0xcfc0d31a), UINT32_C(0xce02b92d),
        UINT32_C(0x91af9640), UINT32_C(0x906dfc77), UINT32_C(0x922b422e), UINT32_C(0x93e92819),
        UINT32_C(0x96a63e9c), UINT32_C(0x976454ab), UINT32_C(0x9522eaf2), UINT32_C(0x94e080c5),
        UINT32_C(0x9fbcc7f8), UINT32_C(0x9e7eadcf), UINT32_C(0x9c381396), UINT32_C(0x9dfa79a1),
        UINT32_C(0x98b56f24), UINT32_C(0x99770513), UINT32_C(0x9b31bb4a), UINT32_C(0x9af3d17d),
        UINT32_C(0x8d893530), UINT32_C(0x8c4b5f07), UINT32_C(0x8e0de15e), UINT32_C(0x8fcf8b69),
        UINT32_C(0x8a809dec), UINT32_C(0x8b42f7db), UINT32_C(0x89044982), UINT32_C(0x88c623b5),
        UINT32_C(0x839a6488), UINT32_C(0x82580ebf), UINT32_C(0x801eb0e6), UINT32_C(0x81dcdad1),
        UINT32_C(0x8493cc54), UINT32_C(0x8551a663), UINT32_C(0x8717183a), UINT32_C(0x86d5720d),
        UINT32_C(0xa9e2d0a0), UINT32_C(0xa820ba97), UINT32_C(0xaa6604ce), UINT32_C(0xaba46ef9),
        UINT32_C(0xaeeb787c), UINT32_C(0xaf29124b), UINT32_C(0xad6fac12), UINT32_C(0xacadc625),
        UINT32_C(0xa7f18118), UINT32_C(0xa633eb2f), UINT32_C(0xa4755576), UINT32_C(0xa5b73f41),
        UINT32_C(0xa0f829c4), UINT32_C(0xa13a43f3), UINT32_C(0xa37cfdaa), UINT32_C(0xa2be979d),
        UINT32_C(0xb5c473d0), UINT32_C(0xb40619e7), UINT32_C(0xb640a7be), UINT32_C(0xb782cd89),
        UINT32_C(0xb2cddb0c), UINT32_C(0xb30fb13b), UINT32_C(0xb1490f62), UINT32_C(0xb08b6555),
        UINT32_C(0xbbd72268), UINT32_C(0xba15485f), UINT32_C(0xb853f606), UINT32_C(0xb9919c31),
        UINT32_C(0xbcde8ab4), UINT32_C(0xbd1ce083), UINT32_C(0xbf5a5eda), UINT32_C(0xbe9834ed),
    },
    {
        UINT32_C(0x00000000), UINT32_C(0xb8bc6765), UINT32_C(0xaa09c88b), UINT32_C(0x12b5afee),
        UINT32_C(0x8f629757), UINT32_C(0x37def032), UINT32_C(0x256b5fdc), UINT32_C(0x9dd738b9),
        UINT32_C(0xc5b428ef), UINT32_C(0x7d084f8a), UINT32_C(0x6fbde064), UINT32_C(0xd7018701),
        UINT32_C(0x4ad6bfb8), UINT32_C(0xf26ad8dd), UINT32_C(0xe0df7733), UINT32_C(0x58631056),
        UINT32_C(0x5019579f), UINT32_C(0xe8a530fa), UINT32_C(0xfa109f14), UINT32_C(0x42acf871),
        UINT32_C(0xdf7bc0c8), UINT32_C(0x67c7a7ad), UINT32_C(0x75720843), UINT32_C(0xcdce6f26),
        UINT32_C(0x95ad7f70), UINT32_C(0x2d111815), UINT32_C(0x3fa4b7fb), UINT32_C(0x8718d09e),
        UINT32_C(0x1acfe827), UINT32_C(0xa2738f42), UINT32_C(0xb0c620ac), UINT32_C(0x087a47c9),
        UINT32_C(0xa032af3e), UINT32_C(0x188ec85b), UINT32_C(0x0a3b67b5), UINT32_C(0xb28700d0),
        UINT32_C(0x2f503869), UINT32_C(0x97ec5f0c), UINT32_C(0x8559f0e2), UINT32_C(0x3de59787),
        UINT32_C(0x658687d1), UINT32_C(0xdd3ae0b4), UINT32_C(0xcf8f4f5a), UINT32_C(0x7733283f),
        UINT32_C(0xeae41086), UINT32_C(0x525877e3), UINT32_C(0x40edd80d), UINT32_C(0xf851bf68),
        UINT32_C(0xf02bf8a1), UINT32_C(0x48979fc4), UINT32_C(0x5a22302a), UINT32_C(0xe29e574f),
        UINT32_C(0x7f496ff6), UINT32_C(0xc7f50893), UINT32_C(0xd540a77d), UINT32_C(0x6dfcc018),
        UINT32_C(0x359fd04e), UINT32_C(0x8d23b72b), UINT32_C(0x9f9618c5), UINT32_C(0x272a7fa0),
        UINT32_C(0xbafd4719), UINT32_C(0x0241207c), UINT32_C(0x10f48f92), UINT32_C(0xa848e8f7),
        UINT32_C(0x9b14583d), UINT32_C(0x23a83f58), UINT32_C(0x311d90b6), UINT32_C(0x89a1f7d3),
        UINT32_C(0x1476cf6a), UINT32_C(0xaccaa80f), UINT32_C(0xbe7f07e1), UINT32_C(0x06c36084),
        UINT32_C(0x5ea070d2), UINT32_C(0xe61c17b7), UINT32_C(0xf4a9b859), UINT32_C(0x4c15df3c),
        UINT32_C(0xd1c2e785), UINT32_C(0x697e80e0), UINT32_C(0x7bcb2f0e), UINT32_C(0xc377486b),
        UINT32_C(0xcb0d0fa2), UINT32_C(0x73b168c7), UINT32_C(0x6104c729), UINT32_C(0xd9b8a04c),
        UINT32_C(0x446f98f5), UINT32_C(0xfcd3ff90), UINT32_C(0xee66507e), UINT32_C(0x56da371b),
        UINT32_C(0x0eb9274d), UINT32_C(0xb6054028), UINT32_C(0xa4b0efc6), UINT32_C(0x1c0c88a3),
        UINT32_C(0x81dbb01a), UINT32_C(0x3967d77f), UINT32_C(0x2bd27891), UINT32_C(0x936e1ff4),
        UINT32_C(0x3b26f703), UINT32_C(0x839a9066), UINT32_C(0x912f3f88), UINT32_C(0x299358ed),
        UINT32_C(0xb4446054), UINT32_C(0x0cf80731), UINT32_C(0x1e4da8df), UINT32_C(0xa6f1cfba),
        UINT32_C(0xfe92dfec), UINT32_C(0x462eb889), UINT32_C(0x549b1767), UINT32_C(0xec277002),
        UINT32_C(0x71f048bb), UINT32_C(0xc94c2fde), UINT32_C(0xdbf98030), UINT32_C(0x6345e755),
        UINT32_C(0x6b3fa09c), UINT32_C(0xd383c7f9), UINT32_C(0xc1366817), UINT32_C(0x798a0f72),
        UINT32_C(0xe45d37cb), UINT32_C(0x5ce150ae), UINT32_C(0x4e54ff40), UINT32_C(0xf6e89825),
        UINT32_C(0xae8b8873), UINT32_C(0x1637ef16), UINT32_C(0x048240f8), UINT32_C(0xbc3e279d),
        UINT32_C(0x21e91f24), UINT32_C(0x99557841), UINT32_C(0x8be0d7af), UINT32_C(0x335cb0ca),
        UINT32_C(0xed59b63b), UINT32_C(0x55e5d15e), UINT32_C(0x47507eb0), UINT32_C(0xffec19d5),
        UINT32_C(0x623b216c), UINT32_C(0xda874609), UINT32_C(0xc832e9e7), UINT32_C(0x708e8e82),
        UINT32_C(0x28ed9ed4), UINT32_C(0x9051f9b1), UINT32_C(0x82e4565f), UINT32_C(0x3a58313a),
        UINT32_C(0xa78f0983), UINT32_C(0x1f336ee6), UINT32_C(0x0d86c108), UINT32_C(0xb53aa66d),
        UINT32_C(0xbd40e1a4), UINT32_C(0x05fc86c1), UINT32_C(0x1749292f), UINT32_C(0xaff54e4a),
        UINT32_C(0x322276f3), UINT32_C(0x8a9e1196), UINT32_C(0x982bbe78), UINT32_C(0x2097d91d),
        UINT32_C(0x78f4c94b), UINT32_C(0xc048ae2e), UINT32_C(0xd2fd01c0), UINT32_C(0x6a4166a5),
        UINT32_C(0xf7965e1c), UINT32_C(0x4f2a3979), UINT32_C(0x5d9f9697), UINT32_C(0xe523f1f2),
        UINT32_C(0x4d6b1905), UINT32_C(0xf5d77e60), UINT32_C(0xe762d18e), UINT32_C(0x5fdeb6eb),
        UINT32_C(0xc2098e52), UINT32_C(0x7ab5e937), UINT32_C(0x680046d9), UINT32_C(0xd0bc21bc),
        UINT32_C(0x88df31ea), UINT32_C(0x3063568f), UINT32_C(0x22d6f961), UINT32_C(0x9a6a9e04),
        UINT32_C(0x07bda6bd), UINT32_C(0xbf01c1d8), UINT32_C(0xadb46e36), UINT32_C(0x15080953),
        UINT32_C(0x1d724e9a), UINT32_C(0xa5ce29ff), UINT32_C(0xb77b8611), UINT32_C(0x0fc7e174),
        UINT32_C(0x9210d9cd), UINT32_C(0x2aacbea8), UINT32_C(0x38191146), UINT32_C(0x80a57623),
        UINT32_C(0xd8c66675), UINT32_C(0x607a0110), UINT32_C(0x72cfaefe), UINT32_C(0xca73c99b),
        UINT32_C(0x57a4f122), UINT32_C(0xef189647), UINT32_C(0xfdad39a9), UINT32_C(0x45115ecc),
        UINT32_C(0x764dee06), UINT32_C(0xcef18963), UINT32_C(0xdc44268d), UINT32_C(0x64f841e8),
        UINT32_C(0xf92f7951), UINT32_C(0x41931e34), UINT32_C(0x5326b1da), UINT32_C(0xeb9ad6bf),
        UINT32_C(0xb3f9c6e9), UINT32_C(0x0b45a18c), UINT32_C(0x19f00e62), UINT32_C(0xa14c6907),
        UINT32_C(0x3c9b51be), UINT32_C(0x842736db), UINT32_C(0x96929935), UINT32_C(0x2e2efe50),
        UINT32_C(0x2654b999), UINT32_C(0x9ee8defc), UINT32_C(0x8c5d7112), UINT32_C(0x34e11677),
        UINT32_C(0xa9362ece), UINT32_C(0x118a49ab), UINT32_C(0x033fe645), UINT32_C(0xbb838120),
        UINT32_C(0xe3e09176), UINT32_C(0x5b5cf613), UINT32_C(0x49e959fd), UINT32_C(0xf1553e98),
        UINT32_C(0x6c820621), UINT32_C(0xd43e6144), UINT32_C(0xc68bceaa), UINT32_C(0x7e37a9cf),
        UINT32_C(0xd67f4138), UINT32_C(0x6ec3265d), UINT32_C(0x7c7689b3), UINT32_C(0xc4caeed6),
        UINT32_C(0x591dd66f), UINT32_C(0xe1a1b10a), UINT32_C(0xf3141ee4), UINT32_C(0x4ba87981),
        UINT32_C(0x13cb69d7), UINT32_C(0xab770eb2), UINT32_C(0xb9c2a15c), UINT32_C(0x017ec639),
        UINT32_C(0x9ca9fe80), UINT32_C(0x241599e5), UINT32_C(0x36a0360b), UINT32_C(0x8e1c516e),
        UINT32_C(0x866616a7), UINT32_C(0x3eda71c2), UINT32_C(0x2c6fde2c), UINT32_C(0x94d3b949),
        UINT32_C(0x090481f0), UINT32_C(0xb1b8e695), UINT32_C(0xa30d497b), UINT32_C(0x1bb12e1e),
        UINT32_C(0x43d23e48), UINT32_C(0xfb6e592d), UINT32_C(0xe9dbf6c3), UINT32_C(0x516791a6),
        UINT32_C(0xccb0a91f), UINT32_C(0x740cce7a), UINT32_C(0x66b96194), UINT32_C(0xde0506f1),
    },
};

#define DDR_START UINT64_C(0x80000000)
#define DDR_END UINT64_C(0x100000000)
#define MAX_CHUNK 65536u

static const uint8_t magic[8] = {'A', 'R', 'A', 'E', 'T', 'H', '0', '1'};

static uint32_t load32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
           (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static uint64_t load64(const uint8_t *bytes) {
    return (uint64_t)load32(bytes) | (uint64_t)load32(bytes + 4) << 32;
}

static void store32(uint8_t *bytes, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) bytes[i] = (uint8_t)(value >> (8 * i));
}

static void store64(uint8_t *bytes, uint64_t value) {
    store32(bytes, (uint32_t)value);
    store32(bytes + 4, (uint32_t)(value >> 32));
}

uint32_t eth_loader_crc32(const void *data, size_t n) {
    const uint8_t *bytes = data;
    uint32_t crc = UINT32_MAX;
    size_t i = 0;
#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__) && \
    __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    while (i < n && ((uintptr_t)(bytes + i) & 3u))
        crc = eth_loader_crc32_byte(crc, bytes[i++]);
    while (n - i >= sizeof(uint32_t)) {
        uint32_t word;
        memcpy(&word, bytes + i, sizeof(word));
        crc = eth_loader_crc32_word(crc, word);
        i += sizeof(word);
    }
#endif
    for (; i < n; ++i)
        crc = eth_loader_crc32_byte(crc, bytes[i]);
    return ~crc;
}

static int acknowledge(const struct eth_loader_io *io, void *context,
                       uint64_t address, uint32_t crc, uint32_t status) {
    uint8_t packet[16];
    store64(packet, address);
    store32(packet + 8, crc);
    store32(packet + 12, status);
    return io->send(context, packet, sizeof(packet));
}

int eth_loader_receive(const struct eth_loader_io *io, void *context,
                       void *scratch, size_t scratch_size) {
    uint8_t packet[20];
    uint64_t last_end = DDR_START;
    size_t max_chunk = scratch_size < MAX_CHUNK ? scratch_size : MAX_CHUNK;
    int wrote = 0;
    if (!io || !io->receive || !io->send || !io->write_ddr ||
        !io->readback_crc32 || !scratch || max_chunk == 0) return -1;
    if (io->receive(context, packet, sizeof(magic)) ||
        memcmp(packet, magic, sizeof(magic))) return -2;
    memcpy(packet, magic, sizeof(magic));
    store32(packet + 8, 1);  /* CAP_HOST; DDR2 intentionally absent. */
    store32(packet + 12, (uint32_t)max_chunk);
    if (io->send(context, packet, 16)) return -3;

    for (;;) {
        uint64_t address;
        uint32_t length, expected_crc, actual_crc;
        if (io->receive(context, packet, sizeof(packet))) return -4;
        address = load64(packet + 4);
        length = load32(packet + 12);
        expected_crc = load32(packet + 16);
        if (memcmp(packet, "DONE", 4) == 0) {
            if (!wrote || length != 0 || expected_crc != 0 ||
                address < DDR_START || address >= DDR_END) {
                acknowledge(io, context, address, 0, 1);
                return -5;
            }
            return acknowledge(io, context, address, 0, 0) ? -6 : 0;
        }
        if (memcmp(packet, "DATA", 4) != 0 || length == 0 ||
            length > max_chunk || address < DDR_START || address >= DDR_END ||
            length > DDR_END - address || address < last_end) {
            acknowledge(io, context, address, 0, 1);
            return -7;
        }
        if (io->receive(context, scratch, length)) return -8;
        if (eth_loader_crc32(scratch, length) != expected_crc) {
            acknowledge(io, context, address, 0, 2);
            return -9;
        }
        if (io->write_ddr(context, address, scratch, length) ||
            io->readback_crc32(context, address, length, &actual_crc)) {
            acknowledge(io, context, address, 0, 3);
            return -10;
        }
        if (acknowledge(io, context, address, actual_crc,
                        actual_crc == expected_crc ? 0 : 4)) return -11;
        if (actual_crc != expected_crc) return -12;
        last_end = address + length;
        wrote = 1;
    }
}
