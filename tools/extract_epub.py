#!/usr/bin/env python3
"""Extract chapter text, page markers and the index from the Westad epub.

Usage: python3 tools/extract_epub.py <path-to-epub> [out_dir=work]

Writes (all gitignored):
  work/text/chNN.txt   plain text per chapter, with [p.N] print-page markers
  work/index.json      index entries: {term, sub, refs: [{ch, page}]}
  work/chapters.json   chapter number, title, first/last page
"""
import json
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

# Book order: intro "World Making" = 0, chapters 1-22, conclusion = 23.
CHAPTER_FILES = {"preface001": 0, **{f"chapter{n:03d}": n for n in range(1, 24)}}


class ChapterText(HTMLParser):
    """Collect paragraph text, turning <a id="page-N"/> into [p.N] markers."""

    BLOCKS = {"p", "h1", "h2", "h3", "li", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.pages = []
        self.headings = []
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        page = re.fullmatch(r"page-(\d+)", attrs.get("id") or "")
        if tag == "a" and page:
            n = int(page.group(1))
            self.pages.append(n)
            self.parts.append(f"[p.{n}]")
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "h1":
            self._in_h1 = True
            self.headings.append("")

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        self.parts.append(data)
        if self._in_h1:
            self.headings[-1] += data

    def text(self):
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln) + "\n"


class IndexParser(HTMLParser):
    """Parse primaryie/secondaryie paragraphs and their chapter page links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries = []
        self._cur = None
        self._primary = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "p" and cls.startswith(("primaryie", "secondaryie")):
            self._cur = {"level": 1 if cls.startswith("primaryie") else 2, "text": "", "refs": []}
        elif tag == "a" and self._cur is not None:
            m = re.match(r"(chapter\d{3}|preface001)\.xhtml#page-(\d+)", attrs.get("href", ""))
            if m and m.group(1) in CHAPTER_FILES:
                self._cur["refs"].append({"ch": CHAPTER_FILES[m.group(1)], "page": int(m.group(2))})

    def handle_data(self, data):
        if self._cur is not None:
            self._cur["text"] += data

    def handle_endtag(self, tag):
        if tag != "p" or self._cur is None:
            return
        cur, self._cur = self._cur, None
        # Term text is everything before the first page number.
        term = re.split(r",\s*\d", cur["text"], maxsplit=1)[0].strip().rstrip(",")
        if cur["level"] == 1:
            self._primary = term
            self.entries.append({"term": term, "sub": None, "refs": cur["refs"]})
        else:
            self.entries.append({"term": self._primary, "sub": term, "refs": cur["refs"]})


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    epub = zipfile.ZipFile(sys.argv[1])
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "work")
    (out / "text").mkdir(parents=True, exist_ok=True)

    chapters = []
    for stem, n in CHAPTER_FILES.items():
        p = ChapterText()
        p.feed(epub.read(f"OEBPS/{stem}.xhtml").decode("utf-8"))
        (out / "text" / f"ch{n:02d}.txt").write_text(p.text(), encoding="utf-8")
        heads = [h.strip() for h in p.headings if h.strip()]
        title = heads[-1] if heads else stem
        chapters.append({"n": n, "title": title, "pages": [min(p.pages), max(p.pages)]})

    idx = IndexParser()
    idx.feed(epub.read("OEBPS/appendix001.xhtml").decode("utf-8"))

    (out / "chapters.json").write_text(json.dumps(chapters, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "index.json").write_text(json.dumps(idx.entries, indent=1, ensure_ascii=False), encoding="utf-8")
    words = sum(len((out / "text" / f"ch{c['n']:02d}.txt").read_text().split()) for c in chapters)
    print(f"{len(chapters)} chapters, {words} words, {len(idx.entries)} index entries -> {out}/")


if __name__ == "__main__":
    main()
