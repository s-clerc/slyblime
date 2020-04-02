from .sexpdata import *
from typing import Dict, Any, List, Tuple, Optional

from .pydispatch import Dispatcher


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

class Repl():
    def __init__(self, channel):
        self.channel = channel
        self.is_open = self.channel.is_open
        channel.bind(message_recieved=self.on_message)

    def on_message(self, data):
        c = data[0].lower()[1:]
        parameters = data[1:]
        if c == "write-values":
            self.write_values(parameters[0])
        elif c == "evaluation-aborted":
            self.print(f"Aborted evaluation for {parameters[0]}")
        elif c == "write-string":
            self.print(parameters[0])
        elif c == "set-read-mode":
            self.print("Read-mode set?? wtf")
        elif c == "prompt":
            self.prompt(parameters)
        elif c == "open-dedicated-output-stream":
            self.print("Attempted to open-dedicated-output-stream ??")
        elif c == "clear-repl-history":
            pass
        elif c == "server-side-repl-close":
            self.print("Closed from serverside")
            self.channel.is_open = False
            self.is_open = False
        else:
            self.print(f"Unknown REPL command {c}")

    def prompt(self, parameters):
        [package, prompt, error_level, *condition] = parameters
        if error_level == 0:
            prompt = f"{prompt}〉"
        else:
            prompt = f"{prompt} ｢{error_level}｣〉"
        s = input(prompt)
        self.process(s)

    def process(self, input):
        self.channel.send_message(f"(:PROCESS {dumps(input)})")

    def print(self, message):
        print(message)

    def write_values(self, results):
        for result in results:
            self.print(result[0])




