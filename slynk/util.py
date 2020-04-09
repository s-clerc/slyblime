from ..sexpdata import *
from typing import Dict, Any, List, Tuple, Optional

from ..pydispatch import Dispatcher

import queue

class Channel(Dispatcher):
    _events_ = ["message_recieved"]
    def __init__(self, slynk, id):
        self.slynk = slynk
        self.id = id
        self.is_open = False

    def message_recieved(self, argument):
        self.emit("message_recieved", argument)

    def send_message(self, message):
        self.slynk.send_message(f"(:EMACS-CHANNEL-SEND {str(self.id)} {message})")


class Repl(Dispatcher):
    _events_ = ["write_values",
                "evaluation_aborted",
                "write_string",
                "set_read_mode",
                "prompt",
                "open_dedicated_output_stream",
                "clear_repl_history",
                "server_side_repl_close"]

    def __init__(self, channel, send_events=False):
        self.channel = channel
        self.is_open = self.channel.is_open
        channel.bind(message_recieved=self.on_message)
        self.queue = queue.SimpleQueue()
        self.send_events = send_events

    def play_events(self):
        while not self.queue.empty():
            self.process_message(self.queue.get_nowait())
        self.send_events = True

    def pause_events(self):
        self.send_events = False

    def on_message(self, data):
        if self.send_events:
            self.process_message(data)
        else:
            self.queue.put(data)

    def process_message(self, data):
        command = data[0].lower()[1:]
        if command == "server-side-repl-close":
            self.print("Closed from serverside")
            self.channel.is_open = False
            self.is_open = False
        self.emit(command.replace("-", "_"), *data[1:])

    def process(self, input):
        self.channel.send_message(f"(:PROCESS {dumps(input)})")
        


def property_list_to_dict(plist, lower_keys=True, remove_colon_from_keyword=True):
    def parse_symbol(key):
        nonlocal remove_colon_from_keyword
        nonlocal lower_keys
        key = str(key)
        if remove_colon_from_keyword and key[0] == ":":
            key = key[1:]
        return key.lower()
    return {parse_symbol(key): value 
            for key, value in zip(plist[::2], plist[1::2])}



