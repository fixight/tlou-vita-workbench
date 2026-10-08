"""Read unencrypted PSARC archives; validate every decoded block length."""
import struct
import zlib
from pathlib import Path


class Psarc:
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as stream:
            magic, version, codec, toc, stride, count, self.block_size, flags = struct.unpack('>4sI4s5I', stream.read(32))
            if magic != b'PSAR' or codec != b'zlib' or stride != 30 or flags & 4:
                raise ValueError('Unsupported PSARC header')
            rows = stream.read(count * stride)
            self.entries = [(int.from_bytes(rows[i+16:i+20], 'big'),
                             int.from_bytes(rows[i+20:i+25], 'big'),
                             int.from_bytes(rows[i+25:i+30], 'big'))
                            for i in range(0, len(rows), stride)]
            width = max(1, (self.block_size.bit_length()-1+7)//8)
            raw = stream.read(toc - 32 - count*stride)
            if len(raw) % width:
                raise ValueError('Invalid PSARC block table')
            self.sizes = [int.from_bytes(raw[i:i+width], 'big') or self.block_size
                          for i in range(0, len(raw), width)]
        names = self.read_index(0).decode('utf-8').splitlines()
        if len(names) != count-1:
            raise ValueError('PSARC name count mismatch')
        self.names = {name: i for i, name in enumerate(names, 1)}

    def read_index(self, index):
        block, length, offset = self.entries[index]
        output = bytearray()
        with self.path.open('rb') as stream:
            stream.seek(offset)
            while len(output) < length:
                size = self.sizes[block]
                data = stream.read(size)
                expected = min(self.block_size, length-len(output))
                decoded = data if size == expected else zlib.decompress(data)
                if len(decoded) != expected:
                    raise ValueError('PSARC block size mismatch')
                output.extend(decoded)
                block += 1
        return bytes(output)

    def read(self, name):
        return self.read_index(self.names[name])
