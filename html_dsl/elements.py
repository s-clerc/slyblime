from collections.abc import Iterable
from typing import Any, Optional


def flatten(source: Any):
    # So it doesn't flatten BaseHtmlElements which are lists now
    if isinstance(source, BaseHtmlElement) or isinstance(source, str):
        yield source
    elif isinstance(source, Iterable):
        for element in source:
            yield from flatten(element)
    else:
        yield source


class BaseHtmlElement(list):
    def __init__(self, name: str, single: bool = False, no_content: bool = False):
        self.name = name
        self.attributes: dict = {}
        self.parent: Optional[BaseHtmlElement] = None
        self.single = single
        self.is_created = False
        self.no_content = no_content

    def __call__(self, *args, **attributes) -> "BaseHtmlElement":
        element = type(self)(self.name)
        if "_class" in attributes:
            attributes["class"] = attributes.pop("_class")
        element.attributes.update(attributes)
        element.parent = self.parent
        element.single = self.single
        element.no_content = self.no_content
        if len(args) > 0 and args[0] is None:
            element.is_created = True
            element.no_content = True
        return element

    def __getitem__(self, children) -> "BaseHtmlElement":
        # Allow easy access to child items by further overloading [] syntax
        # Assumes that elements will never be single ints
        if type(children) in [int, slice]:
            return super().__getitem__(children)
        elif self.is_created and type(children) == str:
            return self.get_element_by_id(children)
        element = type(self)(self.name)
        element.attributes.update(self.attributes)
        true_children = list(flatten(children))
        for one in true_children:
            if isinstance(one, BaseHtmlElement):
                one.parent = element
        element.extend(true_children)
        element.single = self.single
        element.no_content = self.no_content
        element.is_created = True
        return element

    def __add__(self, addend):
        if type(addend) == int:
            addend = str(addend)
            
        element = type(self)(self.name)
        element.attributes.update(self.attributes)
        true_children = list(flatten(addend))
        for one in true_children:
            if isinstance(one, BaseHtmlElement):
                one.parent = element
        element.extend(self)
        element.extend(true_children)
        element.single = self.single
        element.no_content = self.no_content
        element.is_created = self.is_created
        return element
        
    @property
    def level(self):
        return self.parent.level + 1 if self.parent else 0

    def __repr__(self):
        blank = "  " * self.level
        attributes = "({})".format(";".join(f"{key}={repr(self.attributes[key])}" for key in self.attributes)) if self.attributes else ""
        children = "\n".join(repr(child) if isinstance(child, BaseHtmlElement) else blank + repr(child) for child in self)
        
        if self.single or self.no_content:
            return f"{blank}{self.name}{attributes}"
        return f"{blank}{self.name}{attributes}[\n{children}]"

    def __str__(self):
        blank = "  " * self.level
        children = "\n".join(str(child) if isinstance(child, BaseHtmlElement) else blank + str(child) for child in self)        
        attributes = " {}".format(" ".join(f"""{key.replace("_", "-")}='{str(self.attributes[key])}'""" for key in self.attributes)) if self.attributes else ""
        if self.single:
            return f"{blank}<{self.name}{attributes}>"
        elif self.no_content:
            return f"{blank}<{self.name}{attributes} \>"
        return f"{blank}<{self.name}{attributes}>{children}{blank}</{self.name}>"

    def get_element_by_id(self, id):
        if self.attributes["id"] == id:
            return self
        for element in self:
            if not isinstance(element, BaseHtmlElement):
                continue
            nested_element = element.get_element_by_id(id)
            if nested_element is not None:
                return nested_element
        return None

    def getElementById(self, *args):
        self.get_element_by_id(*args)
        


A = BaseHtmlElement("a")
ABBR = BaseHtmlElement("abbr")
ADDRESS = BaseHtmlElement("address")
AREA = BaseHtmlElement("area")
ARTICLE = BaseHtmlElement("article")
ASIDE = BaseHtmlElement("aside")
AUDIO = BaseHtmlElement("audio")
B = BaseHtmlElement("b")
BASE = BaseHtmlElement("base")
BLOCKQUOTE = BaseHtmlElement("blockquote")
BODY = BaseHtmlElement("body")
BR = BaseHtmlElement("br", single=True)
BUTTON = BaseHtmlElement("button")
CANVAS = BaseHtmlElement("canvas")
CAPTION = BaseHtmlElement("caption")
CODE = BaseHtmlElement("code")
COL = BaseHtmlElement("col")
COLGROUP = BaseHtmlElement("colgroup")
CONTENT = BaseHtmlElement("content")
DATA = BaseHtmlElement("data")
DATALIST = BaseHtmlElement("datalist")
DD = BaseHtmlElement("dd")
DEL = BaseHtmlElement("del")
DETAILS = BaseHtmlElement("details")
DIALOG = BaseHtmlElement("dialog")
DIR = BaseHtmlElement("dir")
DIV = BaseHtmlElement("div")
DL = BaseHtmlElement("dl")
DT = BaseHtmlElement("dt")
ELEMENT = BaseHtmlElement("element")
EM = BaseHtmlElement("em")
EMBED = BaseHtmlElement("embed")
FIGURE = BaseHtmlElement("figure")
FOOTER = BaseHtmlElement("footer")
FORM = BaseHtmlElement("form")
H1 = BaseHtmlElement("h1")
H2 = BaseHtmlElement("h2")
H3 = BaseHtmlElement("h3")
H4 = BaseHtmlElement("h4")
H5 = BaseHtmlElement("h5")
H6 = BaseHtmlElement("h6")
HEAD = BaseHtmlElement("head")
HGROUP = BaseHtmlElement("hgroup")
HR = BaseHtmlElement("hr")
HTML = BaseHtmlElement("html")
IFRAME = BaseHtmlElement("iframe")
IMG = BaseHtmlElement("img")
INPUT = BaseHtmlElement("input")
INS = BaseHtmlElement("ins")
LABEL = BaseHtmlElement("label")
LEGEND = BaseHtmlElement("legend")
LI = BaseHtmlElement("li")
LINK = BaseHtmlElement("link", no_content=True)
MAIN = BaseHtmlElement("main")
MAP = BaseHtmlElement("map")
MARK = BaseHtmlElement("mark")
MENU = BaseHtmlElement("menu")
MENUITEM = BaseHtmlElement("menuitem")
META = BaseHtmlElement("meta", single=True)
NAV = BaseHtmlElement("nav")
NOSCRIPT = BaseHtmlElement("noscript")
OBJECT = BaseHtmlElement("object")
OL = BaseHtmlElement("ol")
OPTGROUP = BaseHtmlElement("optgroup")
OPTION = BaseHtmlElement("option")
OUTPUT = BaseHtmlElement("output")
P = BaseHtmlElement("p")
PARAM = BaseHtmlElement("param")
PICTURE = BaseHtmlElement("picture")
PRE = BaseHtmlElement("pre")
PROGESS = BaseHtmlElement("progess")
S = BaseHtmlElement("s")
SCRIPT = BaseHtmlElement("script")
SECTION = BaseHtmlElement("section")
SELECT = BaseHtmlElement("select")
SHADOW = BaseHtmlElement("shadow")
SLOT = BaseHtmlElement("slot")
SMALL = BaseHtmlElement("small")
SOURCE = BaseHtmlElement("source")
SPAN = BaseHtmlElement("span")
STRONG = BaseHtmlElement("strong")
STYLE = BaseHtmlElement("style")
SUB = BaseHtmlElement("sub")
SUMMARY = BaseHtmlElement("summary")
TABLE = BaseHtmlElement("table")
TD = BaseHtmlElement("td")
TEMPLATE = BaseHtmlElement("template")
TEXTAREA = BaseHtmlElement("textarea")
TFOOT = BaseHtmlElement("tfoot")
TH = BaseHtmlElement("th")
THEAD = BaseHtmlElement("thead")
TIME = BaseHtmlElement("time")
TITLE = BaseHtmlElement("title")
TR = BaseHtmlElement("tr")
TRACK = BaseHtmlElement("track")
U = BaseHtmlElement("u")
UL = BaseHtmlElement("ul")
VAR = BaseHtmlElement("var")
VIDEO = BaseHtmlElement("video")
