from dataclasses import dataclass
from typing import *


class DictAsObject(object):
    def __init__(self, dict):
        self.__dict__ = dict
    def __repr__(self):
        return str(self.__class__)[:-1] + "|" + str(self.__dict__)[1:-1] + ">"


@dataclass
class PromisedRequest:
    id: int
    command: str
    package: str
    future: Any


@dataclass
class StackFrameLocal:
    name: str
    id: int
    value: str

@dataclass
class StackFrame:
    index: int
    description: str
    is_restartable: bool
    locals: List[StackFrameLocal] = None
    catch_tags: List[str] = None

@dataclass
class DebugEventData:
    thread: int = None
    level: Any = None
    title: Any = None
    type: Any = None
    restarts: List[Tuple[str, str]] = None
    stack_frames: List[StackFrame] = None


@dataclass
class InspectionData:
    title: str
    id: int
    content: list
    length: int = -1
    start: int = -1
    end: int = -1


@dataclass
class Position:
    type: str
    qualifiers: Optional[list] = None
    specialisers: Optional[list] = None
    offset: Optional[int] = None
    column: Optional[int] = None
    function: Optional[str] = None
    source_path_list: Optional[list] = None


@dataclass
class Location:
    buffer_type: Optional[str] = None
    error: Optional[str] = None
    file: Optional[str] = None
    zip_file: Optional[str] = None
    zip_entry: Optional[str] = None
    position: Optional[Position] = None
    source_form: Optional[str] = None


@dataclass
class Definition:
    label: str
    location: Location


@dataclass
class ConnexionInformation:
    pid: int = None
    style: str = None
    encoding: DictAsObject = None
    lisp_implementation: DictAsObject = None
    machine: DictAsObject = None
    features: List[str] = None
    modules: List[str] = None
    package: str = None
    version: str = None


@dataclass
class Completion:
    name: str
    probability: float
    match_locations: List[List[Union[int, str]]]
    namespaces: List[str]

@dataclass
class CompilationNote:
    message: str = ""
    severity: str = ""
    location: Dict[str, Any] = None
    references: list = None
    source_context: Any = None


@dataclass
class CompilationResult:
    notes: List[CompilationNote]
    success: bool
    duration: float
    load: bool
    path: str
    # type which is always :compilation-result


@dataclass
class Trace:
    id: int
    parent_id: int
    spec: Tuple[str, str] = None
    arguments: List[str] = None
    return_list: List[str] = None
    # Haven't seen any of the properties below actually sent
    depth: int = None
    beginning: Any = None
    end: Any = None
    collapse_button_marker: Any = None
    summary_beginning: Any = None
    children_end: Any = None
    is_collapsed: Any = None
