"""Independent, untimed host oracle for completed QBS byte-range reads.

Addresses are flat/identity translated. No MMU/PMP eligibility, fault timing,
outstanding ownership or performance prediction is implied. A burst footprint
is the whole aligned AXI transfer span checked by physical_check_bytes_o, not
just useful bytes, distinct physical bus words, or physical wire capacity.
"""
from dataclasses import dataclass

REFERENCE_RTL = 'hardware/src/vlsu/qbs/qbs_read_engine.sv'
REFERENCE_RTL_SHA256 = 'b5686b6cac03788ae0c3e48ccfd1e792b0050df8fdba4f6fe3f6994bfd729a3c'
PAGE_BYTES = 4096
MAX_BURST_BEATS = 256
MAX_RANGE_BYTES = (1 << 16)-1
NATIVE_WEIGHT_BYTES = {'Q4_K': 144, 'Q6_K': 210}
HEADER_BYTES = 16
ACTIVATION_BYTES = 292


def _integer(value, name):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(name+' must be an integer')


def _physical_bytes(physical_bits):
    _integer(physical_bits, 'physical_bits')
    if physical_bits not in (128, 256):
        raise ValueError('physical_bits must be 128 or 256')
    return physical_bits//8


@dataclass(frozen=True)
class PayloadBeat:
    transfer_address: int
    physical_word_address: int
    first_lane: int
    range_offset: int
    payload_bytes: int
    compacted_strb: int
    rlast: bool


@dataclass(frozen=True)
class Burst:
    cursor: int
    range_offset: int
    payload_bytes: int
    physical_bytes: int
    transfer_bytes: int
    first_lane: int
    first_transfer_byte: int
    ar_address: int
    beats: int

    @property
    def ar_size(self):
        return self.transfer_bytes.bit_length()-1

    @property
    def ar_len(self):
        return self.beats-1

    @property
    def footprint_bytes(self):
        return self.beats*self.transfer_bytes

    @property
    def footprint_end(self):
        return self.ar_address+self.footprint_bytes

    def payload_beats(self):
        """Intersect transfer intervals with useful bytes; prefix strobes after compaction."""
        end = self.cursor+self.payload_bytes
        result = []
        for i in range(self.beats):
            transfer = self.ar_address+i*self.transfer_bytes
            left, right = max(transfer, self.cursor), min(transfer+self.transfer_bytes, end)
            count = right-left
            if not 0 < count <= self.transfer_bytes:
                raise ValueError('Invalid burst payload geometry')
            result.append(PayloadBeat(transfer_address=transfer,
                physical_word_address=left//self.physical_bytes*self.physical_bytes,
                first_lane=left % self.physical_bytes, range_offset=self.range_offset+left-self.cursor,
                payload_bytes=count, compacted_strb=(1 << count)-1, rlast=i == self.beats-1))
        return tuple(result)


def plan_range(address, byte_count, *, physical_bits, transfer_bytes):
    """Return exact AR requests and permission footprints, in logical range order.

    transfer_bytes is explicit: 16 for narrow requests on either physical bus;
    32 for wide weights on a 256-bit bus. Smaller powers of two are supported
    solely to match the reader's legal AXI-size domain and burst-limit tests.
    """
    physical = _physical_bytes(physical_bits)
    for name, value in (('address', address), ('byte_count', byte_count), ('transfer_bytes', transfer_bytes)):
        _integer(value, name)
    if not 0 <= address < 1 << 64 or not 1 <= byte_count <= MAX_RANGE_BYTES or address+byte_count > 1 << 64:
        raise ValueError('Invalid/nonrepresentable logical range')
    if not 1 <= transfer_bytes <= physical or transfer_bytes & (transfer_bytes-1):
        raise ValueError('Transfer size must be a power of two no wider than the physical bus')
    cursor, remaining, offset, result = address, byte_count, 0, []
    while remaining:
        lane = cursor % physical
        head = lane % transfer_bytes
        chunk = min(remaining, PAGE_BYTES-cursor % PAGE_BYTES, MAX_BURST_BEATS*transfer_bytes-head)
        beats = (head+chunk+transfer_bytes-1)//transfer_bytes
        result.append(Burst(cursor=cursor, range_offset=offset, payload_bytes=chunk,
                            physical_bytes=physical, transfer_bytes=transfer_bytes,
                            first_lane=lane, first_transfer_byte=head,
                            ar_address=cursor-head, beats=beats))
        cursor += chunk
        offset += chunk
        remaining -= chunk
    return tuple(result)


def qbs_request(role, address, *, physical_bits, profile=None, rows=4, per_range=True):
    """Descriptor/header=16 B, one Q8_K activation=292 B, native R4 weights.

    per_range=False represents legacy fixed-bus-width transfers. In optional
    mode headers/activations remain 16-byte transfers; weights use 16 at 128
    physical bits or 32 at 256 bits. No impossible 32-on-128 request is created.
    """
    physical = _physical_bytes(physical_bits)
    if not isinstance(per_range, bool):
        raise ValueError('per_range must be boolean')
    if role in ('header', 'descriptor'):
        if profile is not None:
            raise ValueError('Only weights take a profile')
        count, transfer = HEADER_BYTES, 16
    elif role == 'activation':
        if profile is not None:
            raise ValueError('Only weights take a profile')
        count, transfer = ACTIVATION_BYTES, 16
    elif role == 'weights':
        _integer(rows, 'rows')
        if profile not in NATIVE_WEIGHT_BYTES or not 1 <= rows <= 4:
            raise ValueError('Expected Q4_K/Q6_K and 1..4 native R4 rows')
        count, transfer = rows*NATIVE_WEIGHT_BYTES[profile], physical
    else:
        raise ValueError('Unknown QBS request role')
    return plan_range(address, count, physical_bits=physical_bits,
                      transfer_bytes=transfer if per_range else physical)


def summarize(bursts):
    """Add paid service per AR, never deduplicate overlapping separate requests."""
    bursts = tuple(bursts)
    return dict(ar_count=len(bursts), r_beats=sum(b.beats for b in bursts),
                payload_bytes=sum(b.payload_bytes for b in bursts),
                footprint_bytes=sum(b.footprint_bytes for b in bursts))
