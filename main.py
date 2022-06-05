import asyncio
import grpc.aio
import logging

from messages_pb2_grpc import RPCStub
from messages_pb2 import KaspadMessage
from pow import calculate_target
from rpc_pb2 import GetInfoRequestMessage, GetBlockDagInfoRequestMessage, NotifyNewBlockTemplateRequestMessage, GetBlockTemplateRequestMessage

from miner import Miner

MINER_NAME = "kaspy-miner/0.0.1"

async def message_iter(queue: asyncio.Queue, lock: asyncio.Semaphore):
    """
    This generator is used to communicate with the server. All outgoing messages
    are coming from here. Basically, it sends everything it hash in the queue.
    :param queue: queue of messages to send
    :param lock: semaphore preventing sending too many objects without response
    """
    logging.debug("Started sending messages from queue")
    message = await queue.get()
    while message is not None:
        yield message
        queue.task_done()
        # Making sure not to overload server
        await lock.acquire()
        message = await queue.get()
    queue.task_done()
    logging.debug("Queue is over")


async def main(kaspad, address, mine_when_not_synced=False):
    """
    Connects to gRPC and starts the mining process

    """
    logging.basicConfig(level=logging.DEBUG)

    channel = grpc.aio.insecure_channel(kaspad)
    await asyncio.wait_for(channel.channel_ready(), 2)

    stub = RPCStub(channel)
    queue = asyncio.Queue(4)

    miner = Miner(queue)
    miner_task = asyncio.create_task(miner.mine())

    await queue.put(KaspadMessage(getInfoRequest=GetInfoRequestMessage()))
    await queue.put(KaspadMessage(getBlockDagInfoRequest=GetBlockDagInfoRequestMessage()))
    await queue.put(KaspadMessage(notifyNewBlockTemplateRequest=NotifyNewBlockTemplateRequestMessage()))
    await queue.put(KaspadMessage(getBlockTemplateRequest=GetBlockTemplateRequestMessage(payAddress=address, extraData=MINER_NAME)))

    concurrency = asyncio.Semaphore(190)
    async for message in stub.MessageStream(message_iter(queue, concurrency)):
        payload = message.WhichOneof("payload")
        message = getattr(message, message.WhichOneof("payload"))

        # We lock on send, release on receive
        if payload.endswith("Response"):
            concurrency.release()

        if hasattr(message, "error") and message.error.message:
            logging.error("Error from %s: %s", payload, message.error.message)
        elif payload == "getInfoResponse":
            logging.info("Connected to Kaspad version %s", message.serverVersion)
        elif payload == "getBlockDagInfoResponse":
            logging.info("Network %s", message.networkName)
        elif payload == "notifyNewBlockTemplateResponse":
            logging.info("Subscribed to template notifier")

        elif payload == "newBlockTemplateNotification":
            await queue.put(KaspadMessage(getBlockTemplateRequest=GetBlockTemplateRequestMessage(payAddress=address, extraData=MINER_NAME)))
        elif payload == "getBlockTemplateResponse":
            if not mine_when_not_synced and not message.isSynced:
                logging.warning("Kaspad is not synced. Skipping block")
            else:
                logging.info("Current target: %s", hex(calculate_target(message.block.header.bits))[2:].zfill(64))
                await miner.set_work(message.block)
        elif payload == "submitBlockResponse":
            if message.rejectReason != 0:
                logging.error("Block rejected (%s) %s", message.rejectReason, message.error.message)
        else:
            logging.error("Bad response: %s", payload)
            await queue.put(None)
    miner_task.cancel()
    del miner

# asyncio.run(main(
#     kaspad="161.35.157.238:16110",
#     address="kaspa:qz4jdyu04hv4hpyy00pl6trzw4gllnhnwy62xattejv2vaj5r0p5quvns058f"
# ))

asyncio.run(main(
    kaspad="192.168.86.72:16610",
    address="kaspadev:qz4jdyu04hv4hpyy00pl6trzw4gllnhnwy62xattejv2vaj5r0p5qsjkkafj9",
    mine_when_not_synced=True
))