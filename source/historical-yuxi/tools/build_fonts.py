"""
羽析 · 生成前端字体 (只需在改了界面文字后重新运行)

    .venv/bin/python tools/build_fonts.py

从 Google Fonts 下载开源字体 (均为 SIL Open Font License), 按页面实际用到的字符做子集,
输出 frontend/fonts/*.woff2 与 frontend/fonts/fonts.css。需要 fonttools + brotli:
    .venv/bin/python -m pip install fonttools brotli -i https://pypi.tuna.tsinghua.edu.cn/simple
"""
import os
import re
import sys
import urllib.request

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(ROOT, "frontend")
OUT = os.path.join(FRONT, "fonts")
CACHE = os.path.join(ROOT, "tools", ".font_cache")
UA = "Mozilla/4.0"   # 旧 UA 让 Google Fonts 返回完整 TTF (而不是按 unicode-range 切片)

# (CSS 字体名, Google Fonts family 参数, 字重, 斜体, 输出文件名, 字符集)
FACES = [
    ("Instrument Serif", "Instrument+Serif:ital@0;1", 400, False, "instrument-serif-400", "latin"),
    ("Instrument Serif", "Instrument+Serif:ital@0;1", 400, True, "instrument-serif-400-italic", "latin"),
    ("IBM Plex Mono", "IBM+Plex+Mono:wght@400;500", 400, False, "ibm-plex-mono-400", "latin"),
    ("IBM Plex Mono", "IBM+Plex+Mono:wght@400;500", 500, False, "ibm-plex-mono-500", "latin"),
    ("Inter", "Inter:wght@400;500", 400, False, "inter-400", "latin"),
    ("Inter", "Inter:wght@400;500", 500, False, "inter-500", "latin"),
    ("YX Serif SC", "Noto+Serif+SC:wght@500", 500, False, "noto-serif-sc-500", "cjk"),
]


def fetch(url, dest=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
    return data


def ttf_url(family_q, weight, italic):
    css = fetch(f"https://fonts.googleapis.com/css2?family={family_q}&display=swap").decode()
    for block in re.findall(r"@font-face\s*\{[^}]*\}", css):
        st = "italic" if italic else "normal"
        if f"font-style: {st}" in block and f"font-weight: {weight}" in block:
            return re.search(r"url\((https://[^)]+)\)", block).group(1)
    raise SystemExit(f"找不到 {family_q} {weight} {'italic' if italic else ''}")


def page_text():
    txt = ""
    for fn in os.listdir(FRONT):
        if fn.endswith((".js", ".html", ".css")):
            txt += open(os.path.join(FRONT, fn), encoding="utf-8").read()
    return txt


def gb2312_level1():
    out = []
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return "".join(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    src = page_text()
    latin = "".join(chr(c) for c in range(0x20, 0x7F)) + "·—–’‘“”…×✓•→←€©°±"
    cjk = "".join(sorted(set(ch for ch in src if "　" <= ch <= "鿿" or "＀" <= ch <= "￯")))
    cjk += gb2312_level1() + "，。、：；？！（）《》「」·—…0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    css = ["/* 由 tools/build_fonts.py 生成, 字体均为 SIL Open Font License */"]
    for name, fam, w, it, stem, kind in FACES:
        raw = os.path.join(CACHE, stem + ".ttf")
        if not os.path.exists(raw):
            print("下载", name, w, "italic" if it else "")
            fetch(ttf_url(fam, w, it), raw)
        text = latin if kind == "latin" else cjk
        font = TTFont(raw)
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(text=text)
        sub.subset(font)
        out = os.path.join(OUT, stem + ".woff2")
        font.flavor = "woff2"
        font.save(out)
        print(f"  {stem}.woff2  {os.path.getsize(out) / 1024:.0f} KB")
        rng = "" if kind == "latin" else "  unicode-range: U+3000-9FFF, U+FF00-FFEF;\n"
        css.append(f'@font-face {{\n  font-family: "{name}";\n  src: url("{stem}.woff2") format("woff2");\n'
                   f'  font-weight: {w};\n  font-style: {"italic" if it else "normal"};\n  font-display: swap;\n{rng}}}')
    with open(os.path.join(OUT, "fonts.css"), "w", encoding="utf-8") as f:
        f.write("\n".join(css) + "\n")
    print("完成 →", OUT)


if __name__ == "__main__":
    sys.exit(main())
