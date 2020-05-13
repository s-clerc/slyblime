from ..sexpdata import *
from typing import Dict, Any, List, Tuple, Optional
from .types import *
from ..pydispatch import Dispatcher

import queue

from . import types

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
                "server_side_repl_close",
                "unknown"]

    def __init__(self, channel, send_events=False):
        self.channel = channel
        self.is_open = self.channel.is_open
        channel.bind(message_recieved=self.on_message)
        self.queue = queue.SimpleQueue()
        self.send_events = send_events
        self.read_mode = False

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
        elif command == "set-read-mode":
            if data[1].lower() == ":read":
                self.read_mode = True
            else:
                self.read_mode = False
        command = command.replace("-", "_")
        if command in self._events_:
            self.emit(command, *data[1:])
        else:
            print(f"unknown event {command}")
            self.emit("unknown", *data)

    def process(self, input):
        if not self.read_mode:
            input = input.strip() # Remove trailing whitespace for whatever reason
        self.channel.send_message(f"(:PROCESS {dumps(input)})")


def parse_symbol(key, lower_keys=True, remove_colon_from_keyword=True, replace_dash_with_underscore=True):
    key = str(key)
    if remove_colon_from_keyword and key[0] == ":":
        key = key[1:]
    if replace_dash_with_underscore:
        key = key.replace("-", "_")
    return key.lower() if lower_keys else key

def property_list_to_dict(plist, *args):
    return {parse_symbol(key, *args): value 
            for key, value in zip(plist[::2], plist[1::2])}

def association_list_to_dict(alist, preserve_list=False, *args):
    return {parse_symbol(values[0], *args): (values[1:] if preserve_list else values[1])
            for values in alist}

  # Slynk data parsing
def parse_position(raw_position):
    position = Position(raw_position[0][1:].lower())

    if position.type == "position":
        position.offset = raw_position[1]
    elif position.type == "offset":
        position.type = "position"
        position.offset = raw_position[1] + raw_position[2]
    elif position.type == "line":
        position.line = raw_position[1]
        if len(raw_position) >= 3:
            position.column = raw_position[2]
    elif position.type == "function-name":
        position.function = raw_position[1]
    elif position.type == "source-path":
        # Both r_p[1] and r_p[2] MAY be symbols and not str as assumed
        position.source_path_list = raw_position[1] if type(raw_position[1]) == list else []
        position.source_path_start = raw_position[2]
    elif position.type == "method":
        # The following MAY be symbols !!
        position.method_name = raw_position[1]
        position.specialisers = raw_position[2] if type(raw_position[2]) == list else []
        position.qualifiers = raw_position[3:]

    return position


def parse_location(raw_location):
    data = Location()

    # symbexp of form (:ERROR <message>)
    if str(raw_location[0]).upper() == ":ERROR":
        data.buffer_type = "error"
        data.error = str(raw_location[1])
        return data
    # symbexp of form (:LOCATION <buffer> <position> <hints>)
    raw_buffer = raw_location[1]
    data.buffer_type = raw_buffer[0][1:].lower()
    buffer_type = data.buffer_type
    second = str(raw_buffer[1])
    third = str(raw_buffer[2])
    # Parse type
    if buffer_type == "file":
        data.file = second
    elif buffer_type == "buffer":
        data.buffer_name = second
    elif buffer_type == "buffer-and-file":
        data.buffer_name = second
        data.file = third
    elif buffer_type == "source-from":
        data.source_form = second
    elif data.buffer_type == "zip":
        data.zip_file = second
        data.zip_entry = third

    data.position = self.parse_position(raw_location[2])
    data.hints = raw_location[3:]
    return data


def parse_compilation_information(expression):
    def parse_compilation_note(expression):
        note = property_list_to_dict(expression)
        note["location"] = association_list_to_dict(note["location"][1:])
        note["severity"] = str(note["severity"])
        return CompilationNote(**note)

    return CompilationResult(
        notes=[parse_compilation_note(note) for note in expression[1]],
        success=True if expression[2] else False,
        duration=expression[3] if expression[3] else None,
        load=True if expression[4] else False,
        path=expression[5] if expression[5] else None)

def parse_inspection(inspection):
    def parse_element(element):
        if type(element) == list:
            return DictAsObject(
                # Remove colon from keyword
                {"type": element[0][1:],
                 "content": element[1],
                 "index": element[2],
                 # Primarily for debugging purposes
                 "original_content": element})
        return element

    inspection = property_list_to_dict(inspection)
    inspection["content_specifiers"] = inspection["content"][1:]
    inspection = DictAsObject(inspection)
    inspection.content = [parse_element(element) for element in inspection.content[0]]
    return inspection

def _extract_properties(expression):
    thread = str(expression[1])
    tag = str(expression[2])
    return thread, tag


def _extract_question_properties(expression):
    thread, tag = _extract_properties(expression)
    prompt = str(expression[3])
    initial_value = expression[4] if len(expression) > 4 and expression[4] else ""
    return thread, tag, prompt, initial_value