"""Exact fresh scalar setup and full ordered eight-byte oracle coverage."""


def require(ok, message):
    if not ok:
        raise ValueError(message)


class SetupLedger:
    def __init__(self, input_address, output_address):
        self.input = input_address
        self.output = output_address
        self.in_bytes = 0
        self.out_bytes = 0
        self.calls = 0
        self.input_stores = 0
        self.output_stores = 0

    def store(self, address, size, value, case):
        require(size == 8 and address % 8 == 0, 'Non-word setup store')
        if self.input <= address < self.input + 1024:
            require(self.out_bytes == 0 and address == self.input + self.in_bytes,
                    'Missing/duplicate/out-of-order fresh input store')
            offset = self.in_bytes
            expected = sum((((offset + j) * 37 + case['seed'] * 71 + 3) & 255) << (8*j)
                           for j in range(8))
            require(value == expected, 'Fresh input value')
            self.in_bytes += 8
            self.input_stores += 1
        else:
            require(self.output <= address < self.output + 1088 and self.in_bytes == 1024
                    and address == self.output + self.out_bytes, 'Fresh output coverage/order')
            require(value == 0x5b5b5b5b5b5b5b5b, 'Fresh output sentinel')
            self.out_bytes += 8
            self.output_stores += 1

    def enter(self):
        require((self.in_bytes, self.out_bytes) == (1024, 1088), 'Incomplete fresh setup')
        self.in_bytes = self.out_bytes = 0
        self.calls += 1

    def finish(self):
        require((self.in_bytes, self.out_bytes, self.calls, self.input_stores, self.output_stores)
                == (0, 0, 1134, 1134*128, 1134*136), 'Full fresh-store ledger')


def word_read(active, offset, size, value):
    require(size == 8 and offset % 8 == 0 and 0 <= offset <= 1080,
            'Non-word oracle or bounds')
    require(offset == len(active['reads']), 'Missing/duplicate/out-of-order oracle word')
    c = active['tuple']
    for j in range(8):
        i = offset + j
        expected = (((i-32)*37 + c['seed']*71 + 3) & 255
                    if 32+c['start']*c['bytes'] <= i < 32+c['registers']*128 else 91)
        require((value >> (8*j)) & 255 == expected, 'Original all-byte oracle')
    active['reads'].update(range(offset, offset+8))
