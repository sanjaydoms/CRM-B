import html
import pathlib
import re
import shutil
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
BUILD = HERE / "pdf-build"
MAX_RATIO = 1.3
OVERLAP = 24
TARGET_WIDTH = 1100



def prepare_image(src: pathlib.Path) -> list[pathlib.Path]:

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



def inline(text: str) -> str:

    spans: list[str] = []

    def stash(m):
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
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


CSS =

def build(md_path: pathlib.Path, out_pdf: pathlib.Path, title: str, subtitle: str):
    global BUILD
    BUILD = HERE / "pdf-build" / md_path.stem
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    md = md_path.read_text()
    md = re.sub(r"\A# .*?\n(?=---\n)", "", md, flags=re.S)
    body = convert(md)

    cover = f
    page = (f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style>{cover}{body}")
    (BUILD / "guide.html").write_text(page)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        pg = browser.new_page()
        pg.goto((BUILD / "guide.html").as_uri())
        pg.wait_for_timeout(2500)
        pg.emulate_media(media="print")
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
