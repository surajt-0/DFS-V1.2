"""Known-answer + hostile-input tests for the pure-Python LZ4 block decoder."""
import struct

from django.test import SimpleTestCase

from core.recovery.mozlz4 import MAGIC, lz4_block_decompress, read_mozlz4


class Lz4Block(SimpleTestCase):
    def test_literals_only(self):
        self.assertEqual(lz4_block_decompress(b"\x50hello", 5), b"hello")

    def test_match_with_overlap(self):
        # 3 literals "abc", then a 6-byte match at distance 3 (overlapping copy) -> abcabcabc
        block = bytes([0x32]) + b"abc" + b"\x03\x00"
        self.assertEqual(lz4_block_decompress(block, 9), b"abcabcabc")

    def test_long_literal_length_extension(self):
        data = bytes(range(256)) * 2            # 512 literals -> needs length-extension bytes
        ext = 512 - 15
        block = bytes([0xF0]) + bytes([255] * (ext // 255)) + bytes([ext % 255]) + data
        self.assertEqual(lz4_block_decompress(block, 512), data)

    def test_rejects_hostile_input(self):
        for bad, size in [(b"\xf0\xff", 100),              # truncated length run
                          (b"\x11\x00\x00", 100),           # match offset 0
                          (b"\x10a\x09\x00", 100),          # offset beyond output
                          (b"\x50hello", 4),                # output larger than declared
                          (b"\x50hello", 6)]:               # output smaller than declared
            with self.assertRaises(ValueError):
                lz4_block_decompress(bad, size)
        with self.assertRaises(ValueError):
            lz4_block_decompress(b"\x00", 10 ** 12)         # absurd declared size (decompression bomb)

    def test_container_roundtrip_and_bad_magic(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        good = os.path.join(d, "a.jsonlz4")
        with open(good, "wb") as fh:
            fh.write(MAGIC + struct.pack("<I", 5) + b"\x50hello")
        self.assertEqual(read_mozlz4(good), b"hello")
        bad = os.path.join(d, "b.jsonlz4")
        with open(bad, "wb") as fh:
            fh.write(b"notmoz" * 10)
        with self.assertRaises(ValueError):
            read_mozlz4(bad)
