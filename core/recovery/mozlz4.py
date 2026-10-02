"""Minimal pure-Python LZ4 *block* decompressor + Mozilla `mozLz40` container
reader (Firefox session store, bookmark backups, search.json.mozlz4, ...).
Bounds-checked and output-capped: hostile/corrupt input raises ValueError,
never hangs or exhausts memory."""
from __future__ import annotations

import struct

MAGIC = b"mozLz40\x00"
MAX_OUTPUT = 128 * 1024 * 1024


def lz4_block_decompress(src: bytes, out_size: int) -> bytes:
    if out_size < 0 or out_size > MAX_OUTPUT:
        raise ValueError("Declared decompressed size is out of range.")
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                if i >= n:
                    raise ValueError("Truncated literal length.")
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        if i + lit > n:
            raise ValueError("Literal run exceeds input.")
        out += src[i:i + lit]
        i += lit
        if len(out) > out_size:
            raise ValueError("Output exceeds declared size.")
        if i >= n:
            break  # last sequence has literals only
        if i + 2 > n:
            raise ValueError("Truncated match offset.")
        off = src[i] | (src[i + 1] << 8)
        i += 2
        if off == 0 or off > len(out):
            raise ValueError("Invalid match offset.")
        mlen = token & 0x0F
        if mlen == 15:
            while True:
                if i >= n:
                    raise ValueError("Truncated match length.")
                b = src[i]
                i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        if len(out) + mlen > out_size:
            raise ValueError("Output exceeds declared size.")
        start = len(out) - off
        if off >= mlen:
            out += out[start:start + mlen]
        else:  # overlapping copy
            for k in range(mlen):
                out.append(out[start + k])
    if len(out) != out_size:
        raise ValueError("Decompressed size mismatch.")
    return bytes(out)


def read_mozlz4(path) -> bytes:
    with open(path, "rb") as fh:
        data = fh.read(MAX_OUTPUT // 2)
    if not data.startswith(MAGIC) or len(data) < 12:
        raise ValueError("Not a mozLz4 file.")
    (size,) = struct.unpack("<I", data[8:12])
    return lz4_block_decompress(data[12:], size)
