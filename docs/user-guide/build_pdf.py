#!/usr/bin/env python3
"""Render the User Guide markdown into a printable, screenshot-rich PDF.

    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
        docs/user-guide/build_pdf.py

Two jobs that a generic markdown-to-PDF tool does badly, and which are the
reason this script exists:

**Tall screenshots.** Every capture is full-page, and some are 4,700 px tall.
Scaled to a page width they become an unreadable ribbon; left alone the printer
slices them mid-sentence. So an image taller than `MAX_RATIO` times its width is
cut into page-shaped slices here, and laid out as consecutive figures.

**Page discipline.** A screenshot and the paragraph explaining it must not be
separated, and a new chapter starts on a new page.

The markdown reader below understands only the subset used by this guide --
headings, paragraphs, fenced code, tables, lists, block quotes, images, links,
bold, italic and inline code. That is deliberate: the alternative was a
dependency for a document that only ever has one author.
"""
import html
import pathlib
import re
import shutil
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
#: Per-document, so rebuilding one guide cannot delete the other's images.
BUILD = HERE / "pdf-build"
#: An image taller than this many times its width is sliced.
MAX_RATIO = 1.3
#: Slices overlap slightly so nothing is lost on the cut line.
OVERLAP = 24
#: Screenshots are captured at 1440 px; halving keeps them sharp in print
#: without carrying 21 MB of pixels into the document.
TARGET_WIDTH = 1100


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------

def prepare_image(src: pathlib.Path) -> list[pathlib.Path]:
    """Return the print-ready pieces of one screenshot, in order."""
    out_dir = BUILD / "img"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = str(src.relative_to(HERE / "screenshots")).replace("/", "_")[:-4]

    with Image.open(src) as im:
        im = im.convert("RGB")
        if im.width > TARGET_WIDTH:
            im = im.resize(
                (TARGET_WIDTH, round(im.height * TARGET_WIDTH / im.width)),
                Image.LANCZOS,
            )
        limit = round(im.width * MAX_RATIO)
        if im.height <= limit:
            path = out_dir / f"{stem}.jpg"
            im.save(path, "JPEG", quality=88)
            return [path]

        # Equal slices rather than fill-then-remainder: the remainder was
        # regularly a 200 px sliver that took a whole page to itself.
        count = -(-im.height // limit)
        step = -(-im.height // count)
        pieces = []
        for index in range(count):
            top = max(0, index * step - OVERLAP)
            bottom = min(im.height, (index + 1) * step)
            path = out_dir / f"{stem}-{index + 1}.jpg"
            im.crop((0, top, im.width, bottom)).save(path, "JPEG", quality=88)
            pieces.append(path)
        return pieces


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

def inline(text: str) -> str:
    """Inline markdown -> HTML. Code spans are protected from the rest."""
    spans: list[str] = []

    def stash(m):
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # Internal anchors stay as text. A link to a screenshot names the file
    # instead, since a printed page cannot follow it into the repository.
    text = re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(screenshots/([^)]+)\)",
                  r'\1 <span class="shot">\2</span>', text)
    text = re.sub(r"\[([^\]]+)\]\(([A-Za-z0-9_.-]+\.(?:md|py))\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>", text)


def table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]
    out = ["<table><thead><tr>"]
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def convert(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    list_open = None

    def close_list():
        nonlocal list_open
        if list_open:
            out.append(f"</{list_open}>")
            list_open = None

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            close_list()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(html.escape(lines[i]))
                i += 1
            out.append("<pre>" + "\n".join(buf) + "</pre>")
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            close_list()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(table(rows))
            continue

        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", line)
        if m:
            close_list()
            src = HERE / m.group(2)
            for n, piece in enumerate(prepare_image(src)):
                suffix = "" if n == 0 else " (continued)"
                out.append(
                    f'<figure><img src="img/{piece.name}" alt="{html.escape(m.group(1))}">'
                    f"<figcaption>{inline(m.group(1))}{suffix}</figcaption></figure>"
                )
            i += 1
            continue

        if line.startswith(">"):
            close_list()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(buf))}</blockquote>")
            continue

        if list_open and re.match(r"^\s+\S", line) and out and out[-1].startswith("<li>"):
            out[-1] = out[-1][:-len("</li>")] + " " + inline(line.strip()) + "</li>"
            i += 1
            continue

        m = re.match(r"^(\d+)\.\s+(.*)", line)
        if m:
            if list_open != "ol":
                close_list()
                out.append("<ol>")
                list_open = "ol"
            out.append(f"<li>{inline(m.group(2))}</li>")
            i += 1
            continue

        m = re.match(r"^[-*]\s+(.*)", line)
        if m:
            if list_open != "ul":
                close_list()
                out.append("<ul>")
                list_open = "ul"
            out.append(f"<li>{inline(m.group(1))}</li>")
            i += 1
            continue

        if line.strip() in ("---", "***"):
            close_list()
            i += 1
            continue

        if not line.strip():
            close_list()
            i += 1
            continue

        close_list()
        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,4} |\||!\[|>|```|\d+\.\s|[-*]\s|---$)", lines[i]):
            buf.append(lines[i])
            i += 1
        text = inline(" ".join(buf))
        cls = ' class="figlead"' if text.startswith("<strong>Figure") else ""
        out.append(f"<p{cls}>{text}</p>")

    close_list()
    return "\n".join(out)


CSS = """
@page { size: A4; margin: 18mm 16mm 20mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.55 "Helvetica Neue", Helvetica, Arial, sans-serif;
       color: #1c2321; margin: 0; }
h1, h2, h3, h4 { color: #0f291e; line-height: 1.25; margin: 0 0 .4em; }
h1 { font-size: 22pt; }
h2 { font-size: 16pt; margin-top: 0; padding-top: 0;
     border-bottom: 2px solid #c9a227; padding-bottom: .25em;
     break-before: page; }
h2:first-of-type { break-before: avoid; }
h3 { font-size: 12.5pt; margin-top: 1.4em; color: #1c4433; }
h4 { font-size: 11pt; margin-top: 1.1em; }
h2, h3, h4 { break-after: avoid; }
p, li { orphans: 3; widows: 3; }
p { margin: 0 0 .7em; }
ul, ol { margin: 0 0 .8em; padding-left: 1.3em; }
li { margin-bottom: .25em; }
a { color: #1c4433; text-decoration: none; }
code { font: 9pt/1.4 "SF Mono", Menlo, Consolas, monospace;
       background: #f4f2ec; padding: .1em .35em; border-radius: 3px; }
pre { font: 8.5pt/1.45 "SF Mono", Menlo, Consolas, monospace;
      background: #f7f6f2; border: 1px solid #e4e0d5; border-left: 3px solid #c9a227;
      padding: 10px 12px; border-radius: 4px; white-space: pre; overflow: hidden;
      break-inside: avoid; margin: 0 0 1em; }
blockquote { margin: 0 0 1em; padding: 10px 14px; background: #fdf8ec;
             border-left: 3px solid #c9a227; break-inside: avoid; font-size: 10pt; }
table { border-collapse: collapse; width: 100%; margin: 0 0 1.1em;
        font-size: 9pt; break-inside: avoid; }
th, td { border: 1px solid #ded9cc; padding: 5px 7px; text-align: left;
         vertical-align: top; }
th { background: #f2efe6; font-weight: 600; }
figure { margin: 0 0 1.2em; break-inside: avoid; text-align: center; }
p.figlead { break-after: avoid; margin-bottom: .45em; }
figure img { max-width: 100%; max-height: 190mm; border: 1px solid #ded9cc;
             border-radius: 4px; }
figcaption { font-size: 8.5pt; color: #6a6a63; margin-top: .4em; font-style: italic; }
.cover { height: 245mm; display: flex; flex-direction: column; justify-content: center;
         text-align: center; break-after: page; }
.cover .brand { font-size: 13pt; letter-spacing: .32em; color: #6a6a63; }
.cover h1 { font-size: 34pt; margin: .35em 0 .2em; border: 0; }
.cover .sub { font-size: 13pt; color: #444; margin-bottom: 2.5em; }
.cover .meta { font-size: 10pt; color: #6a6a63; line-height: 1.9; }
.cover .rule { width: 70px; height: 3px; background: #c9a227; margin: 1.5em auto; }
.shot { font: 8pt "SF Mono", Menlo, Consolas, monospace; color: #8a8a82; }
.shot::before { content: "["; } .shot::after { content: "]"; }
"""


def build(md_path: pathlib.Path, out_pdf: pathlib.Path, title: str, subtitle: str):
    global BUILD
    BUILD = HERE / "pdf-build" / md_path.stem
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    md = md_path.read_text()
    # The cover carries the title and the provenance block, so drop them from
    # the body rather than printing them twice.
    md = re.sub(r"\A# .*?\n(?=---\n)", "", md, flags=re.S)
    body = convert(md)

    cover = f"""
    <div class="cover">
      <div class="brand">SCALEEZY</div>
      <h1>{html.escape(title)}</h1>
      <div class="rule"></div>
      <div class="sub">{html.escape(subtitle)}</div>
      <div class="meta">
        Documented from the running product<br>
        Branch <b>MSK-CL</b> · commit <b>ccfed28</b><br>
        Captured 27 August 2026<br>
        Demo boutique: Kanchi Threads, Chennai
      </div>
    </div>"""

    page = (f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style>{cover}{body}")
    (BUILD / "guide.html").write_text(page)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        pg = browser.new_page()
        pg.goto((BUILD / "guide.html").as_uri())
        pg.wait_for_timeout(2500)
        pg.emulate_media(media="print")
        # Chromium can build a clickable bookmark tree from the headings, which
        # is the only navigation a long PDF really has. Older Playwright builds
        # do not expose it, so it is optional rather than assumed.
        outline_kwargs = {"outline": True}
        try:
            import inspect
            if "outline" not in inspect.signature(pg.pdf).parameters:
                outline_kwargs = {}
        except (TypeError, ValueError):
            outline_kwargs = {}
        pg.pdf(
            path=str(out_pdf),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=(
                "<div style='width:100%;font-size:7.5pt;color:#8a8a82;"
                "padding:0 16mm;display:flex;justify-content:space-between;'>"
                f"<span>{html.escape(title)}</span>"
                "<span class='pageNumber'></span></div>"
            ),
            margin={"top": "16mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
            **outline_kwargs,
        )
        browser.close()
    print(f"{out_pdf}  ({out_pdf.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    jobs = {
        "guide": (HERE / "README.md", HERE / "Boutique-CRM-User-Guide.pdf",
                  "Boutique CRM — User Guide",
                  "How to use the product, screen by screen, for every role"),
        "demo": (HERE / "demo-guide.md", HERE / "Boutique-CRM-Demo-Guide.pdf",
                 "Boutique CRM — Demo Guide",
                 "What to show, what to say, what to click"),
    }
    for name in (sys.argv[1:] or jobs):
        build(*jobs[name])
