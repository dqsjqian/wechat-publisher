#!/usr/bin/env python3
"""md_render.py — Markdown → 微信公众号 HTML 渲染器（纯标准库）

覆盖公众号写作的常用语法子集，输出结构与主流公众号排版引擎对齐：
- ATX 标题 h1-h6（文字包 <span>，样式载体）
- 段落 / 粗体 / 斜体 / 删除线 / 行内代码 / 链接 / 图片
- 围栏代码块（内置 mini 语法高亮，输出 hljs 兼容 class）
- 引用（支持嵌套）/ 有序无序列表（支持嵌套）/ 表格 / 分割线
- 内嵌 HTML 块（含多行 SVG）原样透传
- 链接转脚注（公众号正文外链会被过滤，统一转为文末引用）

不依赖任何第三方包，Python 3.9+ 可运行。
"""

from __future__ import annotations

import re
import urllib.parse

# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def parse_frontmatter(text):
    """解析 YAML 风格 frontmatter（键值 / 引号字符串 / 列表 / 布尔）。

    返回 (meta: dict, body: str)。
    """
    meta = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            block = text[3:end].strip("\n")
            rest = text[end + 4:].lstrip("\n")
            for line in block.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1].strip()
                    items = [
                        item.strip().strip("\"'")
                        for item in inner.split(",") if item.strip()
                    ] if inner else []
                    meta[key] = items
                elif value.lower() in ("true", "false"):
                    meta[key] = value.lower() == "true"
                else:
                    meta[key] = value.strip("\"'")
            body = rest
    return meta, body


# ---------------------------------------------------------------------------
# Mini 语法高亮（hljs 兼容输出）
# ---------------------------------------------------------------------------

KEYWORDS = {
    "python": (
        "def class return if elif else for while try except finally with as "
        "import from pass raise lambda yield global nonlocal assert del in "
        "is not and or None True False async await break continue match case"
    ),
    "javascript": (
        "function var let const return if else for while do switch case break "
        "continue new delete typeof instanceof in of class extends super this "
        "import export default from async await try catch finally throw yield "
        "static get set null undefined true false void"
    ),
    "typescript": (
        "function var let const return if else for while do switch case break "
        "continue new delete typeof instanceof in of class extends implements "
        "super this import export default from async await try catch finally "
        "throw yield static get set null undefined true false void interface "
        "type enum namespace declare readonly public private protected as"
    ),
    "cpp": (
        "alignas alignof auto bool break case catch char char8_t class concept "
        "const consteval constexpr constinit const_cast continue co_await "
        "co_return co_yield decltype default delete do double dynamic_cast "
        "else enum explicit export extern false float for friend goto if "
        "inline int long mutable namespace new noexcept nullptr operator "
        "private protected public register reinterpret_cast requires return "
        "short signed sizeof static static_assert static_cast struct switch "
        "template this thread_local throw true try typedef typeid typename "
        "union unsigned using virtual void volatile while"
    ),
    "c": (
        "auto break case char const continue default do double else enum "
        "extern float for goto if inline int long register restrict return "
        "short signed sizeof static struct switch typedef union unsigned void "
        "volatile while NULL"
    ),
    "java": (
        "abstract assert boolean break byte case catch char class const "
        "continue default do double else enum extends final finally float for "
        "goto if implements import instanceof int interface long native new "
        "package private protected public return short static strictfp super "
        "switch synchronized this throw throws transient try void volatile "
        "while true false null var record"
    ),
    "go": (
        "break case chan const continue default defer else fallthrough for "
        "func go goto if import interface map package range return select "
        "struct switch type var nil true false"
    ),
    "rust": (
        "as async await break const continue crate dyn else enum extern false "
        "fn for if impl in let loop match mod move mut pub ref return self "
        "static struct super trait true type unsafe use where while"
    ),
    "bash": (
        "if then else elif fi for while in do done case esac function select "
        "time until return exit break continue local export readonly declare "
        "typeset unset shift source alias echo cd pwd ls mkdir rm cp mv cat "
        "grep sed awk find xargs which sudo apt brew pip npm git curl wget tar "
        "chmod chown kill ps"
    ),
    "css": (
        "important media supports keyframes import from to and not only"
    ),
    "sql": (
        "SELECT FROM WHERE INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE "
        "ALTER DROP INDEX VIEW JOIN LEFT RIGHT INNER OUTER FULL ON AS AND OR "
        "NOT NULL PRIMARY KEY FOREIGN REFERENCES GROUP BY ORDER HAVING LIMIT "
        "OFFSET DISTINCT UNION ALL EXISTS BETWEEN LIKE IN CASE WHEN THEN ELSE "
        "END ASC DESC COUNT SUM AVG MIN MAX"
    ),
}

BUILTINS = {
    "python": (
        "print len range str int float list dict set tuple open type "
        "isinstance enumerate zip map filter sorted sum min max abs super "
        "getattr setattr hasattr repr format input Exception ValueError "
        "TypeError KeyError IndexError RuntimeError"
    ),
    "javascript": (
        "console require module exports window document JSON Math Object "
        "Array String Number Boolean Promise Map Set Date setTimeout "
        "setInterval fetch process Buffer"
    ),
    "typescript": (
        "console require module exports window document JSON Math Object "
        "Array String Number Boolean Promise Map Set Date setTimeout fetch "
        "process Buffer Partial Required Record Pick Omit"
    ),
    "cpp": (
        "std cout cin endl vector string map set pair make_pair push_back "
        "size begin end auto_ptr unique_ptr shared_ptr move forward swap "
        "size_t uint32_t uint64_t int32_t int64_t"
    ),
    "java": (
        "System out println print String Integer Double Boolean Character "
        "List ArrayList Map HashMap Set HashSet Optional Stream"
    ),
}

COMMENT_STYLES = {
    "python": "#",
    "bash": "#",
    "yaml": "#",
    "javascript": "//",
    "typescript": "//",
    "cpp": "//",
    "c": "//",
    "java": "//",
    "go": "//",
    "rust": "//",
    "css": None,
    "sql": "--",
}

LANG_ALIASES = {
    "js": "javascript", "ts": "typescript", "py": "python", "sh": "bash",
    "shell": "bash", "zsh": "bash", "c++": "cpp", "cxx": "cpp", "cc": "cpp",
    "hpp": "cpp", "objc": "cpp", "objectivec": "cpp", "m": "cpp",
    "golang": "go", "rs": "rust", "yml": "yaml", "html": "xml", "xml": "xml",
    "json": "json", "yaml": "yaml", "css": "css", "sql": "sql",
}

HLJS_CLASS = {
    "comment": "hljs-comment",
    "string": "hljs-string",
    "keyword": "hljs-keyword",
    "number": "hljs-number",
    "built_in": "hljs-built_in",
    "title": "hljs-title function_",
}


def _build_lang_pattern(lang):
    """合成一个语言的高亮正则（命名组按优先级排列）。"""
    kw = KEYWORDS.get(lang)
    if not kw:
        return None
    comment = COMMENT_STYLES.get(lang)
    parts = []
    if lang in ("javascript", "typescript", "java", "cpp", "c", "go",
                "rust", "css"):
        block_comment = r"/\*[\s\S]*?\*/"
        if lang == "css":
            parts.append(r"(?P<comment>\/\*[\s\S]*?\*\/)")
        else:
            parts.append(
                r"(?P<comment>\/\*[\s\S]*?\*\/|\/\/[^\n]*)"
            )
    elif comment == "#":
        parts.append(r"(?P<comment>#[^\n]*)")
    elif comment == "--":
        parts.append(r"(?P<comment>--[^\n]*)")
    else:
        parts.append(r"(?P<comment>#!?[^\n]*)")

    if lang == "python":
        parts.append(
            r'(?P<string>"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\''
            r'|[rbfu]{0,2}"(?:\\.|[^"\\\n])*"|[rbfu]{0,2}\'(?:\\.|[^\'\\\n])*\')'
        )
    elif lang in ("javascript", "typescript"):
        parts.append(
            r'(?P<string>`(?:\\.|[^`\\])*`'
            r'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')'
        )
    else:
        parts.append(
            r'(?P<string>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')'
        )

    kw_pattern = "|".join(re.escape(k) for k in kw.split())
    parts.append(rf"(?P<keyword>\b(?:{kw_pattern})\b)")

    builtins = BUILTINS.get(lang)
    if builtins:
        b_pattern = "|".join(re.escape(b) for b in builtins.split())
        parts.append(rf"(?P<built_in>\b(?:{b_pattern})\b)")

    parts.append(r"(?P<title>\b[A-Za-z_]\w*)(?=\s*\()")
    parts.append(
        r"(?P<number>\b0[xX][0-9a-fA-F]+\b|\b\d[\d_]*(?:\.\d+)?"
        r"(?:[eE][+-]?\d+)?[fFlLuU]*\b)"
    )
    return re.compile("|".join(parts))


_LANG_CACHE = {}


def _lang_pattern_for(lang):
    key = LANG_ALIASES.get(lang, lang)
    if key not in _LANG_CACHE:
        _LANG_CACHE[key] = _build_lang_pattern(key)
    return _LANG_CACHE[key], key


def highlight_code(code, lang):
    """代码 → hljs 风格高亮 HTML。未知语言返回纯转义文本。"""
    if not lang:
        return escape_html(code)
    pattern, resolved = _lang_pattern_for(lang)
    if pattern is None:
        return escape_html(code)
    out = []
    pos = 0
    for m in pattern.finditer(code):
        if m.start() > pos:
            out.append(escape_html(code[pos:m.start()]))
        for kind, value in m.groupdict().items():
            if value is None:
                continue
            cls = HLJS_CLASS.get(kind)
            if kind == "title":
                out.append(f'<span class="hljs-title function_">'
                           f"{escape_html(value)}</span>")
            elif cls:
                out.append(f'<span class="{cls}">{escape_html(value)}</span>')
            else:
                out.append(escape_html(value))
            break
        pos = m.end()
    if pos < len(code):
        out.append(escape_html(code[pos:]))
    return "".join(out)


# ---------------------------------------------------------------------------
# 行内渲染
# ---------------------------------------------------------------------------

_URI_SAFE = "!#$&'()*+,/:;=?@[]~"


def normalize_href(href):
    href = href.strip()
    if href.startswith("<") and href.endswith(">"):
        href = href[1:-1]
    try:
        return urllib.parse.quote(href, safe=_URI_SAFE)
    except Exception:
        return href


def escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)
_EM_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)")
_DEL_RE = re.compile(r"~~(.+?)~~", re.S)
_SLOT_RE = re.compile("\x00(\\d+)\x00")


def render_inline(text):
    """行内 Markdown → HTML。

    流程：行内代码/图片/链接生成后立即占位 → 转义剩余文本 →
    粗斜体/删除线替换（此时无嵌套风险）→ 循环还原占位符。
    """
    slots = []

    def stash(html):
        slots.append(html)
        return f"\x00{len(slots) - 1}\x00"

    text = _INLINE_CODE_RE.sub(
        lambda m: stash(f"<code>{escape_html(m.group(1))}</code>"), text
    )
    text = _IMAGE_RE.sub(
        lambda m: stash(
            f'<img src="{normalize_href(m.group(2))}" '
            f'alt="{escape_html(m.group(1))}">'
        ),
        text,
    )

    def sub_link(m):
        label, href = m.group(1), m.group(2)
        return stash(
            f'<a href="{normalize_href(href)}">{render_inline(label)}</a>'
        )

    text = _LINK_RE.sub(sub_link, text)

    # 剩余纯文本统一转义（此时不会再生成新标签以外的 < > & "）
    text = escape_html(text)

    # 粗体/斜体/删除线：内容已转义，标签直接拼接
    text = _BOLD_RE.sub(
        lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text
    )
    text = _EM_RE.sub(
        lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text
    )
    text = _DEL_RE.sub(lambda m: f"<del>{m.group(1)}</del>", text)

    # 循环还原（支持占位符嵌套，如链接里含行内代码）
    while True:
        new_text = _SLOT_RE.sub(lambda m: slots[int(m.group(1))], text)
        if new_text == text:
            break
        text = new_text
    return text


# ---------------------------------------------------------------------------
# 块级渲染
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^```(\S*)\s*$")
_HR_RE = re.compile(r"^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
_UL_ITEM_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL_ITEM_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_BLOCK_TAG_RE = re.compile(
    r"^\s*<(div|section|svg|table|figure|center|p|img|video|audio|iframe)\b",
    re.I,
)
_NESTED_TAG_RE = re.compile(r"<(/?)([\w-]+)")


def render_markdown(body):
    """Markdown 正文 → HTML（不含脚注，脚注由 add_footnotes 处理）。"""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            out.append(
                f"<h{level}><span>{render_inline(m.group(2))}</span></h{level}>"
            )
            i += 1
            continue

        m = _FENCE_RE.match(line)
        if m:
            lang = m.group(1)
            i += 1
            code_lines = []
            while i < n and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结尾 ```
            code = "\n".join(code_lines)
            highlighted = highlight_code(code, lang)
            cls = f' class="hljs language-{lang}"' if lang else ' class="hljs"'
            out.append(f"<pre><code{cls}>{highlighted}</code></pre>")
            continue

        if _HR_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        if line.lstrip().startswith("|") and i + 1 < n and _TABLE_SEP_RE.match(
            lines[i + 1]
        ):
            header_cells = _split_table_row(line)
            i += 2
            rows = []
            while i < n and _is_table_row(lines[i]):
                rows.append(_split_table_row(lines[i]))
                i += 1
            out.append(_render_table(header_cells, rows))
            continue

        m = _QUOTE_RE.match(line)
        if m:
            quote_lines = []
            while i < n:
                qm = _QUOTE_RE.match(lines[i])
                if qm:
                    quote_lines.append(qm.group(1))
                elif lines[i].strip() and quote_lines:
                    quote_lines.append(lines[i])  # 引用延续行
                else:
                    break
                i += 1
            inner = render_markdown("\n".join(quote_lines))
            if not inner.startswith("<p>"):
                inner = f"<p>{inner}</p>"
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        if _UL_ITEM_RE.match(line) or _OL_ITEM_RE.match(line):
            items_html, i = _render_list(lines, i, n)
            out.append(items_html)
            continue

        if _BLOCK_TAG_RE.match(line):
            html_block, i = _collect_html_block(lines, i, n)
            out.append(html_block)
            continue

        # 段落：连续文本行合并
        para_lines = [line.strip()]
        i += 1
        while i < n:
            nxt = lines[i]
            if (
                not nxt.strip()
                or _HEADING_RE.match(nxt)
                or _FENCE_RE.match(nxt)
                or _HR_RE.match(nxt)
                or _QUOTE_RE.match(nxt)
                or _UL_ITEM_RE.match(nxt)
                or _OL_ITEM_RE.match(nxt)
                or _BLOCK_TAG_RE.match(nxt)
                or nxt.lstrip().startswith("|")
            ):
                break
            para_lines.append(nxt.strip())
            i += 1
        out.append(f"<p>{render_inline(' '.join(para_lines))}</p>")
    return "\n".join(out)


def _is_table_row(line):
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 2


def _split_table_row(line):
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _render_table(header_cells, rows):
    thead = "".join(f"<th>{render_inline(c)}</th>" for c in header_cells)
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in row) + "</tr>"
        )
    return (
        f"<table><thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def _render_list(lines, i, n, indent=None):
    """渲染列表（含嵌套）。返回 (html, next_index)。

    indent 为 None 时以首行缩进为基准（支持任意缩进层级切入）。
    """
    start = i
    is_ordered = bool(_OL_ITEM_RE.match(lines[i]))
    tag = "ol" if is_ordered else "ul"
    first = _OL_ITEM_RE.match(lines[i]) if is_ordered else _UL_ITEM_RE.match(lines[i])
    if indent is None:
        indent = len(first.group(1).replace("\t", "    "))
    items = []
    while i < n:
        line = lines[i]
        m = _OL_ITEM_RE.match(line) if is_ordered else _UL_ITEM_RE.match(line)
        if not m:
            break
        cur_indent = len(m.group(1).replace("\t", "    "))
        if cur_indent != indent:
            break
        content = m.group(3) if is_ordered else m.group(2)
        # 收集该条目的续行与嵌套列表
        child_lines = []
        i += 1
        while i < n:
            nxt = lines[i]
            nxt_indent = len(nxt) - len(nxt.lstrip())
            if (
                _UL_ITEM_RE.match(nxt) or _OL_ITEM_RE.match(nxt)
            ) and nxt_indent > cur_indent:
                child_lines.append(nxt)
                i += 1
            elif not nxt.strip():
                # 空行后如果还是深层列表项则继续收集
                if i + 1 < n and (
                    _UL_ITEM_RE.match(lines[i + 1]) or _OL_ITEM_RE.match(lines[i + 1])
                ):
                    peek_indent = len(lines[i + 1]) - len(lines[i + 1].lstrip())
                    if peek_indent > cur_indent:
                        child_lines.append(nxt)
                        i += 1
                        continue
                break
            elif nxt_indent > cur_indent and nxt.strip():
                child_lines.append(nxt)
                i += 1
            else:
                break
        inner_html = render_inline(content.strip())
        if child_lines:
            sub = "\n".join(child_lines)
            sub_html = render_markdown(sub)
            inner_html += sub_html
        items.append(f"<li>{inner_html}</li>")
    # 保底推进至少一行，防止调用方原地循环
    return f"<{tag}>{''.join(items)}</{tag}>", max(i, start + 1)


def _collect_html_block(lines, i, n):
    """收集原始 HTML 块（含多行 SVG），直到顶层标签闭合。"""
    first = _BLOCK_TAG_RE.match(lines[i])
    tag = first.group(1).lower()
    block = [lines[i]]
    i += 1
    depth = _tag_delta(lines[i - 1], tag)
    while i < n and depth > 0:
        block.append(lines[i])
        depth += _tag_delta(lines[i], tag)
        i += 1
    return "\n".join(block), i


_SELF_CLOSE_RE = re.compile(r"<[\w-]+[^>]*?/>", re.S)


def _tag_delta(line, tag):
    """一行内 tag 的开闭差值（自闭合不算）。"""
    cleaned = _SELF_CLOSE_RE.sub("", line)
    delta = 0
    for m in re.finditer(rf"<(/?){tag}\b[^>]*>", cleaned, re.I):
        delta += -1 if m.group(1) else 1
    return delta


# ---------------------------------------------------------------------------
# 脚注（链接 → 文末引用）
# ---------------------------------------------------------------------------


def add_footnotes(body_html):
    """把正文里的 <a> 转成斜体文本 + 上标序号，文末追加引用块。

    返回 (new_body_html, footnotes_block_html)；无链接时 footnotes 为空串。
    """
    import css_inline

    root = css_inline.parse_html(body_html)
    footnotes = []
    index = 0
    for el in list(root.iter_descendants()):
        if el.tag != "a" or not el.get("href"):
            continue
        index += 1
        title = el.text_content().strip() or el.get("href")
        href = el.get("href")
        footnotes.append((index, title, href))
        sup = css_inline.Element("sup", {"class": "footnote"})
        sup.append(f"[{index}]")
        # 用 <em> 包裹原链接文字，保持可读性与主题色
        em = css_inline.Element("em")
        for child in list(el.children):
            em.append(child)
        el.children = [em]
        parent = el.parent
        pos = parent.children.index(el)
        parent.children.insert(pos + 1, sup)
        sup.parent = parent

    if not footnotes:
        return body_html, ""

    items = []
    for idx, title, href in footnotes:
        if title == href:
            items.append(
                f'<p><span class="footnote-num">[{idx}]</span>'
                f'<span class="footnote-txt"><i>{escape_html(title)}</i></span></p>'
            )
        else:
            items.append(
                f'<p><span class="footnote-num">[{idx}]</span>'
                f'<span class="footnote-txt">{escape_html(title)}: '
                f"<i>{escape_html(href)}</i></span></p>"
            )
    block = (
        "<h3>引用链接</h3>"
        f'<section id="footnotes">{"".join(items)}</section>'
    )
    new_body = "".join(
        css_inline.serialize(c) if not isinstance(c, str) else c
        for c in root.children
    )
    return new_body, block
