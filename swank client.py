from typing import Dict, Any

from pydispatch import Dispatcher

# import socket
# import asyncore
# from promise import Promise
import asyncio
from hy.lex import hy_parse
from sexpdata import loads
from collections import namedtuple
from queue import Queue
import threading

DebugEventData = namedtuple("DebugEventData",
                            ["thread",
                             "level",
                             "title",
                             "type",
                             "restarts",
                             "stack_frames"],
                            defaults=(None,) * 6)

PromisedRequest = namedtuple("RequestData",
                             ["id",
                              "command",
                              "package",
                              "future"])


class SwankClientProtocol(Dispatcher, asyncio.Protocol):
    _events_ = [
        "reception",
        "connect",
        "disconnect"
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.partial_message = None

    def connection_made(self, transport):
        self.transport = transport
        self.emit("connect")

    def connection_lost(self, something):
        self.emit("disconnect", something)

    def complete_data(self, data):
        if self.partial_message is None:
            packet_size = int(data[0:6].decode("utf-8"), 16)
            if len(data)-6 < packet_size:
                self.partial_message = data
                return None
            else:  # Data is already complete
                return data
        else:
            self.partial_message += data
            packet_size = int(self.partial_message[0:6].decode("utf-8"), 16)
            if len(self.partial_message)-6 < packet_size:
                return None
            else:  # Data is finally complete
                data = self.partial_message
                self.partial_message = None
                return data

    def data_received(self, data):
        data = self.complete_data(data)
        if (data is None): return
        packet_size = int(data[0:6].decode("utf-8"), 16)
        print(data)
        self.emit("reception", data[6:packet_size + 6])

        remainder = data[packet_size + 6:]
        if len(remainder) > 5:  # sanity check
            print("Remainder: ")
            print(remainder)
            self.data_received(remainder)
        elif len(remainder) > 0:
            print("Erroneous remainder of ")
            print(remainder)

    def write(self, message):
        output = message.encode("utf-8")
        length = str(hex(len(output)))[2:].zfill(6).upper()
        buffer = length.encode("utf-8") + output #+ "\n".encode("utf-8")
        self.transport.write(buffer)
        print(buffer)


class SwankClient(Dispatcher):
    request_table: Dict[int, PromisedRequest]
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
        self.connexion = None
        self.connected = False
        self.request_counter = 1
        self.request_table = {}
        self.output_buffer = "".encode("utf-8")
        self.rex_queue = Queue()
        self.loop = None
        # setup_read(6, header_complete_callback)

    async def connect(self, *args):
        if len(args) > 0:
            self.loop = args[0]
        else:
            self.loop = asyncio.new_event_loop()
            threading.Thread(target=self.loop.run_forever)
        self.connexion = SwankClientProtocol()
        self.connexion.bind(connect=self.handle_connect,
                            disconnect=self.handle_close,
                            reception=self.handle_read)
        await self.loop.create_connection(lambda: self.connexion,
                                          self.host, self.port)
        self.closed_future = self.loop.create_future()

    async def closed(self):
        await self.closed_future
        return self.closed_future.result()

    def setup_read(self, length, callback):
        pass

    def data_complete_callback(self, data):
        pass

    def header_complete_callback(self, data):
        pass

    def send_message(self, message):
        self.connexion.write(message)

    def handle_connect(self):
        self.connected = True
        self.emit("connect")

    def handle_close(self, something):
        if self.connected:
            self.connected = False
            self.closed_future.set_result(True)
            self.emit("disconnect")

    def handle_read(self, data):
        print(data)
        expression = loads(data.decode("utf-8"))
        command = str(expression[0]).lower()[1:]  # This should be a keyword symbol
        if command == "return":
            print("return reception")
            self.rex_return_handler(expression)
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

    def ping_handler(self, expression):
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

    async def debug_invoke_restart(self, level, restart, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        command = "SWANK:INVOKE-NTH-RESTART-FOR-EMACS " + str(level) \
                  + " " + str(restart)
        result = await self.rex(command, thread, package)
        return result

    async def debug_escape_all(self, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        result = await self.rex("SWANK:THROW-TO-TOPLEVEL", thread, package)
        return result

    async def debug_continue(self, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        result = await self.rex("SWANK:SLDB-CONTINUE", thread, package)
        return result

    async def debug_abort_current_level(self, level, thread, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        if level == 1:
            result = await self.debug_escape_all(thread, package)
        else:
            result = await self.rex("SWANK:SLDB-ABORT", thread, package)
        return result

    async def rex(self, command, thread, *args):
        print("do rex")
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        id = self.request_counter
        self.request_counter += 1
        message = "(:EMACS-REX (" + command + ") \"" + package + "\" " + str(thread) + " " + str(id) + ")"
        self.send_message(message)
        # This future will be returned when emacs returns.
        future = self.loop.create_future()
        request = PromisedRequest(id, command, package, future)
        self.request_table[request.id] = request
        await future
        return future.result()

    def rex_return_handler(self, expression):
        status = str(expression[1][0]).lower()
        return_value = expression[1][1]
        id = int(expression[2])
        if id in self.request_table:
            request = self.request_table[id]
            print("Promise fulfilled for" + str(request))
            del self.request_table[id]
            if request.future.cancelled(): return
            request.future.set_result(return_value)
        else:
            print(str(self.request_table))
            print(f"Danger, recieved rex response for unknown command id {id}")

    async def eval(self, expression_string, *args):
        package = args[0] if len(args) > 0 else "COMMON-LISP-USER"
        command = "SWANK-REPL:LISTENER-EVAL " + expression_string
        result = await self.rex(command, ":REPL-THREAD", package)
        return result

    async def prepare_swank(self):
        print("now prep")
        command = "SWANK:SWANK-REQUIRE '(SWANK-IO-PACKAGE::SWANK-TRACE-DIALOG"     \
                                      + " SWANK-IO-PACKAGE::SWANK-PACKAGE-FU"      \
                                      + " SWANK-IO-PACKAGE::SWANK-PRESENTATIONS"   \
                                      + " SWANK-IO-PACKAGE::SWANK-FUZZY"           \
                                      + " SWANK-IO-PACKAGE::SWANK-FANCY-INSPECTOR" \
                                      + " SWANK-IO-PACKAGE::SWANK-C-P-C"           \
                                      + " SWANK-IO-PACKAGE::SWANK-ARGLISTS"        \
                                      + " SWANK-IO-PACKAGE::SWANK-REPL)"
        await self.rex(command, "T")
        print("First done")
        await self.rex("SWANK:INIT-PRESENTATIONS", "T", "COMMON-LISP-USER")
        print("second done")
        await self.rex("SWANK-REPL:CREATE-REPL NIL :CODING-SYSTEM \"utf-8-unix\"", "T", "COMMON-LISP-USER")
        print("third done")
        return


class TestListener():
    def __init__(self, client: SwankClient, loop):
        self.client = client
        self.loop = loop
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
        print(r[len(r) - 1])
        self.loop.create_task(self.client.debug_invoke_restart(self.debug_data.level, len(r) - 1, self.debug_data.thread))

    def on_debug_return(self, data):
        print("debug R")


async def main(x):
    print("main")
    await x.connect(asyncio.get_event_loop())
    await x.prepare_swank()
    await x.closed()
    # x.eval("(+ 2 2)")


if __name__ == '__main__':
    PYTHONASYNCIODEBUG = 1
    loop = asyncio.new_event_loop()
    x = SwankClient("localhost", 4005)
    y = TestListener(x, loop)
    loop.create_task(main(x))
    threading.Thread(target=loop.run_forever).start()
    print("Anyways")
