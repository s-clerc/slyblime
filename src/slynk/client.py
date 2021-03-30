import asyncio, threading, pathlib

try:
    from .util import *
except ImportError as e:
    print(f"ImportError encoutered, switching gears in client: {e}")
    from util import *

class SlynkClientProtocol(Dispatcher, asyncio.Protocol):
    _events_ = [
        "reception",
        "connect",
        "disconnect"
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.partial_message = None
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.emit("connect")

    def connection_lost(self, something):
        self.emit("disconnect", something)

    def complete_data(self, data):
        if self.partial_message is None:
            packet_size = int(data[0:6].decode("utf-8"), 16)
            if len(data) - 6 < packet_size:
                self.partial_message = data
                return None
            else:  # Data is already complete
                return data
        else:
            self.partial_message += data
            packet_size = int(self.partial_message[0:6].decode("utf-8"), 16)
            if len(self.partial_message) - 6 < packet_size:
                return None
            else:  # Data is finally complete
                data = self.partial_message
                self.partial_message = None
                return data

    def data_received(self, data):
        data = self.complete_data(data)
        if data is None:
            return
        packet_size = int(data[0:6].decode("utf-8"), 16)
        # print(data)
        self.emit("reception", data[6:packet_size + 6])

        remainder = data[packet_size + 6:]
        if len(remainder) > 5:  # sanity check
            # print("Remainder: ")
            # print(remainder)
            self.data_received(remainder)
        elif len(remainder) > 0:
            print("Erroneous remainder of ")
            print(remainder)

    def write(self, message):
        output = message.encode("utf-8")
        length = str(hex(len(output)))[2:].zfill(6).upper()
        buffer = length.encode("utf-8") + output
        self.transport.write(buffer)
        # print(buffer)