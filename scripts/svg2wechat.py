#!/usr/bin/env python3
"""
svg2wechat —— 把 SVG 转成微信公众号正文可用的内联片段

微信正文会把 content 当 HTML 解析后重新序列化，实测造成两个破坏：
  1. id 属性 100% 被剥离  -> <marker>/<linearGradient>/<clipPath> 的 url(#ref) 全部悬空
  2. 固定 width/height 保留 -> 手机上横向溢出

本脚本做三件事：
  - 去掉 XML 声明与固定宽高，改成 viewBox + width:100% 响应式
  - 把 marker 箭头（依赖 id 引用）展开成显式 <path> 三角形，支持一张图里多个 marker
  - 输出可直接粘进公众号编辑器的 HTML 片段

用法：
  python3 svg2wechat.py input.svg                     # 打印片段
  python3 svg2wechat.py input.svg -o out.html         # 写入文件
  python3 svg2wechat.py input.svg --svg-only -o x.svg  # 只出处理后的 svg
  python3 svg2wechat.py images/*.svg -o-dir out/       # 批量
"""
import argparse
import math
import os
import re
import sys


def strip_xml(s: str) -> str:
    return re.sub(r"<\?xml[^>]*\?>", "", s).strip()


def parse_markers(svg: str) -> dict:
    """取出所有 marker 的几何定义，key 为 id。"""
    out = {}
    for m in re.finditer(r"<marker\b([^>]*)>(.*?)</marker>", svg, re.S):
        attrs, inner = m.group(1), m.group(2)

        def attr(name, default=None):
            a = re.search(rf'\b{name}="([^"]*)"', attrs, re.I)
            return a.group(1) if a else default

        mid = attr("id")
        if not mid:
            continue

        pm = re.search(r"<path\b([^>]*)/?>", inner)
        if not pm:
            continue
        pd = re.search(r'\bd="([^"]*)"', pm.group(1))
        fill = re.search(r'\bfill="([^"]*)"', pm.group(1))

        vb = attr("viewBox", "0 0 8 7").split()
        if len(vb) < 4:
            vb = ["0", "0", "8", "7"]
        out[mid] = {
            "id": mid,
            "vbW": float(vb[2]),
            "vbH": float(vb[3]),
            "refX": float(attr("refX", 0)),
            "refY": float(attr("refY", 0)),
            "mw": float(attr("markerWidth", 3)),
            "mh": float(attr("markerHeight", 3)),
            "path": pd.group(1) if pd else "M0,0 L0,7 L8,3.5 z",
            "fill": fill.group(1) if fill else "context-stroke",
        }
    return out


def parse_path_points(d: str):
    """只支持 M x,y L x,y [L x,y ...]，marker 定义基本都是这种简单形状。"""
    nums = re.findall(r"[-+]?[0-9]*\.?[0-9]+", d)
    pts, i = [], 0
    while i + 1 < len(nums):
        pts.append((float(nums[i]), float(nums[i + 1])))
        i += 2
    return pts


def expand_markers(svg: str, markers: dict) -> tuple[str, int, list]:
    """
    把 <line marker-end="url(#id)"> 换成 line + 显式三角形 path。

    几何：marker 默认 markerUnits=strokeWidth，所以实际缩放为
          T = markerWidth / viewBoxWidth * strokeWidth
    三角形顶点是 marker 本地坐标减去参考点后的结果，
    再按 orient="auto" 规则旋转到线条方向。
    """
    total = 0
    leftovers = []

    for mid, marker in markers.items():
        pts = parse_path_points(marker["path"])
        if not pts:
            continue
        T_norm = marker["mw"] / marker["vbW"]
        cx, cy = marker["refX"], marker["refY"]
        local = [((x - cx) * T_norm, (y - cy) * T_norm) for x, y in pts]

        pat = re.compile(
            r"<line\b([^>]*?)marker-end=\"url\(#" + re.escape(mid) + r"\)\"([^>]*?)/>"
        )

        def repl(m, marker=marker, local=local):
            nonlocal total
            allattrs = m.group(1) + m.group(2)

            def a(n, default=None):
                r = re.search(rf'\b{n}="([^"]*)"', allattrs)
                if r is None:
                    return default
                try:
                    return float(r.group(1))
                except ValueError:
                    return default

            x1, y1 = a("x1", 0.0), a("y1", 0.0)
            x2, y2 = a("x2", 0.0), a("y2", 0.0)
            sw = a("stroke-width", 1.0) or 1.0
            stroke = re.search(r'\bstroke="([^"]*)"', allattrs)
            color = marker["fill"]
            if color == "context-stroke" and stroke:
                color = stroke.group(1)

            dx, dy = x2 - x1, y2 - y1
            L = math.hypot(dx, dy)
            if L == 0:
                return m.group(0)
            ux, uy = dx / L, dy / L
            nx, ny = -uy, ux

            gp = []
            for lx, ly in local:
                lx, ly = lx * sw, ly * sw
                gp.append((x2 + ux * lx + nx * ly, y2 + uy * lx + ny * ly))

            d = "M " + " L ".join(f"{px:.2f},{py:.2f}" for px, py in gp) + " Z"
            total += 1
            clean = re.sub(r'\s*marker-end="url\(#[^"]*\)"', "", allattrs).rstrip()
            return f'<line {clean}/><path d="{d}" fill="{color}" stroke="none"/>'

        svg, n = pat.subn(repl, svg)

    # 已展开的 marker 引用若还残留，记下来交给调用方告警
    for m in re.finditer(r'marker-(?:start|mid|end)="url\(#([^)]*)\)"', svg):
        leftovers.append(m.group(1))

    # 移除已经用不到的 defs（仅当其中只剩 marker 时）
    svg = re.sub(r"<defs>\s*(?:<marker\b.*?</marker>\s*)*</defs>", "", svg, flags=re.S)
    return svg, total, leftovers


def make_responsive(svg: str, orig_w: int, orig_h: int) -> str:
    """去掉固定宽高，换成 width:100% 响应式。"""
    m = re.search(r"<svg\b([^>]*)>", svg)
    if not m:
        return svg
    attrs = m.group(1)
    attrs = re.sub(r'\swidth="[^"]*"', "", attrs, count=1)
    attrs = re.sub(r'\sheight="[^"]*"', "", attrs, count=1)
    if "viewBox" not in attrs:
        attrs = f' viewBox="0 0 {orig_w} {orig_h}"' + attrs
    ratio = round(orig_h / orig_w, 4)
    style = f'style="width:100%;height:auto;vertical-align:top;" data-w="{orig_w}" data-ratio="{ratio}"'
    if "style=" not in attrs:
        attrs = " " + style + attrs
    return svg[: m.start()] + f"<svg{attrs}>" + svg[m.end():]


def convert(path: str, strip_font: bool = False) -> tuple[str, dict]:
    raw = open(path, encoding="utf-8").read()
    svg = strip_xml(raw)

    dim = re.search(r'\bwidth="(\d+)"\s+height="(\d+)"', svg)
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if dim:
        orig_w, orig_h = int(float(dim.group(1))), int(float(dim.group(2)))
    elif vb:
        orig_w, orig_h = int(float(vb.group(1))), int(float(vb.group(2)))
    else:
        raise ValueError(f"无法确定尺寸（既无 width/height 也无 viewBox）: {path}")

    markers = parse_markers(svg)
    svg, n_markers, leftover = expand_markers(svg, markers)
    svg = make_responsive(svg, orig_w, orig_h)

    if strip_font:
        svg = re.sub(r'\s*font-family="[^"]*"', "", svg)

    # 非 marker 类的 id 引用（渐变/裁剪/滤镜）本工具不处理，单独告警
    other_refs = sorted(
        set(re.findall(r"url\(#([^)]*)\)", svg)) - set(markers.keys())
    )

    info = {
        "file": os.path.basename(path),
        "size": f"{orig_w}x{orig_h}",
        "markers_found": len(markers),
        "markers_expanded": n_markers,
        "unsupported_refs": other_refs,
        "leftover_marker_refs": leftover,
        "has_id_left": bool(re.search(r'\bid="', svg)),
        "has_defs_left": "<defs" in svg,
    }
    return svg, info


def wrap_html(svg: str) -> str:
    return '<section style="text-align:center;margin:0;padding:0;">\n' + svg + "\n</section>"


def report(info: dict, stream=sys.stderr):
    warn = bool(info["unsupported_refs"] or info["leftover_marker_refs"])
    print(
        f"{'WARN' if warn else 'ok  '} {info['file']:<34s} "
        f"size={info['size']:<10s} markers={info['markers_expanded']}/{info['markers_found']}",
        file=stream,
    )
    if info["unsupported_refs"]:
        print(f"     未处理的 id 引用（微信会剥离 id，需手工展开）: {info['unsupported_refs']}", file=stream)
    if info["leftover_marker_refs"]:
        print(f"     残留 marker 引用: {info['leftover_marker_refs']}", file=stream)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="+")
    ap.add_argument("-o", "--output")
    ap.add_argument("-o-dir", "--output-dir", help="批量模式：输出目录（保留原文件名）")
    ap.add_argument("--svg-only", action="store_true", help="输出处理后的 svg 而非 HTML 片段")
    ap.add_argument("--strip-font-family", action="store_true", help="删除 font-family")
    a = ap.parse_args()

    if a.output_dir:
        os.makedirs(a.output_dir, exist_ok=True)

    for path in a.input:
        try:
            svg, info = convert(path, strip_font=a.strip_font_family)
        except Exception as e:
            print(f"FAIL {os.path.basename(path)}: {e}", file=sys.stderr)
            continue
        report(info)
        out = svg if a.svg_only else wrap_html(svg)

        if a.output_dir:
            ext = ".svg" if a.svg_only else ".html"
            dst = os.path.join(a.output_dir, os.path.splitext(os.path.basename(path))[0] + ext)
            open(dst, "w", encoding="utf-8").write(out)
        elif a.output:
            open(a.output, "w", encoding="utf-8").write(out)
            print(f"-> {a.output}", file=sys.stderr)
        else:
            print(out)


if __name__ == "__main__":
    main()
