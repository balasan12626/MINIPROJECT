# -*- coding: utf-8 -*-
import copy, json, os, re, shutil, sys, zipfile
from lxml import etree as ET
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content as K
import paths as P

SP = P.WORK.as_posix() + "/"
ROOT = P.ROOT.as_posix() + "/"
SRC = SP + "sample"
OUT_DIR = SP + "built"
# fresh unzip of the college sample every run (formatting comes only from this file)
if os.path.exists(SRC):
    shutil.rmtree(SRC)
with zipfile.ZipFile(P.SAMPLE) as z:
    z.extractall(SRC)
WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = "{%s}" % WNS
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

if os.path.exists(OUT_DIR):
    shutil.rmtree(OUT_DIR)
shutil.copytree(SRC, OUT_DIR)

# ---------------------------------------------------------------- exact table data from JSON
e4 = json.load(open(ROOT + "models/flood_evaluation_v4.json"))
meta4 = json.load(open(ROOT + "models/flood_model_metadata_v4.json"))
n_unseen = len(meta4["unseen_gauges"])
labels = {"logistic_regression": "Logistic regression", "random_forest": "Random forest", "hist_gradient_boosting": "Hist. gradient boosting",
          "xgboost_d4": "XGBoost depth 4", "xgboost_d6": "XGBoost depth 6", "xgboost_d8": "XGBoost depth 8",
          "xgboost_d6_full": "XGBoost depth 6, full refit (selected)"}
v4rows = []
for k, v in e4["candidates"].items():
    m = v["validation"]
    v4rows.append([labels.get(k, k)] + [f"{m[x]:.3f}" for x in ("balanced_accuracy", "recall", "precision", "roc_auc", "pr_auc")])
for i, b in enumerate(K.C):
    if b[0] == "tab" and b[1].startswith("Table 5.3"):
        K.C[i] = (b[0], b[1], b[2], v4rows, b[4])
t = e4["test"]["unseen_gauges_2015_2020"]["model"]
assert abs(t["balanced_accuracy"] - 0.8978) < 1e-3 and t["tp"] == 2609


def fix_text(s):
    return s.replace("49 unseen gauges", f"{n_unseen} unseen gauges")


# ---------------------------------------------------------------- citations
ref_index = {k: i + 1 for i, (k, _) in enumerate(K.REFS)}
used = set()


def cite(s):
    def rep(m):
        keys = [x.strip().lstrip("@") for x in m.group(1).split(",")]
        for k in keys:
            if k not in ref_index:
                raise KeyError(k)
            used.add(k)
        return "[" + ", ".join(str(ref_index[k]) for k in keys) + "]"
    return re.sub(r"\[(@[^\]]+)\]", rep, s)


# ---------------------------------------------------------------- xml helpers
def el(tag, attrib=None, *children):
    e = ET.Element(W + tag)
    for k, v in (attrib or {}).items():
        e.set(W + k, str(v))
    for c in children:
        if c is not None:
            e.append(c)
    return e


def rpr(bold=False, italic=False, sz=28, font=None, highlight=None, color=None, underline=False):
    r = el("rPr")
    if font:
        r.append(el("rFonts", {"ascii": font, "hAnsi": font, "cs": font, "eastAsia": font}))
    if bold:
        r.append(el("b")); r.append(el("bCs"))
    if italic:
        r.append(el("i")); r.append(el("iCs"))
    if color:
        r.append(el("color", {"val": color}))
    r.append(el("sz", {"val": sz})); r.append(el("szCs", {"val": sz}))
    if highlight:
        r.append(el("highlight", {"val": highlight}))
    if underline:
        r.append(el("u", {"val": "single"}))
    return r


def run(text, **kw):
    r = el("r")
    r.append(rpr(**kw))
    tt = el("t"); tt.text = text; tt.set(XML_SPACE, "preserve")
    r.append(tt)
    return r


def rich_runs(text, sz=28, bold=False, italic=False, font=None):
    """**bold** markup + citations."""
    text = cite(fix_text(text))
    out = []
    for i, part in enumerate(re.split(r"\*\*", text)):
        if part:
            out.append(run(part, sz=sz, bold=bold or (i % 2 == 1), italic=italic, font=font))
    return out


def ppr(jc=None, before=0, after=0, line=None, rule="auto", ind=None, outline=None, keep_next=False, page_break=False,
        style=None, num=None, keep_lines=False, shade=None, border=False, tabs=None):
    p = el("pPr")
    if style:
        p.append(el("pStyle", {"val": style}))
    if keep_next:
        p.append(el("keepNext"))
    if keep_lines:
        p.append(el("keepLines"))
    if page_break:
        p.append(el("pageBreakBefore"))
    if num:
        p.append(el("numPr", None, el("ilvl", {"val": 0}), el("numId", {"val": num})))
    if border:
        bd = el("pBdr")
        for side in ("top", "left", "bottom", "right"):
            bd.append(el(side, {"val": "single", "sz": 4, "space": 4, "color": "A6A6A6"}))
        p.append(bd)
    if shade:
        p.append(el("shd", {"val": "clear", "color": "auto", "fill": shade}))
    if tabs:
        tb = el("tabs")
        for tdef in tabs:
            tb.append(el("tab", tdef))
        p.append(tb)
    sp = {"before": before, "after": after}
    if line:
        sp["line"] = line; sp["lineRule"] = rule
    p.append(el("spacing", sp))
    if ind:
        p.append(el("ind", ind))
    if jc:
        p.append(el("jc", {"val": jc}))
    if outline is not None:
        p.append(el("outlineLvl", {"val": outline}))
    return p


def para(runs, **kw):
    p = el("p")
    p.append(ppr(**kw))
    for r in runs:
        p.append(r)
    return p


BODY = dict(jc="both", before=0, after=120, line=360)


def body_p(text):
    return para(rich_runs(text), **BODY)


# ---------------------------------------------------------------- numbering (bullets + decimal lists)
num_path = OUT_DIR + "/word/numbering.xml"
ntree = ET.parse(num_path); nroot = ntree.getroot()
abs_ids = [int(a.get(W + "abstractNumId")) for a in nroot.findall(W + "abstractNum")]
num_ids = [int(n.get(W + "numId")) for n in nroot.findall(W + "num")]
next_abs = max(abs_ids) + 1
next_num = max(num_ids) + 1


def make_abstract(aid, fmt, text, font=None):
    a = el("abstractNum", {"abstractNumId": aid})
    a.append(el("multiLevelType", {"val": "singleLevel"}))
    lvl = el("lvl", {"ilvl": 0})
    lvl.append(el("start", {"val": 1}))
    lvl.append(el("numFmt", {"val": fmt}))
    lvl.append(el("lvlText", {"val": text}))
    lvl.append(el("lvlJc", {"val": "left"}))
    lvl.append(el("pPr", None, el("ind", {"left": 720, "hanging": 360})))
    r = el("rPr")
    if font:
        r.append(el("rFonts", {"ascii": font, "hAnsi": font, "hint": "default"}))
    r.append(el("sz", {"val": 28}))
    lvl.append(r)
    a.append(lvl)
    return a


first_num = nroot.find(W + "num")
bul_abs = next_abs
nroot.insert(list(nroot).index(first_num), make_abstract(bul_abs, "bullet", "\u2022", "Symbol" if False else "Times New Roman"))
next_abs += 1
BULLET_NUM = next_num
nroot.append(el("num", {"numId": BULLET_NUM}, el("abstractNumId", {"val": bul_abs})))
next_num += 1
dec_abs_ids = []


def new_decimal_list():
    """Each numbered list restarts at 1 -> its own abstractNum."""
    global next_abs, next_num
    aid = next_abs; next_abs += 1
    nroot.insert(list(nroot).index(nroot.find(W + "num")), make_abstract(aid, "decimal", "%1."))
    nid = next_num; next_num += 1
    nroot.append(el("num", {"numId": nid}, el("abstractNumId", {"val": aid})))
    return nid


# ---------------------------------------------------------------- styles (TOC + captions)
st_path = OUT_DIR + "/word/styles.xml"
stree = ET.parse(st_path); sroot = stree.getroot()


def add_style(sid, name, ppr_el, rpr_el, ui=39):
    s = el("style", {"type": "paragraph", "styleId": sid})
    s.append(el("name", {"val": name}))
    s.append(el("basedOn", {"val": "Normal"}))
    s.append(el("next", {"val": "Normal"}))
    s.append(el("uiPriority", {"val": ui}))
    s.append(el("unhideWhenUsed"))
    s.append(el("qFormat"))
    s.append(ppr_el); s.append(rpr_el)
    sroot.append(s)


RIGHT_TAB = 9780
toc_tab = [{"val": "right", "leader": "dot", "pos": RIGHT_TAB}]
add_style("TOC1", "toc 1", ppr(before=120, after=40, tabs=toc_tab), rpr(bold=True, sz=24))
add_style("TOC2", "toc 2", ppr(before=0, after=30, ind={"left": 440}, tabs=toc_tab), rpr(sz=24))
add_style("TOC3", "toc 3", ppr(before=0, after=30, ind={"left": 880}, tabs=toc_tab), rpr(sz=24))
add_style("TOC9", "toc 9", ppr(before=0, after=80, tabs=toc_tab), rpr(sz=24))
add_style("FigureCaption", "Figure Caption", ppr(jc="center", before=60, after=240, keep_lines=True), rpr(bold=True, sz=24), ui=35)
add_style("CodeCaption", "Code Caption", ppr(jc="center", before=200, after=100, keep_next=True), rpr(bold=True, sz=24), ui=35)
add_style("TableCaption", "Table Caption", ppr(jc="center", before=200, after=100, keep_next=True), rpr(bold=True, sz=24), ui=35)
stree.write(st_path, xml_declaration=True, encoding="UTF-8", standalone=True)

# ---------------------------------------------------------------- images
rels_path = OUT_DIR + "/word/_rels/document.xml.rels"
rtree = ET.parse(rels_path); rroot = rtree.getroot()
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
rid_n = [100]
img_id = [500]


def add_image(fname):
    rid_n[0] += 1
    rid = f"rId{rid_n[0]}"
    shutil.copy(SP + "fig/" + fname, OUT_DIR + "/word/media/" + fname)
    r = ET.SubElement(rroot, PR + "Relationship")
    r.set("Id", rid)
    r.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")
    r.set("Target", "media/" + fname)
    return rid


def image_para(fname, width_in):
    rid = add_image(fname)
    w, h = Image.open(SP + "fig/" + fname).size
    cx = int(width_in * 914400); cy = int(cx * h / w)
    max_cy = int(8.3 * 914400)
    if cy > max_cy:
        cy = max_cy; cx = int(cy * w / h)
    img_id[0] += 1
    xml = f'''<w:r xmlns:w="{WNS}" xmlns:r="{RNS}"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">
<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{img_id[0]}" name="Picture {img_id[0]}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>
<pic:nvPicPr><pic:cNvPr id="{img_id[0]}" name="{fname}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'''
    r = ET.fromstring(xml)
    return para([r], jc="center", before=200, after=60, keep_next=True)


# ---------------------------------------------------------------- tables
TABLE_W = 9600


def table(head, rows, widths):
    scale = TABLE_W / sum(widths)
    widths = [int(w * scale) for w in widths]
    widths[-1] += TABLE_W - sum(widths)
    tbl = el("tbl")
    tp = el("tblPr")
    tp.append(el("tblW", {"w": TABLE_W, "type": "dxa"}))
    tp.append(el("jc", {"val": "center"}))
    b = el("tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b.append(el(side, {"val": "single", "sz": 4, "space": 0, "color": "000000"}))
    tp.append(b)
    tp.append(el("tblLayout", {"type": "fixed"}))
    cm = el("tblCellMar")
    for side, v in (("top", 50), ("left", 100), ("bottom", 50), ("right", 100)):
        cm.append(el(side, {"w": v, "type": "dxa"}))
    tp.append(cm)
    tbl.append(tp)
    g = el("tblGrid")
    for w in widths:
        g.append(el("gridCol", {"w": w}))
    tbl.append(g)
    for ri, row in enumerate([head] + rows):
        tr = el("tr")
        trp = el("trPr", None, el("cantSplit"))
        if ri == 0:
            trp.append(el("tblHeader"))
        tr.append(trp)
        for ci, cell in enumerate(row):
            tc = el("tc")
            tcp = el("tcPr", None, el("tcW", {"w": widths[ci], "type": "dxa"}))
            if ri == 0:
                tcp.append(el("shd", {"val": "clear", "color": "auto", "fill": "D9E2F3"}))
            tcp.append(el("vAlign", {"val": "center"}))
            tc.append(tcp)
            jc = "center" if (ri == 0 or (ci > 0 and re.fullmatch(r"[\d.,%–\- ]+", str(cell)))) else "left"
            tc.append(para(rich_runs(str(cell), sz=22, bold=(ri == 0)), jc=jc, before=0, after=0, line=240,
                           keep_next=(len(rows) <= 12 and ri < len(rows))))
            tr.append(tc)
        tbl.append(tr)
    return tbl


def caption(text, kind):
    return para([run(fix_text(text), sz=24, bold=True)], style={"fig": "FigureCaption", "tab": "TableCaption", "code": "CodeCaption"}[kind],
                jc="center", before=60 if kind == "fig" else 200, after=240 if kind == "fig" else 100, keep_next=(kind == "tab"))


# ---------------------------------------------------------------- build chapter blocks
def build_blocks(blocks):
    out = []
    first_h1 = True
    for b in blocks:
        k = b[0]
        if k == "h1":
            out.append(para([run(b[1], sz=28, bold=True)], before=0, after=240, line=360, outline=0, keep_next=True, page_break=True))
            first_h1 = False
        elif k == "h2":
            out.append(para([run(b[1], sz=28, bold=True)], before=240, after=120, line=360, outline=1, keep_next=True))
        elif k == "h3":
            out.append(para([run(b[1], sz=28, bold=True)], before=180, after=100, line=360, outline=2, keep_next=True))
        elif k == "p":
            out.append(body_p(b[1]))
        elif k in ("bul", "num"):
            nid = BULLET_NUM if k == "bul" else new_decimal_list()
            for item in b[1]:
                out.append(para(rich_runs(item), jc="both", before=0, after=80, line=360, num=nid, ind={"left": 720, "hanging": 360}))
        elif k == "eq":
            out.append(para([run(b[1], sz=26, italic=True)], jc="center", before=120, after=120, line=300))
        elif k == "fig" and not os.path.exists(SP + "fig/" + b[1]):
            print("WARNING: missing figure", b[1], "- inserting placeholder (run screenshots.mjs)")
            out.append(para([run("[Insert application screenshot here]", sz=24, italic=True, highlight="yellow")],
                            jc="center", before=240, after=60, keep_next=True, border=True))
            out.append(caption(b[2], "fig"))
        elif k == "fig":
            out.append(image_para(b[1], b[3]))
            out.append(caption(b[2], "fig"))
        elif k == "shot":
            out.append(para([run("[Insert application screenshot here]", sz=24, italic=True, highlight="yellow")],
                            jc="center", before=240, after=60, keep_next=True, border=True))
            out.append(caption(b[1], "fig"))
        elif k == "tab":
            out.append(caption(b[1], "tab"))
            out.append(table(b[2], b[3], b[4]))
            out.append(para([], before=0, after=120))
        elif k == "code":
            out.append(caption(b[1], "code"))
            for i, line in enumerate(b[2]):
                out.append(para([run(line if line else " ", sz=19, font="Courier New")], before=60 if i == 0 else 0,
                                after=60 if i == len(b[2]) - 1 else 0, line=240, shade="F2F2F2",
                                ind={"left": 284, "right": 284}, keep_next=(i < len(b[2]) - 1)))
            out.append(para([], before=0, after=60))
    return out


# ---------------------------------------------------------------- open document
doc_path = OUT_DIR + "/word/document.xml"
dtree = ET.parse(doc_path); droot = dtree.getroot()
body = droot.find(W + "body")
E = list(body)


def ptext(p):
    return "".join(x.text or "" for x in p.iter(W + "t"))


def strip_marks(r):
    rp = r.find(W + "rPr")
    if rp is not None:
        for tag in ("highlight", "color", "u"):
            for x in rp.findall(W + tag):
                rp.remove(x)


def set_text(p, text, keep_objects=True, highlight=None):
    """Replace the text of a template paragraph, keeping its pPr, first-run format and drawings."""
    text_runs = [r for r in p.findall(W + "r") if r.find(W + "t") is not None]
    for r in p.findall(W + "r"):
        if r.find(W + "t") is None and r.find(W + "tab") is not None and not keep_objects:
            p.remove(r)
    if not text_runs:
        p.append(run(text)); return
    first = text_runs[0]
    for r in text_runs[1:]:
        if r.find(".//" + W + "drawing") is None and r.find(".//" + W + "pict") is None:
            p.remove(r)
    for x in first.findall(W + "t")[1:]:
        first.remove(x)
    first.find(W + "t").text = text
    first.find(W + "t").set(XML_SPACE, "preserve")
    strip_marks(first)
    if highlight:
        first.find(W + "rPr").append(el("highlight", {"val": highlight}))


def replace_runs(p, runs):
    for r in list(p):
        if r.tag != W + "pPr":
            p.remove(r)
    for r in runs:
        p.append(r)


def clone_fmt_run(p, text, bold=None, highlight=None):
    """New run copying the first run's rPr of template paragraph p."""
    src = next((r for r in p.findall(W + "r") if r.find(W + "t") is not None), None)
    r = el("r")
    rp = copy.deepcopy(src.find(W + "rPr")) if src is not None and src.find(W + "rPr") is not None else el("rPr")
    for tag in ("highlight", "color", "u", "spacing", "w"):
        for x in rp.findall(W + tag):
            rp.remove(x)
    if bold is True and rp.find(W + "b") is None:
        rp.insert(0, el("b"))
    if bold is False:
        for x in rp.findall(W + "b"):
            rp.remove(x)
    if highlight:
        rp.append(el("highlight", {"val": highlight}))
    r.append(rp)
    tt = el("t"); tt.text = text; tt.set(XML_SPACE, "preserve"); r.append(tt)
    return r


# ---- front matter: inline heading styles so cover/certificate lines stay out of the TOC
styles_by_id = {s_.get(W + "styleId"): s_ for s_ in sroot.findall(W + "style")}
for p_ in E[:78]:
    for pp in ([p_] if p_.tag == W + "p" else list(p_.iter(W + "p"))):
        pPr = pp.find(W + "pPr")
        ps = pPr.find(W + "pStyle") if pPr is not None else None
        if ps is None or not ps.get(W + "val", "").startswith("Heading"):
            continue
        sdef = styles_by_id[ps.get(W + "val")]
        spp = sdef.find(W + "pPr"); srp = sdef.find(W + "rPr")
        pPr.remove(ps)
        if spp is not None:
            for child in spp:
                if child.tag == W + "outlineLvl":
                    continue
                if pPr.find(child.tag) is None:
                    pPr.append(copy.deepcopy(child))
        for r_ in pp.findall(W + "r"):
            rp = r_.find(W + "rPr")
            if rp is None:
                rp = el("rPr"); r_.insert(0, rp)
            if srp is not None:
                for child in srp:
                    if rp.find(child.tag) is None:
                        rp.append(copy.deepcopy(child))
# tighten blank spacers on the cover so it stays on one page
for p_ in E[1:28]:
    if p_.tag != W + "p" or ptext(p_).strip():
        continue
    spc = p_.find(W + "pPr/" + W + "spacing")
    if spc is not None and spc.get(W + "before"):
        spc.set(W + "before", str(int(int(spc.get(W + "before")) * 0.4)))

# ---- cover
STUDENTS = K.STUDENTS
MENTOR = K.SUPERVISOR
set_text(E[0], K.TITLE)
set_text(E[6], K.COURSE)
tbl = E[13]
# widen the name column so long names stay on one line
tbl.find(W + "tblPr/" + W + "tblInd").set(W + "w", "700")
for gc, wv in zip(tbl.find(W + "tblGrid").findall(W + "gridCol"), (5000, 2900)):
    gc.set(W + "w", str(wv))
for tr in tbl.findall(W + "tr"):
    for tc, wv in zip(tr.findall(W + "tc"), (5000, 2900)):
        tc.find(W + "tcPr/" + W + "tcW").set(W + "w", str(wv))
for i, tr in enumerate(tbl.findall(W + "tr")):
    cells = tr.findall(W + "tc")
    for j, tc in enumerate(cells):
        p0 = tc.find(".//" + W + "p")
        set_text(p0, STUDENTS[i][0] if j == 0 else f"({STUDENTS[i][1]})")
set_text(E[23], K.DEPARTMENT)

# ---- bonafide
names = ", ".join(f"{n} ({r})" for n, r in STUDENTS)
bp = E[34]
replace_runs(bp, [clone_fmt_run(bp, "Certified that this project titled ", bold=False),
                  clone_fmt_run(bp, "“" + K.TITLE + "”", bold=True),
                  clone_fmt_run(bp, " is the bonafide work of ", bold=False),
                  clone_fmt_run(bp, "“" + names + "”", bold=True),
                  clone_fmt_run(bp, " who carried out the project work " + K.COURSE + " under my supervision.", bold=False)])
def tab_run(p):
    src = next((r for r in p.findall(W + "r") if r.find(W + "t") is not None), None)
    r = el("r")
    if src is not None and src.find(W + "rPr") is not None:
        r.append(copy.deepcopy(src.find(W + "rPr")))
    r.append(el("tab"))
    return r


sig = E[39]
replace_runs(sig, [clone_fmt_run(sig, MENTOR, bold=True), tab_run(sig), clone_fmt_run(sig, K.HOD, bold=True)])
dep = E[41]
replace_runs(dep, [clone_fmt_run(dep, K.DEPARTMENT, bold=False), tab_run(dep),
                   clone_fmt_run(dep, K.DEPARTMENT, bold=False)])
des = E[40]
replace_runs(des, [clone_fmt_run(des, K.SUPERVISOR_DESIGNATION, bold=False), tab_run(des),
                   clone_fmt_run(des, K.HOD_DESIGNATION, bold=False)])
gd = E[66]
replace_runs(gd, [clone_fmt_run(gd, "is an original work carried out by us under the guidance of ", bold=False),
                  clone_fmt_run(gd, K.SUPERVISOR_IN_TEXT, bold=True), clone_fmt_run(gd, ".", bold=False)])
for ri, tr in enumerate(E[73].findall(W + "tr")[1:]):
    cells = tr.findall(W + "tc")
    for ci, val in ((1, STUDENTS[ri][1]), (2, STUDENTS[ri][0])):
        cp = cells[ci].find(W + "p")
        for r in cp.findall(W + "r"):
            cp.remove(r)
        ppr_ = cp.find(W + "pPr")
        if ppr_ is None:
            ppr_ = el("pPr"); cp.insert(0, ppr_)
        for x in ppr_.findall(W + "ind"):
            ppr_.remove(x)
        ppr_.append(el("ind", {"left": 80}))
        cp.append(run(val, sz=24))

# ---- declaration
dp = E[65]
replace_runs(dp, [clone_fmt_run(dp, "We hereby declare that the project titled ", bold=False),
                  clone_fmt_run(dp, "“" + K.TITLE + "”", bold=True)])
sp = E[69]
replace_runs(sp, [clone_fmt_run(sp, "We also affirm that all the data and information used in this project are genuine and properly acknowledged. This project work is carried out with reference to the United Nations Sustainable Development Goals ", bold=False),
                  clone_fmt_run(sp, "SDG 11 – Sustainable Cities and Communities and SDG 13 – Climate Action.", bold=True)])
for el_ in E[59].iter(W + "r"):
    strip_marks(el_)

# ---- acknowledgment / abstract
def replace_with(anchor, new_elems):
    parent = anchor.getparent(); idx = parent.index(anchor)
    parent.remove(anchor)
    for k, ne in enumerate(new_elems):
        parent.insert(idx + k, ne)


set_text(E[78], "ACKNOWLEDGMENT")
E[78].find(W + "pPr").append(el("jc", {"val": "center"})) if E[78].find(W + "pPr").find(W + "jc") is None else None
replace_with(E[79], [para(rich_runs(t), jc="both", before=0, after=160, line=360) for t in K.ACK])
E[81].find(W + "pPr").append(el("jc", {"val": "center"})) if E[81].find(W + "pPr").find(W + "jc") is None else None
abs_paras = []
for t in K.ABSTRACT:
    if t.startswith("Keywords:"):
        abs_paras.append(para([run("Keywords: ", bold=True), run(t[len("Keywords: "):], italic=True)], jc="both", before=120, after=0, line=360))
    else:
        abs_paras.append(para(rich_runs(t), jc="both", before=0, after=160, line=360))
replace_with(E[82], abs_paras)


# ---- TOC / LoF / LoT fields
def field_paras(instr, placeholder="Right-click and choose Update Field to refresh."):
    p1 = el("p"); p1.append(ppr(before=120, after=0))
    r = el("r"); r.append(el("fldChar", {"fldCharType": "begin"})); p1.append(r)
    r = el("r"); it = el("instrText"); it.text = f" {instr} "; it.set(XML_SPACE, "preserve"); r.append(it); p1.append(r)
    r = el("r"); r.append(el("fldChar", {"fldCharType": "separate"})); p1.append(r)
    p1.append(run(placeholder, sz=24))
    r = el("r"); r.append(el("fldChar", {"fldCharType": "end"})); p1.append(r)
    return [p1]


for i in range(86, 144):
    body.remove(E[i])
replace_with(E[85], field_paras('TOC \\o "1-3" \\h \\z \\u'))
replace_with(E[146], field_paras('TOC \\h \\z \\t "Figure Caption,9"'))
replace_with(E[149], field_paras('TOC \\h \\z \\t "Table Caption,9"'))
abbrev_tbl = table(["Abbreviation", "Expansion"], [[a, b] for a, b in K.ABBREV], [2600, 7000])
replace_with(E[152], [para([], before=120, after=0), abbrev_tbl])

# ---- chapters: remove template chapter content 153..261, insert ours before sectPr paragraph 262
for i in range(153, 262):
    body.remove(E[i])
idx = body.index(E[262])
for k, ne in enumerate(build_blocks(K.C)):
    body.insert(idx + k, ne)

# ---- SDG page
set_text(E[263], "SDG GOALS")
E[263].find(W + "pPr").append(el("outlineLvl", {"val": 0}))
sdg = [para([], before=0, after=120)]
for kind, txt in K.SDG:
    if kind == "b":
        sdg.append(para([run(txt, bold=True)], before=200, after=80, line=360, keep_next=True))
    else:
        sdg.append(para(rich_runs(txt), jc="both", before=0, after=100, line=360))
idx = body.index(E[264])
for k, ne in enumerate(sdg):
    body.insert(idx + k, ne)

# ---- publications
set_text(E[265], "PUBLICATIONS")
E[265].find(W + "pPr").append(el("outlineLvl", {"val": 0}))
set_text(E[266], "")
E[266].addnext(para([run("Nil – no publication has been made from this work at the time of submission.", sz=28)], jc="both", before=240, after=0, line=360))
for i in range(267, 310):
    body.remove(E[i])

# ---- references
set_text(E[310], "REFERENCES")
rp_ = E[310].find(W + "pPr")
rp_.insert(0, el("pageBreakBefore"))
rp_.append(el("outlineLvl", {"val": 0}))
refs = []
for i, (key, txt) in enumerate(K.REFS):
    refs.append(para([run(f"[{i + 1}]", sz=24), run("\t" + txt, sz=24)], jc="both", before=0, after=120, line=276,
                     ind={"left": 567, "hanging": 567}, tabs=[{"val": "left", "pos": 567}]))
idx = body.index(E[311])
for k, ne in enumerate(refs):
    body.insert(idx + 1 + k, ne)

# ---- drop template instructions / samples; move last section properties to body
last_sect = copy.deepcopy(E[312].find(".//" + W + "sectPr"))
for i in range(312, 478):
    body.remove(E[i])
body.remove(E[478])
body.append(last_sect)

# remove E[261]-style empty page-break paragraph before chapter sectPr was already deleted; remove BR before ch1
# ensure cover/front-matter page breaks remain

# ---- strip any remaining red colour / highlights outside placeholders in front matter
for r in body.iter(W + "r"):
    rp = r.find(W + "rPr")
    if rp is None:
        continue
    for c in rp.findall(W + "color"):
        if c.get(W + "val", "").upper() in ("FF0000", "C00000", "E36C09"):
            rp.remove(c)
    hl = rp.find(W + "highlight")
    if hl is not None:
        txt = "".join(t.text or "" for t in r.findall(W + "t"))
        if not any(s in txt for s in ("STUDENT NAME", "REGISTER NUMBER", "Register No.", "Faculty Name", "Designation", "Department>", "Insert application")):
            rp.remove(hl)

for rf in body.iter(W + "rFonts"):
    if rf.get(W + "ascii") == "Calibri":
        for k in ("ascii", "hAnsi", "cs", "eastAsia"):
            rf.set(W + k, "Times New Roman")
dtree.write(doc_path, xml_declaration=True, encoding="UTF-8", standalone=True)
ntree.write(num_path, xml_declaration=True, encoding="UTF-8", standalone=True)
rtree.write(rels_path, xml_declaration=True, encoding="UTF-8", standalone=True)

ct_path = OUT_DIR + "/[Content_Types].xml"
ct = open(ct_path, encoding="utf-8").read()
if 'Extension="png"' not in ct:
    ct = ct.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
open(ct_path, "w", encoding="utf-8").write(ct)

# drop unused hyperlink rels to template sample sites
rt = ET.parse(rels_path); rr = rt.getroot()
docxml = open(doc_path, encoding="utf-8").read()
for r in list(rr):
    if r.get("TargetMode") == "External" and f'"{r.get("Id")}"' not in docxml:
        rr.remove(r)
rt.write(rels_path, xml_declaration=True, encoding="UTF-8", standalone=True)

out = SP + "report_raw.docx"
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for folder, _, files in os.walk(OUT_DIR):
        for f in files:
            full = os.path.join(folder, f)
            arc = os.path.relpath(full, OUT_DIR).replace("\\", "/")
            z.write(full, arc)
unused = [k for k, _ in K.REFS if k not in used]
print("built", out, "unseen gauges:", n_unseen, "refs:", len(K.REFS), "uncited:", unused)
