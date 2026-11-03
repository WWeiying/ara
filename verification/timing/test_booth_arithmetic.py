"""Check the proposed packed Booth identities before RTL simulation.

This is an arithmetic design check, not a replacement for VCS or equivalence.
"""
import random
import unittest


def booth_product(a, b, n, signed_a, signed_b):
    mask = (1 << (2*n)) - 1
    word_mask = (1 << (n+2)) - 1
    ax = a - ((1 << n) if signed_a and a >> (n-1) else 0)
    total = 0
    bias = 0
    for q in range(0, n, 2):
        prev = (b >> (q-1)) & 1 if q else 0
        middle = (b >> q) & 1
        negative = (b >> (q+1)) & 1
        one = middle ^ prev
        two = (not (middle ^ prev)) and (negative ^ middle)
        magnitude = (ax if one else 0) | ((ax << 1) if two else 0)
        # Complement negative rows, flip their sign bit, add the row's +1
        # separately, and compensate sign-bit flips with a constant bias.
        word = (magnitude ^ (-negative) ^ (1 << (n+1))) & word_mask
        total += (word + negative) << q
        bias -= 1 << (n+1+q)
    if not signed_b and b >> (n-1):
        total += a << n
    return (total + bias) & mask


class BoothArithmeticTests(unittest.TestCase):
    def test_arithmetic_compressors(self):
        for a in (0,1):
            for b in (0,1):
                self.assertEqual(a+b, ((a&b)<<1) | (a^b))
                for c in (0,1):
                    self.assertEqual(a+b+c, (((a&b)|(a&c)|(b&c))<<1) | (a^b^c))

    def test_early_group_propagate(self):
        for a in range(256):
            for b in range(256):
                self.assertEqual(((a+b)&255)==255, (a^b)==255)
        rng = random.Random(0xCA44)
        for width in (16,32,64):
            mask = (1 << width)-1
            for _ in range(10000):
                a,b = rng.getrandbits(width),rng.getrandbits(width)
                for x,y in ((a,b),(a,a^mask)):
                    self.assertEqual(((x+y)&mask)==mask, (x^y)==mask)

    def test_sparse_partitioned_prefix(self):
        rng = random.Random(0xADD4)
        mask128 = (1 << 128)-1
        for width in (16,32,64,128):
            vectors = [(mask128,1), (mask128,mask128), (0,0)]
            vectors += [(mask128 ^ (1 << k), 1 << k) for k in range(128)]
            vectors += [(rng.getrandbits(128), rng.getrandbits(128)) for _ in range(1000)]
            for a,b in vectors:
                bp, bg = a ^ b, a & b
                p, g = [], []
                for k in range(32):
                    x, y = (bp >> (4*k)) & 15, (bg >> (4*k)) & 15
                    p.append(int(x == 15 and (4*k) % width != 0))
                    carry = 0
                    for j in range(4):
                        carry = ((y >> j)&1) | (((x >> j)&1) & carry)
                    g.append(carry)
                for level in range(9):
                    distance = 1 << (level if level < 5 else 8-level)
                    np, ng = p[:], g[:]
                    for k in range(32):
                        join = ((k+1) % (2*distance) == 0) if level < 5 else (
                            k >= 3*distance-1 and (k-(3*distance-1)) % (2*distance) == 0)
                        if join:
                            np[k] = p[k] & p[k-distance]
                            ng[k] = g[k] | (p[k] & g[k-distance])
                    p,g = np,ng
                result = 0
                for k in range(32):
                    carry = g[k-1] if k and (4*k) % width else 0
                    for j in range(4):
                        bit = 4*k+j
                        result |= (((bp >> bit)&1) ^ carry) << bit
                        carry = ((bg >> bit)&1) | (((bp >> bit)&1) & carry)
                mask = (1 << width)-1
                expected = sum(((((a >> k)&mask)+((b >> k)&mask)) & mask) << k
                               for k in range(0,128,width))
                self.assertEqual(result,expected,(width,a,b))

    def check_product(self, a, b, n, sa, sb):
        ax = a - ((1 << n) if sa and a >> (n-1) else 0)
        bx = b - ((1 << n) if sb and b >> (n-1) else 0)
        self.assertEqual(booth_product(a, b, n, sa, sb),
                         (ax*bx) & ((1 << (2*n))-1), (a,b,n,sa,sb))

    def test_exhaustive_byte(self):
        for sa in (0, 1):
            for sb in (0, 1):
                for a in range(256):
                    for b in range(256):
                        self.check_product(a,b,8,sa,sb)

    def test_wide_edges_and_random(self):
        rng = random.Random(0xB004)
        for n in (16,32,64):
            edges = [0,1,(1<<n)-1,(1<<(n-1)),(1<<(n-1))-1]
            for sa in (0,1):
                for sb in (0,1):
                    for a in edges:
                        for b in edges:
                            self.check_product(a,b,n,sa,sb)
                    for _ in range(2000):
                        self.check_product(rng.getrandbits(n),rng.getrandbits(n),n,sa,sb)

    def test_global_row_support(self):
        for n in (8,16,32,64):
            for q in range(0,64,2):
                base = q//n*n
                for k in range(base+q,base+q+n+2):
                    self.assertTrue(q <= k <= q+65 and k < 128)


if __name__ == '__main__':
    unittest.main()
