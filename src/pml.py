# PML is short for Page Modeling Language, our own neat little PDF-wannabe
# format for expressing a script's complete contents in a neutral way
# that's easy to render to almost anything, e.g. PDF, Postscript, Windows
# GDI, etc.
#

# A PML document is a collection of pages plus possibly some metadata.
# Each page is a collection of simple drawing commands, executed
# sequentially in the order given, assuming "complete overdraw" semantics
# on the output device, i.e. whatever is drawn completely covers things it
# is painted on top of.

# All measurements in PML are in (floating point) millimeters.

import misc
import pdf
import util

import textwrap

# text flags. don't change these unless you know what you're doing.
NORMAL = 0
BOLD   = 1
ITALIC = 2
COURIER = 0
TIMES_ROMAN = 4
HELVETICA = 8
UNDERLINED = 16

# fill types
NO_FILL = 0
FILL = 1
STROKE_FILL = 2

# A single document.
class Document:

    # (w, h) is the size of each page.
    def __init__(self, w, h):
        self.w = w
        self.h = h

        # a collection of Page objects
        self.pages = []

        # a collection of TOCItem objects
        self.tocs = []

        # user-specified fonts, if any. key = 2 lowest bits of
        # TextOp.flags, value = pml.PDFFontInfo
        self.fonts = {}

        # whether to show TOC by default on document open
        self.showTOC = False

        # page number to display on document open, or -1
        self.defPage = -1

        # when running testcases, misc.version does not exist, so store a
        # dummy value in that case, correct value otherwise.
        self.version = getattr(misc, "version", "dummy_version")

        # a random string to embed in the PDF; only used by watermarked
        # PDFs
        self.uniqueId = None

    def add(self, page):
        self.pages.append(page)

    def addTOC(self, toc):
        self.tocs.append(toc)

    def addFont(self, style, pfi):
        self.fonts[style] = pfi

class Page:
    def __init__(self, doc):

        # link to containing document
        self.doc = doc

        # a collection of Operation objects
        self.ops = []

    def add(self, op):
        self.ops.append(op)

    def addOpsToFront(self, opsList):
        self.ops = opsList + self.ops

# Table of content item (Outline item, in PDF lingo)
class TOCItem:
    def __init__(self, text, op):
        # text to show in TOC
        self.text = text

        # pointer to the TextOp that this item links to (used to get the
        # correct positioning information)
        self.op = op

        # the PDF object number of the page we point to
        self.pageObjNr = -1

# information about one PDF font
class PDFFontInfo:
    def __init__(self, name, fontProgram):
        # name to use in generated PDF file ("CourierNew", "MyFontBold",
        # etc.). if empty, use the default PDF font.
        self.name = name

        # the font program (in practise, the contents of the .ttf file for
        # the font), or None, in which case the font is not embedded.
        self.fontProgram = fontProgram

# An abstract base class for all drawing operations.
class DrawOp:
    pass

# Draw text string 'text', at position (x, y) mm from the upper left
# corner of the page. Font used is 'size' points, and Courier / Times/
# Helvetica as indicated by the flags, possibly being bold / italic /
# underlined. angle is None, or an integer from 0 to 360 that gives the
# slant of the text counter-clockwise from x-axis.
class TextOp(DrawOp):
    pdfOp = pdf.PDFTextOp()

    def __init__(self, text, x, y, size, flags = NORMAL | COURIER,
                 align = util.ALIGN_LEFT, valign = util.VALIGN_TOP,
                 line = -1, angle = None):
        self.text = text
        self.x = x
        self.y = y
        self.size = size
        self.flags = flags
        self.angle = angle

        # TOCItem, by default we have none
        self.toc = None

        # index of line in Screenplay.lines, or -1 if some other text.
        # only used when drawing display, pdf output doesn't use this.
        self.line = line

        if align != util.ALIGN_LEFT:
            w = util.getTextWidth(text, flags, size)

            if align == util.ALIGN_CENTER:
                self.x -= w / 2.0
            elif align == util.ALIGN_RIGHT:
                self.x -= w

        if valign != util.VALIGN_TOP:
            h = util.getTextHeight(size)

            if valign == util.VALIGN_CENTER:
                self.y -= h / 2.0
            elif valign == util.VALIGN_BOTTOM:
                self.y -= h

# Draw consecutive lines. 'points' is a list of (x, y) pairs (minimum 2
# pairs) and 'width' is the line width, with 0 being the thinnest possible
# line. if 'isClosed' is True, the last point on the list is connected to
# the first one.
class LineOp(DrawOp):
    pdfOp = pdf.PDFLineOp()

    def __init__(self, points, width, isClosed = False):
        self.points = points
        self.width = width
        self.isClosed = isClosed

# helper function for creating simple lines
def genLine(x, y, xd, yd, width):
    return LineOp([(x, y), (x + xd, y + yd)], width)

# Draw a rectangle, possibly filled, with specified lineWidth (which can
# be -1 if fillType is FILL). (x, y) is position of upper left corner.
class RectOp(DrawOp):
    pdfOp = pdf.PDFRectOp()

    def __init__(self, x, y, width, height, fillType = FILL, lineWidth = -1):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.fillType = fillType
        self.lw = lineWidth

# Draw a quarter circle centered at (x, y) with given radius and line
# width. By default it will be the upper left quadrant of a circle, but
# using the flip[XY] parameters you can choose other quadrants.
class QuarterCircleOp(DrawOp):
    pdfOp = pdf.PDFQuarterCircleOp()

    def __init__(self, x, y, radius, width, flipX = False, flipY = False):
        self.x = x
        self.y = y
        self.radius = radius
        self.width = width
        self.flipX = flipX
        self.flipY = flipY

# Arbitrary PDF commands. Should not have whitespace in the beginning or
# the end. Should be used only for non-critical things like tweaking line
# join styles etc, because non-PDF renderers will ignore these.
class PDFOp(DrawOp):
    pdfOp = pdf.PDFArbitraryOp()

    def __init__(self, cmds):
        self.cmds = cmds

# create a PML document containing text (possibly linewrapped) divided
# into pages automatically.
class TextFormatter:
    def __init__(self, width, height, margin, fontSize):
        self.doc = Document(width, height)

        # how much to leave empty on each side (mm)
        self.margin = margin

        # font size
        self.fontSize = fontSize

        # number of chararacters that fit on a single line
        self.charsToLine = int((width - margin * 2.0) /
                               util.getTextWidth(" ", COURIER, fontSize))

        self.createPage()

    # add new empty page, select it as current, reset y pos
    def createPage(self):
        self.pg = Page(self.doc)

        self.doc.add(self.pg)
        self.y = self.margin

    # add blank vertical space, unless we're at the top of the page
    def addSpace(self, mm):
        if self.y > self.margin:
            self.y += mm

    # add text
    def addText(self, text, x = None, fs = None, style = NORMAL):
        if x == None:
            x = self.margin

        if fs == None:
            fs = self.fontSize

        yd = util.getTextHeight(fs)

        if (self.y + yd) > (self.doc.h - self.margin):
            self.createPage()

        self.pg.add(TextOp(text, x, self.y, fs, style))

        self.y += yd

    # wrap text into lines that fit on the page, using Courier and default
    # font size and style, and add the lines. 'indent' is the text to
    # prefix lines other than the first one with.
    def addWrappedText(self, text, indent):
        tmp = textwrap.wrap(text, self.charsToLine,
                subsequent_indent = indent)

        for s in tmp:
            self.addText(s)
