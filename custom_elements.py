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

class RenamedSpan(BaseHtmlElement):
    def __str__(self):
        previous = self.name
        self.name = "span"
        result = super().__str__()
        self.name = previous
        return result

class Details(BaseHtmlElement):
    def __str__(self):
        if "open" in self.attributes:
            element = DIV(**self.attributes)
            element += self
            print("aoeu", element)
            return str(element)
        else:
            return str(DIV(**self.attributes)[
                self[0] if (len(self) > 0 and isinstance(self[0], BaseHtmlElement) 
                                          and "SUMMARY" in self[0].name.upper()) 
                        else ""
            ])
BUTTON = Button("x:button")
CHECKBOX = Checkbox("x:checkbox")
DETAILS = Details("x:details")
SUMMARY = RenamedSpan("x:summary")