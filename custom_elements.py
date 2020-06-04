from .html_dsl.elements import *

class Button(BaseHtmlElement):
    def __str__(self):
        href = self.attributes["href"] if "href" in self.attributes else ""
        if "class" not in self.attributes:
            self.attributes["class"] = ""
        self.attributes["class"] += "sly button"
        return str(SPAN(**self.attributes)[
            A(href=href)[[child for child in self]]
        ])


class Checkbox(BaseHtmlElement):
    def __str__(self):
        href = self.attributes["href"] if "href" in self.attributes else ""
        if "class" not in self.attributes:
            self.attributes["class"] = ""
        self.attributes["class"] += "sly checkbox"
        is_checked = ("checked" in self.attributes) and self.attributes["checked"]
        if is_checked:
            self.attributes["class"] += " checked"
        return str(
            A(**self.attributes)[
                SPAN["✓" if is_checked else "&nbsp;"]
        ])

BUTTON = Button("x:button")
CHECKBOX = Checkbox("x:checkbox")