"""UUIDv7 generation (RFC 9562).

Python's ``uuid.uuid7`` arrives in 3.14; we are on 3.13, so this small,
dependency-free implementation is used until then (ADR-012).

Layout: 48-bit Unix timestamp in milliseconds, 4-bit version (7), 12 random
bits, 2-bit variant (0b10), 62 random bits. IDs sort by creation time, which
keeps B-tree inserts local; 74 random bits make them impractical to guess.
"""

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10))  # 80 bits, 74 used
    rand_a = rand >> 68  # top 12 bits
    rand_b = rand & ((1 << 62) - 1)  # low 62 bits

    value = (unix_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)
