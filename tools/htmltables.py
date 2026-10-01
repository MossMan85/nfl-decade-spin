"""Tiny stdlib HTML table extractor (no bs4 needed)."""
from html.parser import HTMLParser
import html as _html
import re


class _TP(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []      # list of dict(title, rows=[[(text, href, tag)]])
        self.stack = []
        self.cell = None
        self.row = None
        self.last_heading = ""
        self.in_heading = False
        self.heading_buf = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("h1", "h2", "h3", "h4", "caption"):
            self.in_heading = True
            self.heading_buf = []
        if tag == "table":
            self.stack.append({"title": self.last_heading, "rows": [], "cls": a.get("class", "")})
        elif tag == "tr" and self.stack:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = {"text": [], "href": None, "tag": tag, "cls": a.get("class", "")}
        elif tag == "a" and self.cell is not None and self.cell["href"] is None:
            self.cell["href"] = a.get("href")
        elif tag == "br" and self.cell is not None:
            self.cell["text"].append(" ")
        elif tag == "span" and self.cell is not None and "d-none" in (a.get("class") or ""):
            # footballdb repeats an abbreviated name in a hidden span
            self.cell.setdefault("hidden_depth", 0)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in ("h1", "h2", "h3", "h4", "caption") and self.in_heading:
            self.in_heading = False
            t = re.sub(r"\s+", " ", "".join(self.heading_buf)).strip()
            if t:
                self.last_heading = t
                if tag == "caption" and self.stack:
                    self.stack[-1]["title"] = t
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            txt = re.sub(r"\s+", " ", "".join(self.cell["text"])).strip()
            self.row.append((txt, self.cell["href"], self.cell["tag"], self.cell["cls"]))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.stack:
            if self.row:
                self.stack[-1]["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.stack:
            self.tables.append(self.stack.pop())

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_heading:
            self.heading_buf.append(data)
        if self.cell is not None:
            self.cell["text"].append(data)


def tables(raw: str):
    p = _TP()
    p.feed(raw)
    return p.tables
