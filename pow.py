from hashlib import blake2b
from keccak import Keccak
import struct
import numpy as np
import cbitstruct as bitstruct
from rpc_pb2 import RpcBlockHeader
from itertools import islice

BITSTRUCT_MATRIX_PACK = "<" + "u64"*256
BITSTRUCT_MATRIX_UNPACK = "<" + "u4"*4096
BITSTRUCT_VECTOR = ">" + "u4"*64

POW_HEADER = struct.pack("<136s", b"\x01\x88\x01\x00\x01\x78ProofOfWorkHash")
HEAVY_HEADER = struct.pack("<136s", b"\x01\x88\x01\x00\x01\x48HeavyHash")

class Xoshiro256PlusPlus(object):
    def __init__(self, state):
        self.state = [x for x in state]

    @staticmethod
    def _rotl(x, k):
        return ((x << k) & 0xFFFFFFFFFFFFFFFF) | (x >> (64 - k))

    def __next__(self):
        result = (self._rotl((self.state[0] + self.state[3]) & 0xFFFFFFFFFFFFFFFF, 23) + self.state[0]) & 0xFFFFFFFFFFFFFFFF

        t = (self.state[1] << 17) & 0xFFFFFFFFFFFFFFFF

        self.state[2] ^= self.state[0]
        self.state[3] ^= self.state[1]
        self.state[1] ^= self.state[2]
        self.state[0] ^= self.state[3]

        self.state[2] ^= t
        self.state[3] = self._rotl(self.state[3], 45)

        return int(result)

    def __iter__(self):
        return self


def calculate_target(bits):
    unshifted_expt = bits >> 24
    if unshifted_expt <= 3:
        mant = (bits & 0xFFFFFF) >> (8 * (3 - unshifted_expt))
        expt = 0
    else:
        mant = bits & 0xFFFFFF
        expt = 8 * ((bits >> 24) - 3)
    return mant << expt


def cast_to_4bit_matrix(buffer):
    return np.array(bitstruct.unpack(BITSTRUCT_MATRIX_UNPACK, buffer), dtype="uint16").reshape(64, 64)


def generate_matrix(header_hash: bytes):
    xoshiro = Xoshiro256PlusPlus(struct.unpack("<4Q", header_hash))

    buffer = bitstruct.pack(BITSTRUCT_MATRIX_PACK, *islice(xoshiro, 256))
    matrix = cast_to_4bit_matrix(buffer)
    while np.linalg.matrix_rank(matrix) < 64:
        buffer = bitstruct.pack(BITSTRUCT_MATRIX_PACK, *islice(xoshiro, 256))
        matrix = cast_to_4bit_matrix(buffer)
    return matrix

def calculate_hash(header: RpcBlockHeader, nonce):
    header_hash = serialize_header(header, True)
    return _calculate_hash(header_hash, generate_matrix(header_hash), header.timestamp, nonce)

def _calculate_hash(header_hash, matrix, timestamp, nonce):
    to_hash = struct.pack("<32sQ32xQ", header_hash, timestamp, nonce)

    # Keccak returns little endian
    pow_hash = Keccak(1088, 512, POW_HEADER + to_hash, 0x04, 32)

    matmul = np.right_shift(np.matmul(matrix, np.array(bitstruct.unpack(BITSTRUCT_VECTOR, pow_hash), dtype="uint16"), dtype="uint16"), 10, dtype="uint16")
    xored = bytes(a^b for (a,b) in zip(pow_hash, bitstruct.pack(BITSTRUCT_VECTOR, *map(int, matmul))))

    # Keccak returns little endian
    heavy_hash = Keccak(1088, 512, HEAVY_HEADER + xored, 0x04, 32)
    return heavy_hash[::-1]


def serialize_header(header: RpcBlockHeader, for_pre_pow: bool=True):
    hasher = blake2b(digest_size=32, key=b"BlockHash")
    (nonce, timestamp) = (0,0) if for_pre_pow else (header.nonce, header.timestamp)

    hasher.update(struct.pack("<HQ", header.version, len(header.parents)))
    for parent in header.parents:
        hasher.update(struct.pack("<Q", len(parent.parentHashes)))
        for parent_hash in parent.parentHashes:
            hasher.update(bytes.fromhex(parent_hash))
    hasher.update(bytes.fromhex(header.hashMerkleRoot))
    hasher.update(bytes.fromhex(header.acceptedIdMerkleRoot))
    hasher.update(bytes.fromhex(header.utxoCommitment))
    hasher.update(struct.pack("<QIQQQ", timestamp, header.bits, nonce, header.daaScore, header.blueScore))


    blue_work = header.blueWork
    blue_work_len = (len(blue_work) + 1) // 2
    #TODO: blue work
    hasher.update(struct.pack("<Q", blue_work_len))
    if len(blue_work) % 2 == 1:
        blue_work = "0" + blue_work
    hasher.update(bytes.fromhex(blue_work))

    hasher.update(bytes.fromhex(header.pruningPoint))
    return hasher.digest()