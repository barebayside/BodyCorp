"""
A small PDF writer for the lawyer's pack: A4 pages of wrapped text in Helvetica, nothing else.

WHY OUR OWN
    Catalyst's deploy installs requirements with `--only-binary=:all:` for manylinux2014. A pure-Python
    writer can't fail there and needs no Pillow or fonts. Text only: forms are drawn as words
    ("[ ] I'll keep the dog on a lead", "What animal? ____"), which is all a lawyer needs to read them.
    Characters outside Windows-1252 print as "?" (the built-in fonts only know that set).

    doc = Pdf("Legal pack")
    doc.heading("Alatai on the Park")
    doc.text("Plain words, wrapped to the page.", size=10, bold=False, indent=0, grey=False)
    doc.line(); doc.gap(8)
    data = doc.bytes()
"""

PAGE_W, PAGE_H = 595, 842          # A4 in points
MARGIN = 50
BOTTOM = 60
WIDTH_FACTOR = {False: 0.53, True: 0.58}   # average Helvetica glyph width per point of size (kept generous)


SWAPS = {"→": "->", "←": "<-", "≤": "<=", "≥": ">=", "−": "-", "✓": "x"}


def _encode(text):
    text = str(text).replace("\t", "    ")
    for old, new in SWAPS.items():
        text = text.replace(old, new)
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def wrap(text, size, width, bold=False):
    """Lines of `text` that fit `width` points at `size`. Long words are cut."""
    per_line = max(10, int(width / (size * WIDTH_FACTOR[bold])))
    out = []
    for para in str(text or "").split("\n"):
        words, line = para.split(" "), ""
        for word in words:
            while len(word) > per_line:
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:per_line])
                word = word[per_line:]
            candidate = (line + " " + word) if line else word
            if len(candidate) > per_line:
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return out


class Pdf:
    def __init__(self, title=""):
        self.title = title
        self.pages = []
        self._ops = None
        self.y = 0
        self._new_page()

    def _new_page(self):
        self._ops = []
        self.pages.append(self._ops)
        self.y = PAGE_H - MARGIN

    def _room(self, height):
        if self.y - height < BOTTOM:
            self._new_page()

    def gap(self, points):
        self.y -= points
        if self.y < BOTTOM:
            self._new_page()

    def text(self, text, size=10, bold=False, indent=0, grey=False):
        lead = size * 1.35
        for line in wrap(text, size, PAGE_W - 2 * MARGIN - indent, bold):
            self._room(lead)
            self.y -= lead
            colour = "0.4 0.4 0.4 rg" if grey else "0.1 0.1 0.1 rg"
            self._ops.append(b"BT %s /%s %d Tf %d %d Td (%s) Tj ET" % (
                colour.encode(), b"F2" if bold else b"F1", size, MARGIN + indent, int(self.y), _encode(line)))

    def heading(self, text, size=15):
        self.gap(6)
        self.text(text, size=size, bold=True)
        self.gap(4)

    def line(self):
        self._room(10)
        self.y -= 6
        self._ops.append(b"0.75 0.75 0.75 RG 0.5 w %d %d m %d %d l S" % (MARGIN, int(self.y), PAGE_W - MARGIN,
                                                                         int(self.y)))
        self.y -= 4

    def bytes(self):
        objects = []                                   # (number, body bytes)

        def add(body):
            objects.append(body)
            return len(objects)

        catalog = add(b"")                             # filled in below
        pages_obj = add(b"")
        font1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        font2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        total = len(self.pages)
        for n, ops in enumerate(self.pages, 1):
            footer = b"BT 0.5 0.5 0.5 rg /F1 8 Tf %d 30 Td (%s) Tj ET" % (
                MARGIN, _encode("{} - page {} of {}".format(self.title, n, total)))
            stream = b"\n".join(ops + [footer])
            content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
            page = add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                       b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> >>" % (
                           pages_obj, PAGE_W, PAGE_H, content, font1, font2))
            kids.append(page)
        objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj
        objects[pages_obj - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        info = add(b"<< /Title (%s) /Producer (BodyCorp portal) >>" % _encode(self.title))
        out = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        offsets = []
        for number, body in enumerate(objects, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objects) + 1, catalog, info, xref)
        return out
