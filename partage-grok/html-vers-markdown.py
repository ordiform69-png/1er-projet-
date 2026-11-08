"""Convertit guide-survie.html en Markdown lisible (illustrations décrites par leur texte alternatif)."""
import sys
from bs4 import BeautifulSoup, NavigableString, Tag

src, dst = sys.argv[1], sys.argv[2]
soup = BeautifulSoup(open(src, encoding="utf-8").read(), "html.parser")


def inline(node):
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            out.append(str(c))
        elif c.name in ("b", "strong"):
            t = inline(c).strip()
            out.append(f"**{t}**" if t else "")
        elif c.name in ("i", "em"):
            out.append(f"*{inline(c).strip()}*")
        elif c.name == "sup":
            out.append(inline(c))
        elif c.name == "br":
            out.append(" ")
        elif c.name in ("ol", "ul"):
            continue
        else:
            out.append(inline(c))
    return " ".join("".join(out).split())


def block(node, lines, depth=0):
    for c in node.children:
        if not isinstance(c, Tag):
            continue
        n = c.name
        if n == "h1":
            lines += [f"# {inline(c)}", ""]
        elif n == "h2":
            lines += [f"## {inline(c)}", ""]
        elif n == "h3":
            lines += [f"### {inline(c)}", ""]
        elif n == "h4":
            lines += [f"#### {inline(c)}", ""]
        elif n == "p":
            t = inline(c)
            if t:
                lines += [t, ""]
        elif n in ("ul", "ol"):
            check = "check" in (c.get("class") or [])
            for i, li in enumerate(c.find_all("li", recursive=False), 1):
                mark = "- [ ]" if check else ("-" if n == "ul" else f"{i}.")
                lines.append("  " * depth + f"{mark} {inline(li)}")
                for sub in li.find_all(["ul", "ol"], recursive=False):
                    block(Tag(name="div", builder=soup.builder) if False else _wrap(sub), lines, depth + 1)
            lines.append("")
        elif n == "table":
            rows = c.find_all("tr")
            cells = [[inline(x).replace("|", "/") for x in r.find_all(["th", "td"])] for r in rows]
            width = max(len(r) for r in cells)
            cells = [r + [""] * (width - len(r)) for r in cells]
            if rows[0].find("td"):
                cells.insert(0, [""] * width)
            lines.append("| " + " | ".join(cells[0]) + " |")
            lines.append("|" + "---|" * width)
            for r in cells[1:]:
                lines.append("| " + " | ".join(r) + " |")
            lines.append("")
        elif n == "figure":
            svg = c.find("svg")
            alt = svg.get("aria-label") if svg else None
            cap = c.find("figcaption")
            if not alt:
                continue
            desc = alt
            lines.append(f"> 🖼 *Illustration : {desc}.*" + (f" {inline(cap)}" if cap else ""))
            lines.append("")
        elif n == "div" and "box" in (c.get("class") or []):
            title = c.find("strong")
            t = inline(title) if title else ""
            if title:
                title.extract()
            body = []
            block(c, body)
            text = inline(c) if not body else None
            lines.append(f"> **{t}**" if t else ">")
            for l in (body or [text]):
                lines.append(f"> {l}" if l else ">")
            lines.append("")
        elif n in ("div", "nav", "section"):
            block(c, lines, depth)


def _wrap(tag):
    w = soup.new_tag("div")
    w.append(tag.__copy__())
    return w


lines = []
for sec in soup.body.find_all("section", recursive=False):
    block(sec, lines)
    lines += ["---", ""]

text = "\n".join(lines)
while "\n\n\n" in text:
    text = text.replace("\n\n\n", "\n\n")
open(dst, "w", encoding="utf-8").write(text.strip() + "\n")
print(len(text), "caractères,", text.count("\n"), "lignes")
