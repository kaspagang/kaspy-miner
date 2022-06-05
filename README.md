# Running

Make sure you have all requirements by running
```commandline
pip install -r requirements.txt
```

Edit `main.py` and set your address and the kaspad you want to connect to and then just run
```commandline
python main.py
```

# Structure

* `miner.py` - contains the miner logic (how much time to spend on each work item, when to switch, how to generate 
               nonces). Calling HW devices would be done from here
* `pow.py` - the nitty gritty of the proof of work details
* `main.py` - in charge of communication with node and sending work to the miner

### Third Party
* `keccak.py` - python implementation of keccak taken from the offical group (could be optimized)

### GRPC

* `*_pb2.py` - Auto generated. Contains definitions of the protobuf object
* `*_pb2_grpc.py` - Auto generated. Contains definitnions of teh grpc client.

# Developing

## Regenerating gRPC Client

After downloading the required `.proto` files to the `protos` directory
run
```commandline
python -m grpc_tools.protoc -I./protos --python_out=. ./protos/rpc.proto      
python -m grpc_tools.protoc -I./protos --python_out=. ./protos/p2p.proto
python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=. ./protos/messages.proto
```

## Resources

* [Using gRPC](https://grpc.io/docs/languages/python/basics/#bidirectional-streaming-rpc-1)
* [Bitstruct](https://bitstruct.readthedocs.io/en/latest/)