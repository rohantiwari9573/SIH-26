# -*- coding: utf-8 -*-
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)

SRC = str(ASSETS / "SIH2026-IDEA-Presentation-Format.pptx")
OUT = str(DIST / "MetroCert_SIH2026_Idea_Submission.pptx")
# No live screenshots for this one -- PS26035 is a fresh idea-stage
# submission with nothing built yet, so slides 4 and 6 use labelled
# wireframe mockups instead of product evidence (see wireframe_mock()).

# The official template's own "Oval N" shape on every content slide holds
# placeholder text "Your Team Name" at this exact top-left spot -- it's a
# real, intentional part of the template, not decoration. We replace it
# with our own styled badge carrying the actual team name/ID rather than
# just deleting it.
TEAM_NAME = "Nexus2.O"
TEAM_ID = "164739"

# ---------------- palette (sampled from the reference mockup) ----------------
HDR_PURPLE = RGBColor(0x6E, 0x5A, 0x98)
DEEP_PURPLE = RGBColor(0x42, 0x2F, 0x6C)
NAVY_CARD = RGBColor(0x25, 0x46, 0x7E)
TITLE_INK = RGBColor(0x2A, 0x1B, 0x54)
BODY_INK = RGBColor(0x22, 0x28, 0x33)
LILAC_BG = RGBColor(0xF1, 0xE8, 0xFE)
BLUE_BG = RGBColor(0xDA, 0xEF, 0xFB)
GREEN_BG = RGBColor(0xDE, 0xFA, 0xE9)
ORANGE_BG = RGBColor(0xFD, 0xEE, 0xD5)
LILAC_LINE = RGBColor(0xB9, 0xA6, 0xE8)
BLUE_LINE = RGBColor(0x7F, 0xB8, 0xDD)
GREEN_LINE = RGBColor(0x7C, 0xC9, 0x9A)
ORANGE_LINE = RGBColor(0xE4, 0xB6, 0x66)
BLUE_NUM = RGBColor(0x1F, 0x5C, 0x9E)
GREEN_NUM = RGBColor(0x1E, 0x8A, 0x4A)
ORANGE_NUM = RGBColor(0xC2, 0x6A, 0x14)
PURPLE_NUM = RGBColor(0x5B, 0x3A, 0x9E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREY = RGBColor(0x8A, 0x93, 0xA3)
LIGHTBG = RGBColor(0xF6, 0xF4, 0xFB)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
EMOJI_FONT = "Segoe UI Emoji"


def delete_slide(prs, index):
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    rId = slides[index].get(qn('r:id'))
    prs.part.drop_rel(rId)
    xml_slides.remove(slides[index])


def by_name(slide, name):
    for s in slide.shapes:
        if s.name == name:
            return s
    return None


def clear_footer(slide):
    for shape in slide.shapes:
        if shape.name == 'Footer Placeholder 6' and shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    run.text = " "


def clear_default_chrome(slide):
    """Strip the official template's own title/body placeholders and any
    leftover content textboxes so we can lay the mockup's own header/body
    on a clean slide -- keeping the slide's inherited SIH logo picture,
    which lives on the layout/master and isn't a placeholder we touch."""
    for shape in list(slide.shapes):
        if shape.has_text_frame and shape.is_placeholder:
            ph_type = shape.placeholder_format.type
            # keep footer/slide-number placeholders (idx handled by clear_footer)
            if shape.name in ('Footer Placeholder 6',):
                continue
        # remove title/subtitle/body placeholders and legacy textboxes we no
        # longer use; leave pictures (the SIH logo) and footer/page-number
        # placeholders alone.
        if shape.has_text_frame and shape.shape_type != 13:
            if shape.name.startswith('Oval'):
                # The template's own decorative oval (a "Team Name" badge in
                # an earlier layout) keeps a visible stroke even once its
                # text is cleared -- a stray ring left sitting over the
                # title. Delete the shape outright, not just its text.
                shape._element.getparent().remove(shape._element)
                continue
            if shape.name.startswith(('Title', 'Subtitle', 'TextBox')):
                shape.text_frame.clear()


def corner_deco_tl(slide, d=1.9):
    """A clean quarter-circle in the top-left corner: a full circle centred
    exactly on the slide's (0,0) point, so only one quarter is ever visible.
    Far more reliable across renderers than MSO_SHAPE.PIE adjustments.
    Sized to 1.9in (down from an earlier 2.6in) specifically so it clears
    both the header bar and the title row, leaving room for team_badge()
    to sit in the corner without colliding with either."""
    dd = Inches(d)
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(-d / 2), Inches(-d / 2), dd, dd)
    c.fill.solid(); c.fill.fore_color.rgb = DEEP_PURPLE
    c.line.fill.background(); c.shadow.inherit = False
    return c


def team_badge(slide):
    """Fills the official template's own top-left 'Your Team Name' slot
    (an Oval shape at this exact position on every content slide) with a
    real, readable badge instead of the template's unstyled placeholder
    text -- sits just left of the header bar, inside the corner circle."""
    b = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.1), Inches(0.32), Inches(1.32), Inches(0.36))
    b.fill.solid(); b.fill.fore_color.rgb = WHITE
    b.line.color.rgb = WHITE; b.line.width = Pt(1)
    b.shadow.inherit = False
    tf = b.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.06); tf.margin_right = Inches(0.06)
    tf.margin_top = 0; tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = TEAM_NAME
    r.font.size = Pt(12); r.font.bold = True; r.font.color.rgb = DEEP_PURPLE; r.font.name = "Arial"
    return b


def header_bar(slide, title_text):
    """Purple quarter-circle corner + 'SMART INDIA HACKATHON 2026' bar,
    matching the reference mockup's own chrome (replaces the official
    template's default title placeholder look for these content slides)."""
    corner_deco_tl(slide)
    team_badge(slide)

    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.55), Inches(0.22), Inches(5.6), Inches(0.5))
    bar.fill.solid(); bar.fill.fore_color.rgb = HDR_PURPLE
    bar.line.fill.background(); bar.shadow.inherit = False
    tf = bar.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.15)
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = "SMART INDIA HACKATHON 2026"
    r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Arial"

    ttl = slide.shapes.add_textbox(Inches(0.5), Inches(0.85), Inches(11.5), Inches(0.55))
    tf = ttl.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = title_text
    r.font.size = Pt(28); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Georgia"
    return ttl


def subtitle_line(slide, text, top=Inches(1.42)):
    tb = slide.shapes.add_textbox(Inches(0.5), top, Inches(12.3), Inches(0.4))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
    r = p.add_run(); r.text = text
    r.font.size = Pt(13); r.font.color.rgb = NAVY_CARD; r.font.name = "Arial"
    return tb


def corner_deco_br(slide, d=1.8):
    dd = Inches(d)
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(13.333 - d / 2), Inches(7.5 - d / 2), dd, dd)
    c.fill.solid(); c.fill.fore_color.rgb = DEEP_PURPLE
    c.line.fill.background(); c.shadow.inherit = False
    return c


def card(slide, left, top, width, height, fill=WHITE, line_color=None, radius=True):
    shp = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    box = slide.shapes.add_shape(shp, left, top, width, height)
    box.fill.solid(); box.fill.fore_color.rgb = fill
    if line_color is None:
        box.line.fill.background()
    else:
        box.line.color.rgb = line_color
        box.line.width = Pt(1)
    box.shadow.inherit = False
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.12); tf.margin_right = Inches(0.12)
    tf.margin_top = Inches(0.08); tf.margin_bottom = Inches(0.08)
    return box


def section_header_bar(slide, left, top, width, height, text, fill):
    b = card(slide, left, top, width, height, fill=fill)
    b.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = b.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Arial"
    return b


def icon_line(slide, left, top, width, height, emoji, text, emoji_color=NAVY_CARD, text_pt=11):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    r1 = p.add_run(); r1.text = emoji + "  "
    r1.font.size = Pt(text_pt + 1); r1.font.name = EMOJI_FONT; r1.font.color.rgb = emoji_color
    r2 = p.add_run(); r2.text = text
    r2.font.size = Pt(text_pt); r2.font.color.rgb = BODY_INK; r2.font.name = "Arial"
    return box


def number_circle(slide, left, top, d, number, color):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, d, d)
    c.fill.solid(); c.fill.fore_color.rgb = color
    c.line.fill.background(); c.shadow.inherit = False
    tf = c.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.word_wrap = False
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = number
    r.font.size = Pt(15); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Arial"


def right_arrow(slide, left, top, width, height, color=GREY):
    ar = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, left, top, width, height)
    ar.fill.solid(); ar.fill.fore_color.rgb = color
    ar.line.fill.background(); ar.shadow.inherit = False


def down_arrow(slide, left, top, width, height, color=DEEP_PURPLE):
    ar = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, left, top, width, height)
    ar.fill.solid(); ar.fill.fore_color.rgb = color
    ar.line.fill.background(); ar.shadow.inherit = False


def metric_tile(slide, left, top, width, height, number, label, fill, num_color, line_color):
    b = card(slide, left, top, width, height, fill=fill, line_color=line_color)
    tf = b.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p0 = tf.paragraphs[0]; p0.alignment = PP_ALIGN.CENTER
    r0 = p0.add_run(); r0.text = number
    r0.font.size = Pt(24); r0.font.bold = True; r0.font.color.rgb = num_color; r0.font.name = "Arial"
    p1 = tf.add_paragraph(); p1.alignment = PP_ALIGN.CENTER
    r1 = p1.add_run(); r1.text = label
    r1.font.size = Pt(9.5); r1.font.bold = True; r1.font.color.rgb = TITLE_INK; r1.font.name = "Arial"
    return b


def flow_chip(slide, left, top, width, height, text, fill, text_color):
    b = card(slide, left, top, width, height, fill=fill)
    tf = b.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, ln in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = ln
        r.font.size = Pt(11); r.font.bold = True; r.font.color.rgb = text_color; r.font.name = "Arial"
    return b


def icon_chip(slide, left, top, width, height, emoji, label, fill, line_color):
    b = card(slide, left, top, width, height, fill=fill, line_color=line_color)
    tf = b.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p0 = tf.paragraphs[0]; p0.alignment = PP_ALIGN.CENTER
    r0 = p0.add_run(); r0.text = emoji
    r0.font.size = Pt(20); r0.font.name = EMOJI_FONT; r0.font.color.rgb = TITLE_INK
    for ln in label.split("\n"):
        p = tf.add_paragraph(); p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = ln
        r.font.size = Pt(9.5); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Arial"
    return b


def stakeholder_card(slide, left, top, width, height, emoji, title, items, line_color):
    b = card(slide, left, top, width, height, fill=WHITE, line_color=line_color)
    tf = b.text_frame
    p0 = tf.paragraphs[0]; p0.alignment = PP_ALIGN.CENTER
    r0 = p0.add_run(); r0.text = emoji
    r0.font.size = Pt(18); r0.font.name = EMOJI_FONT; r0.font.color.rgb = TITLE_INK
    p0b = tf.add_paragraph(); p0b.alignment = PP_ALIGN.CENTER
    r0b = p0b.add_run(); r0b.text = title
    r0b.font.size = Pt(12); r0b.font.bold = True; r0b.font.color.rgb = TITLE_INK; r0b.font.name = "Arial"
    for it in items:
        p = tf.add_paragraph()
        r = p.add_run(); r.text = "\u2713 " + it
        r.font.size = Pt(10); r.font.color.rgb = BODY_INK; r.font.name = "Arial"
    return b


def ref_card(slide, left, top, width, height, emoji, title, items, fill, line_color):
    hdr = card(slide, left, top, width, Inches(0.42), fill=fill, line_color=line_color)
    tf = hdr.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    r0 = p.add_run(); r0.text = emoji + "  "
    r0.font.size = Pt(13); r0.font.name = EMOJI_FONT; r0.font.color.rgb = TITLE_INK
    r1 = p.add_run(); r1.text = title
    r1.font.size = Pt(11); r1.font.bold = True; r1.font.color.rgb = TITLE_INK; r1.font.name = "Arial"
    body = card(slide, left, top + Inches(0.42), width, height - Inches(0.42), fill=WHITE)
    tf2 = body.text_frame
    for i, it in enumerate(items):
        p = tf2.paragraphs[0] if i == 0 else tf2.add_paragraph()
        r = p.add_run(); r.text = "\u2713 " + it
        r.font.size = Pt(9.5); r.font.color.rgb = BODY_INK; r.font.name = "Arial"


def wireframe_tag(slide, left, top, width):
    """Small honesty label stamped on every mockup panel: this is a concept
    sketch of the proposed UI, not a screenshot of anything built."""
    tb = slide.shapes.add_textbox(left, top, width, Inches(0.22))
    p = tb.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = "CONCEPT UI — PROPOSED, NOT YET BUILT"
    r.font.size = Pt(8); r.font.bold = True; r.font.color.rgb = GREY; r.font.name = "Arial"


def mock_report_form(slide, left, top, w, h):
    """Wireframe sketch of the proposed test-entry / report screen: a dark
    panel with placeholder field bars and a pass/fail compliance chip --
    same visual language as the dark 'evidence' panels elsewhere in this
    template family, but explicitly labelled as a mockup."""
    panel = card(slide, left, top, w, h, fill=RGBColor(0x1A, 0x1A, 0x22))
    pad = Inches(0.18)
    y = top + pad
    title = slide.shapes.add_textbox(left + pad, y, w - 2 * pad, Inches(0.26))
    tf = title.text_frame; tf.word_wrap = True
    r = tf.paragraphs[0].add_run(); r.text = "NAWI Test Report — TR-2026-0142"
    r.font.size = Pt(10.5); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Georgia"
    y += Inches(0.38)
    fields = ["Manufacturer / Model", "Max Capacity / Verification Scale Interval", "Test: Repeatability (OIML R-76 §A.4.2)", "Test: Eccentricity Loading (§A.4.3)"]
    for f in fields:
        row = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left + pad, y, w - 2 * pad, Inches(0.32))
        row.fill.solid(); row.fill.fore_color.rgb = RGBColor(0x2A, 0x2A, 0x35)
        row.line.fill.background(); row.shadow.inherit = False
        tf = row.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE; tf.margin_left = Inches(0.1)
        tf.word_wrap = False
        rr = tf.paragraphs[0].add_run(); rr.text = f
        rr.font.size = Pt(9); rr.font.color.rgb = RGBColor(0xC8, 0xC8, 0xD4); rr.font.name = "Arial"
        y += Inches(0.4)
    chip = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left + pad, y, Inches(2.3), Inches(0.32))
    chip.fill.solid(); chip.fill.fore_color.rgb = RGBColor(0x1E, 0x6B, 0x3A)
    chip.line.fill.background(); chip.shadow.inherit = False
    tf = chip.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE; tf.word_wrap = False
    rr = tf.paragraphs[0].add_run(); rr.text = "● PASS — within tolerance"
    rr.font.size = Pt(9); rr.font.bold = True; rr.font.color.rgb = WHITE; rr.font.name = "Arial"


def mock_dashboard(slide, left, top, w, h):
    """Wireframe sketch of the proposed MetroCert dashboard: sidebar +
    stat-tile row + a report-list table, in the same dark-panel style used
    for the real product screenshots elsewhere -- but this one is a sketch,
    clearly labelled, since no software exists yet for this PS."""
    panel = card(slide, left, top, w, h, fill=RGBColor(0x1A, 0x1A, 0x22))
    pad = Inches(0.15)
    side_w = Inches(1.3)
    side = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, side_w, h)
    side.fill.solid(); side.fill.fore_color.rgb = RGBColor(0x12, 0x12, 0x18)
    side.line.fill.background(); side.shadow.inherit = False
    for i, label in enumerate(["Dashboard", "New Report", "Repository", "Instruments"]):
        t = slide.shapes.add_textbox(left + Inches(0.12), top + Inches(0.2) + i * Inches(0.32), side_w - Inches(0.2), Inches(0.28))
        r = t.text_frame.paragraphs[0].add_run(); r.text = label
        r.font.size = Pt(8.5); r.font.color.rgb = RGBColor(0xC8, 0xC8, 0xD4); r.font.name = "Arial"
    body_left = left + side_w + pad
    body_w = w - side_w - 2 * pad
    heading = slide.shapes.add_textbox(body_left, top + Inches(0.15), body_w, Inches(0.26))
    r = heading.text_frame.paragraphs[0].add_run(); r.text = "Overview"
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Georgia"
    tiles = [("Reports Generated", "128"), ("Pass Rate", "91%"), ("Pending Review", "6")]
    tile_w = (body_w - Inches(0.2)) / 3
    for i, (lab, val) in enumerate(tiles):
        tx = body_left + i * (tile_w + Inches(0.1))
        t = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, tx, top + Inches(0.5), tile_w, Inches(0.62))
        t.fill.solid(); t.fill.fore_color.rgb = RGBColor(0x2A, 0x2A, 0x35)
        t.line.fill.background(); t.shadow.inherit = False
        tf = t.text_frame; tf.margin_left = Inches(0.08); tf.margin_top = Inches(0.04)
        p0 = tf.paragraphs[0]; r0 = p0.add_run(); r0.text = lab
        r0.font.size = Pt(7.5); r0.font.color.rgb = RGBColor(0x9A, 0x9A, 0xAA); r0.font.name = "Arial"
        p1 = tf.add_paragraph(); r1 = p1.add_run(); r1.text = val
        r1.font.size = Pt(15); r1.font.bold = True; r1.font.color.rgb = WHITE; r1.font.name = "Arial"
    table_top = top + Inches(1.3)
    for i in range(3):
        row = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, body_left, table_top + i * Inches(0.3), body_w, Inches(0.26))
        row.fill.solid(); row.fill.fore_color.rgb = RGBColor(0x22, 0x22, 0x2C) if i % 2 else RGBColor(0x1E, 0x1E, 0x27)
        row.line.fill.background(); row.shadow.inherit = False
        tf = row.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE; tf.margin_left = Inches(0.1)
        rr = tf.paragraphs[0].add_run(); rr.text = f"TR-2026-{140+i}   ·   Weighbridge WB-{i+1}   ·   Status: {'Pass' if i != 2 else 'In Review'}"
        rr.font.size = Pt(8); rr.font.color.rgb = RGBColor(0xC8, 0xC8, 0xD4); rr.font.name = "Arial"


# ============================================================ build
prs = Presentation(SRC)
slides = list(prs.slides)

# ================= SLIDE 1 : TITLE =================
s1 = slides[0]
clear_default_chrome(s1)
# Same corner size + same header-bar geometry as every content slide
# (header_bar()'s bar), so the recurring SIH chrome is pixel-identical
# across all 6 slides rather than just "close."
corner_deco_tl(s1)
team_badge(s1)

bar = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.55), Inches(0.22), Inches(5.6), Inches(0.5))
bar.fill.solid(); bar.fill.fore_color.rgb = HDR_PURPLE
bar.line.fill.background(); bar.shadow.inherit = False
tf = bar.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE; tf.margin_left = Inches(0.15)
r = tf.paragraphs[0].add_run(); r.text = "SMART INDIA HACKATHON 2026"
r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Arial"

corner_deco_br(s1)

logo_tb = s1.shapes.add_textbox(Inches(0.5), Inches(2.1), Inches(6.6), Inches(1.0))
tf = logo_tb.text_frame
p = tf.paragraphs[0]
r1 = p.add_run(); r1.text = "MetroCert  "
r1.font.size = Pt(44); r1.font.bold = True; r1.font.color.rgb = DEEP_PURPLE; r1.font.name = "Georgia"
r2 = p.add_run(); r2.text = "⚖"
r2.font.size = Pt(36); r2.font.name = EMOJI_FONT

subt = s1.shapes.add_textbox(Inches(0.5), Inches(3.05), Inches(7.3), Inches(0.8))
tf = subt.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]
r = p.add_run(); r.text = "Automated Test Report & Compliance Platform for Non-Automatic Weighing Instruments"
r.font.size = Pt(17); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Arial"

# Full facts preserved (nothing dropped), but the two most sentence-like
# fields ride a slim line above the scannable metadata grid rather than
# padding out a seven-row bullet list.
extra_line = s1.shapes.add_textbox(Inches(0.55), Inches(3.9), Inches(7.2), Inches(0.3))
p = extra_line.text_frame.paragraphs[0]
r = p.add_run(); r.text = "Problem Statement: NAWI Test Report Generation per OIML R-76   ·   PS Category: Software"
r.font.size = Pt(10.5); r.font.color.rgb = GREY; r.font.name = "Arial"

meta_items = [
    ("PS ID", "26035"),
    ("THEME", "Miscellaneous"),
    ("ORGANIZATION", "DoCA (Consumer Affairs)"),
    ("TEAM", "Nexus2.O  •  164739"),
]
mg_left = Inches(0.55); mg_top = Inches(4.35)
mg_w = Inches(3.5); mg_h = Inches(0.85); mg_gap = Inches(0.18)
for i, (label, value) in enumerate(meta_items):
    col = i % 2; row = i // 2
    l = mg_left + col * (mg_w + mg_gap)
    t = mg_top + row * (mg_h + mg_gap)
    b = card(s1, l, t, mg_w, mg_h, fill=LILAC_BG if (i % 3 != 1) else BLUE_BG, line_color=LILAC_LINE if (i % 3 != 1) else BLUE_LINE)
    tf = b.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p0 = tf.paragraphs[0]; p0.alignment = PP_ALIGN.CENTER
    r0 = p0.add_run(); r0.text = label
    r0.font.size = Pt(10); r0.font.bold = True; r0.font.color.rgb = NAVY_CARD; r0.font.name = "Arial"
    p1 = tf.add_paragraph(); p1.alignment = PP_ALIGN.CENTER
    r1 = p1.add_run(); r1.text = value
    r1.font.size = Pt(15); r1.font.bold = True; r1.font.color.rgb = TITLE_INK; r1.font.name = "Arial"

divider = s1.shapes.add_connector(1, Inches(0.55), Inches(6.42), Inches(6.7), Inches(6.42))
divider.line.color.rgb = DEEP_PURPLE; divider.line.width = Pt(1.25)

tag = s1.shapes.add_textbox(Inches(0.55), Inches(6.55), Inches(6.7), Inches(0.5))
tf = tag.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]
r = p.add_run(); r.text = "FROM MANUAL SPREADSHEETS TO STANDARDIZED COMPLIANCE"
r.font.size = Pt(11); r.font.bold = True; r.font.color.rgb = NAVY_CARD; r.font.name = "Arial"

# The official template's own decorative hex/brain graphic already occupies
# this right-hand region (inherited from SRC, not something we draw) --
# deliberately not adding a duplicate graphic on top of it.

# ================= SLIDE 2 : PROPOSED SOLUTION =================
s2 = slides[1]
clear_default_chrome(s2)
clear_footer(s2)
header_bar(s2, "The Problem \u2192 Our Solution")
subtitle_line(s2, "NAWI model-approval testing still runs on manual spreadsheets \u2014 slow, inconsistent, and error-prone.")
corner_deco_br(s2)

fc_left, fc_top, fc_w, fc_h = Inches(0.5), Inches(2.0), Inches(3.68), Inches(3.55)
section_header_bar(s2, fc_left, fc_top, fc_w, Inches(0.42), "Today's Pain Points", NAVY_CARD)
fc_body = card(s2, fc_left, fc_top + Inches(0.42), fc_w, fc_h - Inches(0.42), fill=WHITE, line_color=RGBColor(0xE3, 0xE3, 0xEE))
clues = [
    ("\U0001F4C4", "Manual spreadsheet reports"),
    ("\u274c", "Calculation errors"),
    ("\U0001F500", "Inconsistent report formats"),
    ("\U0001F50D", "No searchable repository"),
    ("\U0001F40C", "Slow approval turnaround"),
]
cy = fc_top + Inches(0.65)
for emoji, text in clues:
    icon_line(s2, fc_left + Inches(0.2), cy, fc_w - Inches(0.4), Inches(0.4), emoji, text, text_pt=12)
    cy += Inches(0.58)

right_arrow(s2, fc_left + fc_w + Inches(0.08), fc_top + fc_h / 2 - Inches(0.15), Inches(0.5), Inches(0.3), color=NAVY_CARD)

pil_left = fc_left + fc_w + Inches(0.75)
pil_w = Inches(3.47)
title_argus = s2.shapes.add_textbox(pil_left, fc_top - Inches(0.05), pil_w, Inches(0.4))
p = title_argus.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
r = p.add_run(); r.text = "MetroCert"
r.font.size = Pt(20); r.font.bold = True; r.font.color.rgb = DEEP_PURPLE; r.font.name = "Georgia"

pillars = [
    ("01", "Automated Test Data\nCapture & Validation", LILAC_BG, PURPLE_NUM),
    ("02", "OIML R-76 Compliance\nEngine (Pass / Fail)", BLUE_BG, BLUE_NUM),
    ("03", "Standardized Report\nGeneration & Archive", BLUE_BG, GREEN_NUM),
]
py = fc_top + Inches(0.42)
ph = Inches(0.85)
for num, label, fill, numcolor in pillars:
    b = card(s2, pil_left, py, pil_w, ph, fill=fill)
    number_circle(s2, pil_left + Inches(0.12), py + ph / 2 - Inches(0.23), Inches(0.46), num, numcolor)
    tb = s2.shapes.add_textbox(pil_left + Inches(0.68), py + Inches(0.06), pil_w - Inches(0.8), ph - Inches(0.12))
    tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, ln in enumerate(label.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = ln
        r.font.size = Pt(12.5); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Arial"
    py += ph + Inches(0.15)

right_arrow(s2, pil_left + pil_w + Inches(0.08), fc_top + fc_h / 2 - Inches(0.15), Inches(0.5), Inches(0.3), color=NAVY_CARD)

ui_left = pil_left + pil_w + Inches(0.75)
ui_w = Inches(3.68)
section_header_bar(s2, ui_left, fc_top, ui_w, Inches(0.42), "Unified Compliance Output", NAVY_CARD)
ui_body = card(s2, ui_left, fc_top + Inches(0.42), ui_w, fc_h - Inches(0.42), fill=WHITE, line_color=RGBColor(0xE3, 0xE3, 0xEE))
ss_h = Inches(1.0)
ss_w = ui_w - Inches(0.2)
ss_left = ui_left + (ui_w - ss_w) / 2
ss_top = fc_top + Inches(0.58)
mini = card(s2, ss_left, ss_top, ss_w, ss_h, fill=RGBColor(0x1A, 0x1A, 0x22))
mini_title = s2.shapes.add_textbox(ss_left + Inches(0.12), ss_top + Inches(0.08), ss_w - Inches(0.24), Inches(0.22))
r = mini_title.text_frame.paragraphs[0].add_run(); r.text = "NAWI Test Report — TR-2026-0142"
r.font.size = Pt(9.5); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Georgia"
mini_row = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, ss_left + Inches(0.12), ss_top + Inches(0.36), ss_w - Inches(0.24), Inches(0.24))
mini_row.fill.solid(); mini_row.fill.fore_color.rgb = RGBColor(0x2A, 0x2A, 0x35)
mini_row.line.fill.background(); mini_row.shadow.inherit = False
mini_row.text_frame.margin_left = Inches(0.08)
r = mini_row.text_frame.paragraphs[0].add_run(); r.text = "Repeatability (§A.4.2): within tolerance"
r.font.size = Pt(8); r.font.color.rgb = RGBColor(0xC8, 0xC8, 0xD4); r.font.name = "Arial"
mini_chip = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, ss_left + Inches(0.12), ss_top + Inches(0.66), Inches(1.5), Inches(0.24))
mini_chip.fill.solid(); mini_chip.fill.fore_color.rgb = RGBColor(0x1E, 0x6B, 0x3A)
mini_chip.line.fill.background(); mini_chip.shadow.inherit = False
mini_chip.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
r = mini_chip.text_frame.paragraphs[0].add_run(); r.text = "● PASS"
r.font.size = Pt(8.5); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Arial"
wireframe_tag(s2, ui_left, ss_top + ss_h + Inches(0.02), ui_w)
ui_items = [
    ("\U0001F4CB", "Standardized Test Report"),
    ("⚖", "Compliance Verdict (Pass/Fail)"),
    ("\U0001F5C4", "Searchable Report Archive"),
    ("\U0001F510", "Role-Based Secure Access"),
]
uy = ss_top + ss_h + Inches(0.26)
for emoji, text in ui_items:
    icon_line(s2, ui_left + Inches(0.2), uy, ui_w - Inches(0.4), Inches(0.32), emoji, text, text_pt=11)
    uy += Inches(0.34)

flow_labels = ["CAPTURE", "VALIDATE", "CALCULATE", "VERIFY", "GENERATE"]
fw = Inches(2.37); fh = Inches(0.55); fgap = Inches(0.12)
fleft0 = Inches(0.5); ftop = fc_top + fc_h + Inches(0.35)
strip_bg = card(s2, Inches(0.4), ftop - Inches(0.1), Inches(12.53), fh + Inches(0.2), fill=DEEP_PURPLE)
for i, lab in enumerate(flow_labels):
    l = fleft0 + i * (fw + fgap)
    b = flow_chip(s2, l, ftop, fw, fh, lab, LILAC_BG if i % 2 == 0 else BLUE_BG, DEEP_PURPLE)
    if i < len(flow_labels) - 1:
        right_arrow(s2, l + fw + Inches(0.02), ftop + fh / 2 - Inches(0.08), fgap - Inches(0.04), Inches(0.16), color=WHITE)

# ================= SLIDE 3 : TECHNICAL APPROACH =================
s3 = slides[2]
clear_default_chrome(s3)
clear_footer(s3)
header_bar(s3, "Technical Approach")
subtitle_line(s3, "From manual test sheets to a standardized, rule-based compliance report.")
corner_deco_br(s3)

row1 = [
    ("\U0001F5C4", "Instrument &\nTest Data Entry", BLUE_BG, BLUE_LINE),
    ("\U0001F50D", "Data\nValidation", BLUE_BG, BLUE_LINE),
    ("\U0001F4E1", "Environmental &\nLab Conditions", BLUE_BG, BLUE_LINE),
    ("\u2696", "OIML R-76\nRule Engine", GREEN_BG, GREEN_LINE),
    ("\U0001F4CA", "Permissible Error\nCalculation", BLUE_BG, BLUE_LINE),
    ("\u2705", "Compliance\nEngine", ORANGE_BG, ORANGE_LINE),
    ("\U0001F4CB", "Report Template\nEngine", BLUE_BG, BLUE_LINE),
    ("\U0001F5A5", "MetroCert\nDashboard", LILAC_BG, LILAC_LINE),
]
rw = Inches(1.42); rh = Inches(0.95); rgap = Inches(0.14)
rleft0 = Inches(0.5); rtop1 = Inches(1.85)
xs = []
x = rleft0
for i, (emoji, lab, fill, line) in enumerate(row1):
    icon_chip(s3, x, rtop1, rw, rh, emoji, lab, fill, line)
    xs.append(x)
    if i < len(row1) - 1:
        right_arrow(s3, x + rw + Inches(0.01), rtop1 + rh / 2 - Inches(0.08), rgap - Inches(0.02), Inches(0.16), color=GREY)
    x += rw + rgap

sub_top = rtop1 + rh + Inches(0.3)
sub_items = [
    ("\U0001F4E1", "Repeatability\nTest (\u00A7A.4.2)"),
    ("\U0001F4C7", "Eccentricity\nLoading (\u00A7A.4.3)"),
    ("\u270D", "Discrimination\nTest"),
    ("\U0001F4C9", "Accuracy /\nLinearity"),
]
sub_w = Inches(2.95); sub_h = Inches(0.78); sub_gap = Inches(0.18)
sub_left0 = rleft0
for i, (emoji, lab) in enumerate(sub_items):
    l = sub_left0 + i * (sub_w + sub_gap)
    icon_chip(s3, l, sub_top, sub_w, sub_h, emoji, lab, BLUE_BG, BLUE_LINE)
down_arrow(s3, xs[3] + rw / 2 - Inches(0.1), rtop1 + rh + Inches(0.02), Inches(0.2), Inches(0.22), color=NAVY_CARD)

m_top = sub_top + sub_h + Inches(0.35)
mtitle = s3.shapes.add_textbox(Inches(0.5), m_top, Inches(3.0), Inches(0.3))
r = mtitle.text_frame.paragraphs[0].add_run(); r.text = "Key Metrics"
r.font.size = Pt(15); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Arial"

metrics3 = [
    ("R-76", "OIML standard\nfully digitized", LILAC_BG, PURPLE_NUM, LILAC_LINE),
    ("2", "Report formats\nPDF / DOCX", BLUE_BG, BLUE_NUM, BLUE_LINE),
    ("3", "User roles\nAdmin / Tester / Viewer", GREEN_BG, GREEN_NUM, GREEN_LINE),
    ("100%", "Digital — zero manual\nspreadsheets", ORANGE_BG, ORANGE_NUM, ORANGE_LINE),
]
mw3 = Inches(2.978); mh3 = Inches(0.85); mgap3 = Inches(0.14)
mtop2 = m_top + Inches(0.36)
for i, (num, lab, fill, numc, linec) in enumerate(metrics3):
    l = Inches(0.5) + i * (mw3 + mgap3)
    metric_tile(s3, l, mtop2, mw3, mh3, num, lab, fill, numc, linec)

ts_top = mtop2 + mh3 + Inches(0.25)
tstitle = s3.shapes.add_textbox(Inches(0.5), ts_top, Inches(3.0), Inches(0.3))
r = tstitle.text_frame.paragraphs[0].add_run(); r.text = "Technology Stack"
r.font.size = Pt(15); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Arial"
ts_body = card(s3, Inches(0.5), ts_top + Inches(0.36), Inches(12.33), Inches(0.42), fill=BLUE_BG)
ts_body.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
p = ts_body.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
r = p.add_run(); r.text = "React + TS  |  FastAPI  |  Python  |  PostgreSQL  |  ReportLab (PDF)  |  python-docx  |  Redis  |  Celery"
r.font.size = Pt(12); r.font.bold = True; r.font.color.rgb = NAVY_CARD; r.font.name = "Arial"

# ================= SLIDE 4 : FEASIBILITY AND VIABILITY =================
s4 = slides[3]
clear_default_chrome(s4)
clear_footer(s4)
header_bar(s4, "Feasibility and Viability")
subtitle_line(s4, "Real-world challenges, practical engineering responses, a clearly scoped build.")
corner_deco_br(s4)

ch_left = Inches(0.5); ch_top = Inches(1.75); ch_w = Inches(4.15); ch_gap = Inches(0.06)
resp_left = ch_left + ch_w + ch_gap; resp_w = Inches(4.15)
section_header_bar(s4, ch_left, ch_top, ch_w, Inches(0.38), "Challenge", DEEP_PURPLE)
section_header_bar(s4, resp_left, ch_top, resp_w, Inches(0.38), "Our Engineering Response", RGBColor(0x2E, 0x7B, 0xC7))

challenges = [
    ("\U0001F4C4", "Manual, error-prone\nspreadsheet process", "Digital data-entry forms with automated calculation and validation checks"),
    ("\u2696", "Complex OIML R-76 rules\napplied inconsistently", "Rule-based compliance engine encoding R-76 permissible-error tables directly"),
    ("\U0001F500", "Inconsistent report\nformats across labs", "Standardized template engine generating uniform PDF / DOCX reports"),
    ("\U0001F504", "Future OIML\nrecommendation revisions", "Versioned, configurable rule engine \u2014 rules stored as data, not hardcoded"),
    ("\U0001F512", "Sensitive lab &\nmanufacturer data", "Role-based access control with a full audit trail"),
]
row_h = Inches(0.56)
rt = ch_top + Inches(0.38)
for emoji, chal, resp in challenges:
    icon_line(s4, ch_left + Inches(0.08), rt + Inches(0.03), ch_w - Inches(0.5), row_h, emoji, chal, text_pt=9.5)
    right_arrow(s4, ch_left + ch_w - Inches(0.02), rt + row_h / 2 - Inches(0.09), Inches(0.14), Inches(0.18), color=GREY)
    rb = s4.shapes.add_textbox(resp_left + Inches(0.08), rt + Inches(0.03), resp_w - Inches(0.16), row_h)
    tf = rb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = resp
    r.font.size = Pt(9.5); r.font.color.rgb = BODY_INK; r.font.name = "Arial"
    line = s4.shapes.add_connector(1, ch_left, rt + row_h, resp_left + resp_w, rt + row_h)
    line.line.color.rgb = RGBColor(0xE3, 0xE3, 0xEE); line.line.width = Pt(0.75)
    rt += row_h

evid_left = resp_left + resp_w + Inches(0.15)
evid_w = Inches(13.333) - evid_left - Inches(0.5)
evid_hdr = section_header_bar(s4, evid_left, ch_top, evid_w, Inches(0.38), "Proposed Report Screen", RGBColor(0xE3, 0xE9, 0xF7))
evid_hdr.text_frame.paragraphs[0].runs[0].font.color.rgb = TITLE_INK
evid_body_h = Inches(2.58)
mock_report_form(s4, evid_left, ch_top + Inches(0.38), evid_w, evid_body_h)
wireframe_tag(s4, evid_left, ch_top + Inches(0.38) + evid_body_h + Inches(0.03), evid_w)

why_top = rt + Inches(0.15)
why_h = Inches(1.75)
why_w = resp_left + resp_w - ch_left
why_box = card(s4, ch_left, why_top, why_w, why_h, fill=WHITE, line_color=RGBColor(0xE3, 0xE3, 0xEE))
tf = why_box.text_frame
p0 = tf.paragraphs[0]
r0 = p0.add_run(); r0.text = "Why MetroCert is Feasible"
r0.font.size = Pt(13); r0.font.bold = True; r0.font.color.rgb = TITLE_INK; r0.font.name = "Arial"
feas_items = [
    "Built on a published, well-defined standard (OIML R-76)",
    "Deterministic, testable rule-based compliance engine",
    "Proven, off-the-shelf PDF / DOCX generation libraries",
    "Modular rule engine \u2014 ready for future OIML revisions",
    "Team has prior experience building evidence-driven systems",
]
for it in feas_items:
    p = tf.add_paragraph()
    r = p.add_run(); r.text = "\u2705 " + it
    r.font.size = Pt(10); r.font.color.rgb = BODY_INK; r.font.name = "Arial"

wp_left = evid_left
wp_top = ch_top + Inches(0.38) + evid_body_h + Inches(0.32)
wp_h = why_top + why_h - wp_top
wp = card(s4, wp_left, wp_top, evid_w, wp_h, fill=DEEP_PURPLE)
wp.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
p0 = wp.text_frame.paragraphs[0]; p0.alignment = PP_ALIGN.CENTER
r0 = p0.add_run(); r0.text = "PROPOSED SOLUTION"
r0.font.size = Pt(15); r0.font.bold = True; r0.font.color.rgb = WHITE; r0.font.name = "Arial"
p1 = wp.text_frame.add_paragraph(); p1.alignment = PP_ALIGN.CENTER
r1 = p1.add_run(); r1.text = "IDEA-STAGE SUBMISSION"
r1.font.size = Pt(10); r1.font.bold = True; r1.font.color.rgb = RGBColor(0xE6, 0xDC, 0xF7); r1.font.name = "Arial"

# ================= SLIDE 5 : IMPACT AND BENEFITS =================
s5 = slides[4]
clear_default_chrome(s5)
clear_footer(s5)
header_bar(s5, "Impact and Benefits")
subtitle_line(s5, "Transforming manual weighing-instrument compliance into a standardized digital process.")
corner_deco_br(s5)

flow5 = [
    ("Manual Spreadsheets\n+ Inconsistent\nReports", RGBColor(0xE6, 0xE6, 0xEE), TITLE_INK),
    ("MetroCert", DEEP_PURPLE, WHITE),
    ("Standardized\nDigital Reports", BLUE_BG, NAVY_CARD),
    ("Faster Model\nApproval", GREEN_BG, RGBColor(0x1E, 0x6B, 0x3A)),
    ("Stronger Consumer\nProtection", LILAC_BG, PURPLE_NUM),
]
fw5 = Inches(2.355); fh5 = Inches(0.85); fgap5 = Inches(0.14)
fleft5 = Inches(0.5); ftop5 = Inches(1.85)
x = fleft5
for i, (label, fill, tcolor) in enumerate(flow5):
    flow_chip(s5, x, ftop5, fw5, fh5, label, fill, tcolor)
    if i < len(flow5) - 1:
        right_arrow(s5, x + fw5 + Inches(0.01), ftop5 + fh5 / 2 - Inches(0.09), fgap5 - Inches(0.02), Inches(0.18), color=GREY)
    x += fw5 + fgap5

stakeholders = [
    ("⚖", "LEGAL METROLOGY LABS", ["Faster testing turnaround", "Automated calculations", "Standardized reports"], BLUE_LINE),
    ("\U0001F3DB", "MODEL APPROVAL AUTHORITY (DoCA)", ["Consistent compliance verdicts", "Audit-ready records", "Faster approvals"], BLUE_LINE),
    ("\U0001F3ED", "INSTRUMENT MANUFACTURERS", ["Faster time-to-market", "Clear compliance feedback", "Digital certificates"], GREEN_LINE),
    ("\U0001F465", "CONSUMERS & TRADE", ["More accurate instruments", "Stronger fair-trade protection", "Public trust in verification"], LILAC_LINE),
]
gw = Inches(2.993); gh = Inches(1.75); ggap = Inches(0.12)
gtop0 = ftop5 + fh5 + Inches(0.25)
for i, (emoji, title, items, line) in enumerate(stakeholders):
    l = Inches(0.5) + i * (gw + ggap)
    stakeholder_card(s5, l, gtop0, gw, gh, emoji, title, items, line)

ko_top = gtop0 + gh + Inches(0.25)
kotitle = s5.shapes.add_textbox(Inches(0.5), ko_top, Inches(3.0), Inches(0.3))
r = kotitle.text_frame.paragraphs[0].add_run(); r.text = "Key Outcomes"
r.font.size = Pt(15); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Arial"

outcomes = [
    ("R-76", "OIML standard\nfully digitized", LILAC_BG, PURPLE_NUM, LILAC_LINE),
    ("2", "Report export\nformats (PDF/DOCX)", BLUE_BG, BLUE_NUM, BLUE_LINE),
    ("100%", "Digital, searchable\nreport repository", GREEN_BG, GREEN_NUM, GREEN_LINE),
    ("3", "Role-based access\nlevels", ORANGE_BG, ORANGE_NUM, ORANGE_LINE),
]
ow = Inches(2.978); oh = Inches(0.85); ogap = Inches(0.14)
otop2 = ko_top + Inches(0.36)
for i, (num, lab, fill, numc, linec) in enumerate(outcomes):
    l = Inches(0.5) + i * (ow + ogap)
    metric_tile(s5, l, otop2, ow, oh, num, lab, fill, numc, linec)

# ================= SLIDE 6 : RESEARCH AND REFERENCES =================
s6 = slides[5]
clear_default_chrome(s6)
clear_footer(s6)
header_bar(s6, "Research and References")
subtitle_line(s6, "Built on the published Legal Metrology framework and the OIML R-76 standard.")
corner_deco_br(s6)

ref_cats = [
    ("\u2696", "LEGAL METROLOGY", ["Legal Metrology Act, 2009", "Legal Metrology (General) Rules, 2011"], BLUE_BG, BLUE_LINE),
    ("\U0001F4CF", "OIML STANDARDS", ["OIML R-76 Recommendation", "Permissible error tables"], GREEN_BG, GREEN_LINE),
    ("\U0001F4CB", "REPORT AUTOMATION", ["PDF / DOCX generation libraries", "Template-based reporting"], LILAC_BG, LILAC_LINE),
    ("\U0001F512", "SYSTEM DESIGN", ["Role-based access control", "Versioned, configurable rule engines"], BLUE_BG, BLUE_LINE),
]
rw6 = Inches(2.993); rh6 = Inches(1.15); rgap6 = Inches(0.12)
rleft6 = Inches(0.5); rtop6 = Inches(1.85)
for i, (emoji, title, items, fill, line) in enumerate(ref_cats):
    l = rleft6 + i * (rw6 + rgap6)
    ref_card(s6, l, rtop6, rw6, rh6, emoji, title, items, fill, line)

flow_left = Inches(0.5)
flow_w = Inches(2.1)
flow_top = rtop6 + rh6 + Inches(0.3)
flow_items = [
    ("Legal Metrology\nStandards", LILAC_BG),
    ("MetroCert\nRule Engine", LILAC_BG),
    ("Standardized\nCompliance Reports", GREEN_BG),
]
fh6 = Inches(0.85)
fy2 = flow_top
for i, (label, fill) in enumerate(flow_items):
    b = card(s6, flow_left, fy2, flow_w, fh6, fill=fill)
    tf = b.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for j, ln in enumerate(label.split("\n")):
        p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = ln
        r.font.size = Pt(11.5); r.font.bold = True; r.font.color.rgb = TITLE_INK; r.font.name = "Arial"
    if i < len(flow_items) - 1:
        down_arrow(s6, flow_left + flow_w / 2 - Inches(0.09), fy2 + fh6 + Inches(0.02), Inches(0.18), Inches(0.16), color=DEEP_PURPLE)
    fy2 += fh6 + Inches(0.28)

dash_left = flow_left + flow_w + Inches(0.35)
dash_w = Inches(13.333) - dash_left - Inches(0.5)
dash_hdr = section_header_bar(s6, dash_left, flow_top, dash_w, Inches(0.4), "MetroCert Dashboard (Proposed)", LILAC_BG)
dash_hdr.text_frame.paragraphs[0].runs[0].font.color.rgb = TITLE_INK
dash_body_top = flow_top + Inches(0.4)
dash_body_h = Inches(6.6) - dash_body_top - Inches(0.28)
mock_dashboard(s6, dash_left, dash_body_top, dash_w, dash_body_h)
wireframe_tag(s6, dash_left, dash_body_top + dash_body_h + Inches(0.04), dash_w)

# ================= delete instructions slide (per template's own rule) =================
delete_slide(prs, 6)

prs.save(OUT)
print("Saved:", OUT)
print("slides remaining:", len(prs.slides._sldIdLst))
