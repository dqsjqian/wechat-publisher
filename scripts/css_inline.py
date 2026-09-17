#!/usr/bin/env python3
"""css_inline.py — 轻量 DOM + CSS 内联引擎（纯标准库，无第三方依赖）

把主题 CSS 内联成 inline style，让微信公众号正文承载完整排版
（公众号编辑器会丢弃 <style> 标签，只认元素级 style 属性）。

能力：
- HTML 解析（html.parser）→ Element 树，支持内嵌 SVG
- CSS 解析：注释 / 逗号分组 / url() 与嵌套括号内的分号 / @规则跳过
- CSS 变量：:root 与 #article 的 --var 声明，var() 递归替换（含 fallback）
- 选择器匹配：#id / .class / tag / * ，后代与 > 子代组合
- 层叠：批内按 (特异性, 出现顺序)，多份 CSS 依序应用后者覆盖
- 伪元素 ::before / ::after（h1-h6 / blockquote / pre）→ 真实 <section>
- 微信兼容后处理：code 内换行转 <br> + 空格转 U+00A0、li 内容包
  section、嵌套列表扁平化、容器强制黑色文字
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# 基础常量
# ---------------------------------------------------------------------------

SANS_SERIF = (
    "-apple-system, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', "
    "'Helvetica Neue', Arial, sans-serif"
)
MONOSPACE = (
    "'SF Mono', 'JetBrains Mono', Menlo, Consolas, 'Courier New', monospace"
)

VOID_TAGS = {
    "br", "hr", "img", "input", "meta", "link", "source", "area",
    "base", "col", "embed", "track", "wbr",
}

# 代码块顶部的红黄绿圆点装饰（macOS 窗口风格，通用视觉惯例）
MAC_STYLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="52" height="14" '
    'viewBox="0 0 52 14">'
    '<circle cx="7" cy="7" r="5.5" fill="rgb(236,106,94)"/>'
    '<circle cx="26" cy="7" r="5.5" fill="rgb(244,191,79)"/>'
    '<circle cx="45" cy="7" r="5.5" fill="rgb(97,197,84)"/>'
    "</svg>"
)
MAC_STYLE_DECLARATIONS = [
    ("display", "block"),
    ("width", "100%"),
    ("height", "14px"),
    ("background-repeat", "no-repeat"),
    ("background-size", "52px 14px"),
]


# ---------------------------------------------------------------------------
# 轻量 DOM
# ---------------------------------------------------------------------------

class Element:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs) if attrs else {}
        self.children = []  # Element | str
        self.parent = parent

    # -- 属性辅助 -----------------------------------------------------------

    @property
    def id(self):
        return self.attrs.get("id", "")

    @property
    def classes(self):
        cls = self.attrs.get("class")
        return cls.split() if cls else []

    def get(self, name, default=""):
        return self.attrs.get(name, default)

    def set(self, name, value):
        self.attrs[name] = value

    def append(self, node):
        if isinstance(node, Element):
            node.parent = self
        self.children.append(node)
        return node

    def insert_first(self, node):
        if isinstance(node, Element):
            node.parent = self
        self.children.insert(0, node)
        return node

    # -- 遍历 ---------------------------------------------------------------

    def iter_descendants(self):
        """深度优先遍历所有后代元素（不含自身）。"""
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.iter_descendants()

    def descendants(self):
        return list(self.iter_descendants())

    # -- 样式 ---------------------------------------------------------------

    @property
    def style(self):
        return self.attrs.get("style", "")

    def set_style(self, prop, value):
        """合并 style 属性（同名属性覆盖，保持声明顺序）。"""
        decls = parse_declarations(self.attrs.get("style", ""))
        decls = [d for d in decls if d[0] != prop]
        decls.append((prop, value))
        self.attrs["style"] = serialize_declarations(decls)

    def set_styles(self, decls):
        """批量合并声明（同名覆盖，保持首次出现顺序）。"""
        current = parse_declarations(self.attrs.get("style", ""))
        merged = {p: v for p, v in current}
        order = [p for p, _ in current]
        for p, v in decls:
            if p not in merged:
                order.append(p)
            merged[p] = v
        self.attrs["style"] = serialize_declarations(
            [(p, merged[p]) for p in order]
        )

    # -- 文本 ---------------------------------------------------------------

    def text_content(self):
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            else:
                parts.append(child.text_content())
        return "".join(parts)


def escape_attr(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_text(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def serialize(node):
    """Element → HTML 字符串（含自身）。"""
    if isinstance(node, str):
        return escape_text(node)
    parts = ["<", node.tag]
    for name, value in node.attrs.items():
        if value == "" and name in ("disabled", "checked", "readonly"):
            parts.append(f" {name}")
        else:
            parts.append(f' {name}="{escape_attr(value)}"')
    parts.append(">")
    if node.tag in VOID_TAGS:
        return "".join(parts)
    for child in node.children:
        parts.append(serialize(child))
    parts.append(f"</{node.tag}>")
    return "".join(parts)


class DOMBuilder(HTMLParser):
    """把 HTML 片段解析成 Element 树。

    顶层多个元素时自动包一层 <body>（可随后取出 children）。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("body")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = Element(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(el)
        if tag not in VOID_TAGS:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        el = Element(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)

    def handle_entityref(self, name):  # convert_charrefs=True 时基本不触发
        self.stack[-1].children.append(f"&{name};")

    def handle_charref(self, name):
        self.stack[-1].children.append(f"&#{name};")


def parse_html(html):
    builder = DOMBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# ---------------------------------------------------------------------------
# CSS 解析
# ---------------------------------------------------------------------------

class Rule:
    __slots__ = ("selectors", "declarations", "order")

    def __init__(self, selectors, declarations, order):
        self.selectors = selectors      # list[str] 原始选择器
        self.declarations = declarations  # list[(prop, value)]
        self.order = order


def strip_css_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def split_top_level(text, sep=","):
    """顶层逗号分组：括号/引号内不拆分。"""
    parts, buf = [], []
    depth = 0
    quote = None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def parse_declarations(block):
    """声明块 → [(prop, value)]，容忍 url() 与括号内的分号。"""
    decls = []
    buf = []
    depth = 0
    quote = None
    for ch in block:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            decls.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        decls.append("".join(buf))
    result = []
    for item in decls:
        item = item.strip()
        if not item or ":" not in item:
            continue
        prop, _, value = item.partition(":")
        prop = prop.strip().lower()
        value = value.strip()
        if prop.startswith("--") or not value:
            continue
        value = re.sub(r"\s*!important\s*$", "", value, flags=re.I)
        result.append((prop, value))
    return result


def serialize_declarations(decls):
    """[(prop, value)] → 'prop: value; prop: value' 形式。"""
    return "; ".join(f"{p}: {v}" for p, v in decls)


def parse_stylesheet(css_text):
    """CSS 文本 → [Rule]。@规则整块跳过。"""
    text = strip_css_comments(css_text)
    rules = []
    order = 0
    i, n = 0, len(text)
    while i < n:
        brace = text.find("{", i)
        if brace == -1:
            break
        selector_text = text[i:brace].strip()
        # 找匹配的 }（容忍嵌套括号，如 url(...{...}...) 罕见，逐字符扫描）
        depth = 0
        j = brace
        quote = None
        while j < n:
            ch = text[j]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        block = text[brace + 1 : j]
        i = j + 1
        if not selector_text or selector_text.startswith("@"):
            continue
        selectors = split_top_level(selector_text)
        declarations = parse_declarations(block)
        if selectors and declarations:
            rules.append(Rule(selectors, declarations, order))
            order += 1
    return rules


def collect_css_variables(css_text):
    """收集 :root / #article 里的 --var 声明（含跨声明引用，两轮解析）。"""
    variables = {}
    text = strip_css_comments(css_text)
    for sel_part, block in iter_rule_blocks(text):
        sels = [s.strip() for s in split_top_level(sel_part)]
        if not any(s in (":root", "#article") for s in sels):
            continue
        for prop, value in parse_raw_custom_props(block):
            variables[prop] = value
    # 解析 var() 链（如 --header-span-color: var(--primary-color)）
    for _ in range(5):
        changed = False
        for key, value in variables.items():
            if "var(" in value:
                resolved = resolve_vars(value, variables, keep_unresolved=True)
                if resolved != value:
                    variables[key] = resolved
                    changed = True
        if not changed:
            break
    return variables


def iter_rule_blocks(text):
    """yield (selector_text, block_text) 跳过 @规则。"""
    i, n = 0, len(text)
    while i < n:
        brace = text.find("{", i)
        if brace == -1:
            return
        selector_text = text[i:brace].strip()
        depth = 0
        j = brace
        quote = None
        while j < n:
            ch = text[j]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        block = text[brace + 1 : j]
        i = j + 1
        if selector_text and not selector_text.startswith("@"):
            yield selector_text, block


def parse_raw_custom_props(block):
    props = []
    buf = []
    depth = 0
    quote = None
    for ch in block:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            props.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        props.append("".join(buf))
    result = []
    for item in props:
        item = item.strip()
        if not item.startswith("--") or ":" not in item:
            continue
        prop, _, value = item.partition(":")
        result.append((prop.strip(), value.strip()))
    return result


VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*?))?\)")


def resolve_vars(value, variables, keep_unresolved=False):
    """把 value 里的 var(--x[, fallback]) 替换为实际值。"""

    def repl(match):
        name = match.group(1)
        fallback = match.group(2)
        if name in variables:
            return variables[name]
        if fallback is not None and fallback.strip():
            return fallback.strip()
        return match.group(0) if keep_unresolved else ""

    for _ in range(6):
        if "var(" not in value:
            break
        new_value = VAR_RE.sub(repl, value)
        if new_value == value:
            break
        value = new_value
    return value


# ---------------------------------------------------------------------------
# 选择器解析与匹配
# ---------------------------------------------------------------------------

class Compound:
    __slots__ = ("tag", "id", "classes", "is_child")

    def __init__(self, tag="", id="", classes=None, is_child=False):
        self.tag = tag          # "" 表示通配
        self.id = id
        self.classes = classes or []
        self.is_child = is_child  # 与前一个 compound 是 > 关系


SELECTOR_SKIP_RE = re.compile(r":(?!:)" )  # 伪类（单冒号）


def parse_selector(selector):
    """'#article h2 code' → [Compound, Compound, Compound]。

    返回 None 表示无法处理（伪类 / 属性选择器等，跳过）。
    """
    selector = selector.strip()
    if not selector or SELECTOR_SKIP_RE.search(selector):
        # 伪元素 ::before/::after 在 pseudo 阶段单独处理，这里跳过
        return None
    if "::" in selector:
        return None
    # 拆后代链（保留 > 关系）
    parts = re.split(r"\s*(>)\s*|\s+", selector)
    parts = [p for p in parts if p]
    chain = []
    expect_child = False
    for part in parts:
        if part == ">":
            expect_child = True
            continue
        compound = Compound(is_child=expect_child)
        expect_child = False
        rest = part
        m = re.match(r"^([a-zA-Z][\w-]*|\*)", rest)
        if m:
            if m.group(1) != "*":
                compound.tag = m.group(1).lower()
            rest = rest[m.end():]
        id_match = re.search(r"#([\w-]+)", rest)
        if id_match:
            compound.id = id_match.group(1)
            rest = rest.replace(id_match.group(0), "")
        compound.classes = re.findall(r"\.([\w-]+)", rest)
        rest = re.sub(r"\.[\w-]+", "", rest)
        if rest.strip():  # 不认识的语法（属性选择器等）
            return None
        chain.append(compound)
    if not chain:
        return None
    return chain


def compound_matches(el, compound):
    if compound.tag and el.tag != compound.tag:
        return False
    if compound.id and el.id != compound.id:
        return False
    if compound.classes:
        cls = set(el.classes)
        if not all(c in cls for c in compound.classes):
            return False
    return True


def selector_matches(el, chain):
    """标准后向匹配：chain 最后一项匹配 el，向前匹配祖先链。"""
    if not compound_matches(el, chain[-1]):
        return False
    return _match_up(el, chain, len(chain) - 2)


def _match_up(el, chain, idx):
    if idx < 0:
        return True
    node = el.parent
    need_child = chain[idx + 1].is_child
    steps = 0
    while isinstance(node, Element):
        if compound_matches(node, chain[idx]):
            if _match_up(node, chain, idx - 1):
                return True
            if need_child:
                return False
        if need_child:
            return False
        node = node.parent
        steps += 1
        if steps > 200:
            return False
    return False


def specificity(chain):
    a = sum(1 for c in chain if c.id)
    b = sum(len(c.classes) for c in chain)
    c = sum(1 for comp in chain if comp.tag)
    return (a, b, c)


# ---------------------------------------------------------------------------
# 样式内联主流程
# ---------------------------------------------------------------------------

def apply_css(container, css_text):
    """把 CSS 内联到容器内元素（含容器自身，#article 选择器）。"""
    variables = collect_css_variables(css_text)
    rules = parse_stylesheet(css_text)
    if not rules:
        return
    # 收集 (元素, 声明列表) 按层叠顺序
    applications = []  # (specificity, order, element, declarations)
    all_elements = [container] + container.descendants()
    for rule in rules:
        for sel in rule.selectors:
            chain = parse_selector(sel)
            if chain is None:
                continue
            decls = [
                (p, resolve_vars(v, variables) if "var(" in v else v)
                for p, v in rule.declarations
            ]
            if not decls:
                continue
            for el in all_elements:
                if selector_matches(el, chain):
                    # 纯出现顺序层叠（与 CSS 作者书写意图一致）
                    applications.append((rule.order, el, decls))
    applications.sort(key=lambda t: t[0])
    for _, el, decls in applications:
        el.set_styles(decls)


def extract_pseudo_rules(css_text):
    """提取 h1-h6/blockquote/pre 的 ::before/::after 规则。

    返回 {tag: {"before": [(prop, value)], "after": [...]}}，
    声明值里的 var() 已解析为实际值。
    """
    table = {}
    variables = collect_css_variables(css_text)
    text = strip_css_comments(css_text)
    for sel_text, block in iter_rule_blocks(text):
        for sel in split_top_level(sel_text):
            m = re.search(r"(?:^|\s)(h[1-6]|blockquote|pre)::(before|after)\b", sel)
            if not m:
                continue
            tag, pseudo = m.group(1), m.group(2)
            record = table.setdefault(tag, {"before": [], "after": []})
            for prop, value in parse_declarations(block):
                if "var(" in value:
                    value = resolve_vars(value, variables)
                record[pseudo].append((prop, value))
    return table


def build_pseudo_element(decls):
    """伪元素声明 → 真实 <section>（content/SVG data URI/背景 URL 展开）。"""
    section = Element("section")
    remaining = []
    content = None
    for prop, value in decls:
        if prop == "content":
            content = value
        else:
            remaining.append((prop, value))
    if content:
        text = content.strip("\"' ")
        if text and text != "none":
            section.append(text)
    final = []
    for prop, value in remaining:
        if "url(" in value:
            svg_match = re.search(r"data:image/svg\+xml;utf8,(.*</svg>)", value)
            b64_match = re.search(r"data:image/svg\+xml;base64,([^\"')]*)", value)
            http_match = re.search(r"(?:\"|')?(https?[^\"')]*)(?:\"|')?\)?$", value)
            if svg_match:
                svg_code = urllib.parse.unquote(svg_match.group(1))
                svg_root = parse_html(svg_code).children
                for node in svg_root:
                    section.append(node)
                continue
            if b64_match:
                try:
                    decoded = base64.b64decode(b64_match.group(1)).decode("utf-8")
                    for node in parse_html(decoded).children:
                        section.append(node)
                    continue
                except Exception:
                    pass
            if http_match and prop in ("background", "background-image"):
                img = Element("img", {"src": http_match.group(1),
                                      "style": "vertical-align: top;"})
                section.append(img)
                continue
        final.append((prop, value))
    if final:
        section.set_styles(final)
    return section


def apply_pseudo_elements(container, css_text):
    table = extract_pseudo_rules(css_text)
    if not table:
        return
    for tag, record in table.items():
        targets = [el for el in container.descendants() if el.tag == tag]
        for el in targets:
            if record["before"]:
                el.insert_first(build_pseudo_element(record["before"]))
            if record["after"]:
                el.append(build_pseudo_element(record["after"]))


def apply_mac_style(container):
    """pre 前插入 Mac 三圆点 section。"""
    for el in container.descendants():
        if el.tag == "pre":
            dot = build_pseudo_element(
                [("background",
                  f"url('data:image/svg+xml;utf8,{MAC_STYLE_SVG}')")]
                + MAC_STYLE_DECLARATIONS
            )
            el.insert_first(dot)


# ---------------------------------------------------------------------------
# 微信兼容后处理（wechatPostRender 等价）
# ---------------------------------------------------------------------------

NBSP = "\u00a0"


def _process_code_element(code_el):
    """code 内：文本节点 \n → <br>，空格 → U+00A0（微信编辑器吞空白）。"""
    new_children = []
    for child in code_el.children:
        if isinstance(child, str):
            text = child.replace(" ", NBSP).replace("\n", "<br>")
            # <br> 是标签，不能塞进文本节点——拆分
            segments = text.split("<br>")
            for i, seg in enumerate(segments):
                if i > 0:
                    new_children.append(Element("br"))
                if seg:
                    new_children.append(seg)
        else:
            if isinstance(child, Element) and child.tag != "br":
                _process_code_element(child)
            new_children.append(child)
    code_el.children = new_children


def _wrap_li_content(container):
    """li 内容包一层 <section>（微信编辑器兼容）。"""
    for li in [el for el in container.descendants() if el.tag == "li"]:
        content = li.children[:]
        li.children = []
        section = Element("section", parent=li)
        for node in content:
            section.children.append(node)
            if isinstance(node, Element):
                node.parent = section
        li.append(section)


def _flatten_nested_lists(container):
    """li > section > ul/ol → 扁平 section + 手写序号/圆点（微信里嵌套列表渲染不稳）。"""
    while True:
        nested = [
            el for el in container.descendants()
            if el.tag in ("ul", "ol") and isinstance(el.parent, Element)
            and el.parent.tag == "section" and isinstance(el.parent.parent, Element)
            and el.parent.parent.tag == "li"
        ]
        if not nested:
            return
        for lst in nested:
            is_ordered = lst.tag == "ol"
            wrapper = Element("section", {"style": "margin-left: 1em;"})
            index = 0
            for item in lst.children:
                if not isinstance(item, Element) or item.tag != "li":
                    continue
                index += 1
                marker = f"{index}. " if is_ordered else "• "
                section_el = Element("section")
                inner = None
                for child in item.children:
                    if isinstance(child, Element) and child.tag == "section":
                        inner = child
                        break
                if inner is not None:
                    section_el.append(marker)
                    for node in inner.children:
                        section_el.append(node)
                        if isinstance(node, Element):
                            node.parent = section_el
                else:
                    section_el.append(marker + item.text_content())
                wrapper.append(section_el)
            parent_section = lst.parent
            pos = parent_section.children.index(lst)
            parent_section.children[pos] = wrapper
            wrapper.parent = parent_section


def wechat_post_render(container):
    for el in container.descendants():
        if el.tag == "code":
            _process_code_element(el)
    _wrap_li_content(container)
    _flatten_nested_lists(container)
    container.set_style("color", "rgb(0, 0, 0)")
    container.set_style("caret-color", "rgb(0, 0, 0)")


# ---------------------------------------------------------------------------
# 对外主入口
# ---------------------------------------------------------------------------

BASE_UPDATES = [
    ("#article", [("font-family", SANS_SERIF)]),
    ("#article pre", [("font-size", "12px")]),
    ("#article pre code", [("font-family", MONOSPACE)]),
    ("#article p code", [("font-family", MONOSPACE)]),
    ("#article li code", [("font-family", MONOSPACE)]),
]


def render_styled(html_body, theme_css, hl_css="", mac_style=True,
                  add_footnote_html=""):
    """完整渲染管线：HTML → 微信可用的内联样式 HTML。

    参数 add_footnote_html：脚注块 HTML（由渲染器生成、在 CSS 前注入，
    与主题 CSS 应用时机一致）。
    """
    container = Element("section", {"id": "article"})
    for node in parse_html(html_body).children:
        container.append(node)

    # 基础字体补丁，最先应用
    base_css = "\n".join(
        "{} {{ {} }}".format(sel, "; ".join(f"{p}: {v}" for p, v in decls))
        for sel, decls in BASE_UPDATES
    )
    apply_css(container, base_css)

    if add_footnote_html:
        for node in parse_html(add_footnote_html).children:
            container.append(node)

    if mac_style:
        apply_mac_style(container)

    apply_css(container, theme_css)
    apply_pseudo_elements(container, theme_css)

    if hl_css:
        apply_css(container, hl_css)

    wechat_post_render(container)
    html = serialize(container)
    html = html.replace("\n<li", "<li").replace("</li>\n", "</li>")
    return html
