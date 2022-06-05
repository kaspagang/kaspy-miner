import asyncio
import logging
import time
from os import urandom
import struct

from messages_pb2 import KaspadMessage
from pow import calculate_target, calculate_hash, serialize_header, Xoshiro256PlusPlus, _calculate_hash, generate_matrix
from rpc_pb2 import SubmitBlockRequestMessage


class Miner(object):

    def __init__(self, grpc_queue):
        """
        Manages the mining process
        :param grpc_queue: the queue used to submit blocks
        """
        self.work_event = asyncio.Event()
        self.work_lock = asyncio.Lock()
        self.rand = iter(Xoshiro256PlusPlus(struct.unpack(">4Q", urandom(32))))

        self.hashrate_lock = asyncio.Lock()
        self.hashes = 0
        self.last_time = time.time()

        self.grpc_queue = grpc_queue

        self.current_block = None
        self.current_pow_header = None
        self.current_timestamp = None
        self.current_matrix = None

        self.target = None

        self.logging_task = asyncio.create_task(self.report_hashrate())

    def __del__(self):
        self.logging_task.cancel()

    async def set_work(self, block):
        """
        Changes the current work item to the given block
        """
        await self.work_lock.acquire()
        self.current_block = block
        if block is None:
            self.work_event.clear()
        else:
            self.target = calculate_target(block.header.bits)
            self.current_pow_header = serialize_header(block.header, True)
            self.current_timestamp = block.header.timestamp
            self.current_matrix = generate_matrix(self.current_pow_header)
            self.work_lock.release()
        self.work_event.set()

    async def run_batch(self, batch_size=10):
        """
        Mines a batch. Currently uses python as the engine
        Use this function to implement advanced mines
        """
        for i in range(batch_size):
            nonce = next(self.rand)

            value = int(_calculate_hash(self.current_pow_header, self.current_matrix, self.current_timestamp, nonce).hex(), 16)
            if value < self.target:
                self.current_block.header.nonce = nonce
                await self.grpc_queue.put(KaspadMessage(submitBlockRequest=SubmitBlockRequestMessage(block=self.current_block, allowNonDAABlocks=False)))
                logging.info("Found block %s!", serialize_header(self.current_block.header, False).hex())

                await self.hashrate_lock.acquire()
                self.hashes += i
                self.hashrate_lock.release()
                self.work_event.clear()
                return
        await self.hashrate_lock.acquire()
        self.hashes += batch_size
        self.hashrate_lock.release()

    async def mine(self):
        """
        Runs the mining process, while explicitly allowing other tasks to run
        :return:
        """
        try:
            while True:
                await self.work_event.wait()
                await self.work_lock.acquire()
                await self.run_batch()
                self.work_lock.release()
                await asyncio.sleep(0)
        except Exception:
            logging.exception("Error while mining")
            self.logging_task.cancel()
            await self.grpc_queue.put(None)
            await asyncio.sleep(0)

    async def report_hashrate(self):
        """
        Task to report the hash rate. Runs concurrently
        """
        while True:
            try:
                await asyncio.sleep(10)
                await self.hashrate_lock.acquire()
                current = time.time()
                if current > self.last_time:
                    rate = self.hashes / (current - self.last_time)
                    self.hashes = 0
                    self.last_time = current
                self.hashrate_lock.release()
                logging.info("Hashrate: %.02f H/s", rate)

            except Exception as e:
                print(e)
