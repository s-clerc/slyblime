from pydispatch import Dispatcher

import socket

import asyncore

from hy.lex import hy_parse
from collections import namedtuple

DebugEventData = namedtuple("DebugEventData",
                            ["thread",
                             "level",
                             "title",
                             "type",
                             "restarts",
                             "stack_frames"],
                            defaults=(None,) * 6)

RequestData = namedtuple("RequestData",
                         ["id",
                          "command",
                          "package"])


class SwankClient(Dispatcher, asyncore.dispatcher):
    _events_ = [
        "connect",
        "print_string",
        "presentation_start",
        "presentation_end",
        "new_package",
        "debug_activate",
        "debug_setup",
        "debug_return",
        "read_from_minibuffer",
        "y_or_n_p",
        "read_string",
        "read_aborted",
        "profile_command_complete",
        "disconnect"
    ]

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.request_counter = 1
        self.request_table = {}
        self.output_buffer = "".encode("utf-8")
        asyncore.dispatcher.__init__(self)
        # setup_read(6, header_complete_callback)

    def connect(self):
        self.create_socket()
        asyncore.dispatcher.connect(self, (self.host, self.port))

    def setup_read(self, length, callback):
        pass

    def data_complete_callback(self, data):
        pass

    def header_complete_callback(self, data):
        pass

    def send_message(self, message):
        output = message.encode("utf-8")
        length = str(hex(len(message)))[2:].zfill(6)
        self.output_buffer = length.encode("utf-8") + output + "\n".encode("utf-8")
        print(self.output_buffer)

    ## Asyncore stuff
    def handle_connect(self):
        self.connected = True
        self.emit("connect")

    def handle_close(self):
        if (self.connected):
            self.connected = False
            self.close()
            self.emit("disconnect")

    def handle_read(self):
        received = self.recv(8192).decode("utf-8")
        print(received)
        abstract_syntax_tree = hy_parse(received[6:])
        if len(abstract_syntax_tree) < 2: return
        expression = abstract_syntax_tree[1]
        command = str(expression[0]).lower()[1:]  # This should be a keyword symbol
        if command == "return":
            pass
        elif command == "debug":
            self.debug_setup_handler(expression)
        elif command == "debug-activate":
            self.debug_activate_handler(expression)
        elif command == "debug-return":
            self.debug_return_handler(expression)
        elif command == "ping":
            self.ping_handler(expression)
        else:
            print("Danger, unknown command: " + command)

    def handle_write(self):
        sent_length = self.send(self.output_buffer)
        self.output_buffer = self.output_buffer[sent_length:]

    def ping_handler (self, expression):
        self.send_message("(:EMACS-PONG " + str(expression[1]) + " " + str(expression[2]) + ")")
    ### Debugging stuff
    def debug_setup_handler(self, expression):
        restartablility = lambda frame: bool(frame[2][1]) if len(frame) >= 3 else False
        data = DebugEventData(
            int(expression[1]),  # Thread
            int(expression[2]),  # Level
            str(expression[3][0]),  # Title
            str(expression[3][1]),  # Type
            # Restarts
            [(str(restart[0]), str(restart[1])) for restart in expression[4]],
            # Stack frames
            [(int(frame[0]), str(frame[1]), restartablility(frame)) for frame in expression[5]]
        )
        self.emit("debug_setup", data)

    def debug_activate_handler(self, expression):
        self.emit("debug_activate", DebugEventData(
            int(expression[1]),
            int(expression[2])
        ))

    def debug_return_handler(self, expression):
        self.emit("debug_return", DebugEventData(
            int(expression[1]),
            int(expression[2])
        ))

    def debug_invoke_restart(self, level, restart, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        command = "SWANK:INVOKE-NTH-RESTART-FOR-EMACS " + str(level) \
                  + " " + str(restart)
        return self.rex(command, thread, package)

    def debug_escape_all(self, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        return self.rex("SWANK:THROW-TO-TOPLEVEL", thread, package)

    def debug_continue(self, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        return self.rex("SWANK:SLDB-CONTINUE", thread, package)

    def debug_abort_current_level(self, level, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        if level == 1:
            return self.debug_escape_all(thread, package)
        else:
            return self.rex("SWANK:SLDB-ABORT", thread, package)

    def rex(self, command, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        request = RequestData(self.request_counter, command, package)
        message = "(:EMACS-REX (" + command + ") \"" + package + "\" " + str(thread) + " " + str(self.request_counter) + ")"
        self.send_message(message)
        self.request_counter += 1
        self.request_table[request.id] = request

    def eval(self, expression_string, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        command = "SWANK-REPL:LISTENER-EVAL " + expression_string
        return self.rex(command, ":REPL-THREAD", package)

    def prepare_swank (self):
        command = """
            SWANK:SWANK-REQUIRE '(SWANK-IO-PACKAGE::SWANK-TRACE-DIALOG 
                                  SWANK-IO-PACKAGE::SWANK-PACKAGE-FU
                                  SWANK-IO-PACKAGE::SWANK-PRESENTATIONS
                                  SWANK-IO-PACKAGE::SWANK-FUZZY
                                  SWANK-IO-PACKAGE::SWANK-FANCY-INSPECTOR
                                  SWANK-IO-PACKAGE::SWANK-C-P-C
                                  SWANK-IO-PACKAGE::SWANK-ARGLISTS
                                  SWANK-IO-PACKAGE::SWANK-REPL)
        """
        self.rex(command, "T")
        self.rex("SWANK:INIT-PRESENTATIONS", "T")


class TestListener():
    def __init__(self, client: SwankClient):
        self.client = client
        client.bind(connect=self.on_connect,
                    disconnect=self.on_disconnect,
                    debug_setup=self.on_debug_setup,
                    debug_activate=self.on_debug_activate,
                    debug_return=self.on_debug_return)

    def on_connect(self):
        print("conneion")

    def on_disconnect(self):
        print("discon")

    def on_debug_setup(self, data):
        print("Debug s")
        self.debug_data = data

    def on_debug_activate(self, data):
        print("debug A")
        r = self.debug_data.restarts
        print(r[len(r)-1])
        self.client.debug_invoke_restart(self.debug_data.level, len(r)-1, self.debug_data.thread)

    def on_debug_return(self, data):
        print("debug R")


if __name__ == '__main__':
    x = SwankClient("localhost", 4005)
    y = TestListener(x)
    x.connect()
    x.prepare_swank()
    #x.eval("(+ 2 2)")
    asyncore.loop()
