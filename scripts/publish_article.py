#!/usr/bin/env python3
"""publish_article.py — 图文长文一键发布（纯标准库，自闭环）

流程：Markdown → 渲染（主题/高亮/内联样式）→ 正文图片上传替换 →
封面上传 → 创建草稿 → draft/count + draft/get 闭环自检。

前置条件：
- 环境变量 WECHAT_APP_ID / WECHAT_APP_SECRET（可 source 凭证文件）
- 公网 IP 已加入公众号后台白名单

用法：
  python3 publish_article.py article.md
  python3 publish_article.py article.md --theme lapis --highlight github
  python3 publish_article.py article.md --render-only preview.html
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import css_inline  # noqa: E402
import md_render  # noqa: E402

# ---------------------------------------------------------------------------
# 微信 API（urllib 实现，无第三方依赖）
# ---------------------------------------------------------------------------

API_BASE = "https://api.weixin.qq.com/cgi-bin"
TOKEN_URL = f"{API_BASE}/stable_token"
ADD_MATERIAL_URL = f"{API_BASE}/material/add_material"
DRAFT_ADD_URL = f"{API_BASE}/draft/add"
DRAFT_COUNT_URL = f"{API_BASE}/draft/count"
DRAFT_GET_URL = f"{API_BASE}/draft/get"

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "wechat-publisher",
)
TOKEN_CACHE = os.path.join(CONFIG_DIR, "token.json")
UPLOAD_CACHE = os.path.join(CONFIG_DIR, "upload-cache.json")

ERROR_HINTS = {
    40001: "access_token 无效或已过期（缓存自动清除，请重试）",
    40004: "不合法的媒体文件类型（检查图片格式）",
    40007: "media_id 无效（素材不存在或已过期）",
    40125: "AppSecret 无效（检查凭证）",
    40164: "IP 不在白名单（公众号后台 → 设置与开发 → 基本配置 → IP 白名单）",
    40005: "不支持的文件类型（SVG 需先转 PNG，见 svg2wechat.py / render.py）",
    40113: "不支持的文件类型（SVG 需先转 PNG）",
    45004: "字段超长（digest/content 过长，封面需 ≤64KB）",
    45166: "内容不合规或超长（检查正文长度与敏感词）",
}


class WechatError(Exception):
    def __init__(self, errcode, errmsg):
        hint = ERROR_HINTS.get(errcode, "")
        msg = f"{errcode}: {errmsg}"
        if hint:
            msg = f"{msg} —— {hint}"
        super().__init__(msg)
        self.errcode = errcode


def _http_json(url, payload=None, method=None, token=None):
    if token:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}access_token={urllib.parse.quote(token)}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method=method or ("POST" if data is not None else "GET"),
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errcode", 0) != 0:
        raise WechatError(result["errcode"], result.get("errmsg", ""))
    return result


def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


def get_access_token(app_id, app_secret, force_refresh=False):
    """stable_token + 本地缓存（600s 提前量，过期自动清除）。"""
    cache = _read_json(TOKEN_CACHE, {})
    if not force_refresh:
        cached = cache.get(app_id)
        if cached and cached.get("expireAt", 0) - 600 > _now():
            return cached["accessToken"]
    payload = {
        "grant_type": "client_credential",
        "appid": app_id,
        "secret": app_secret,
        "force_refresh": bool(force_refresh),
    }
    try:
        result = _http_json(TOKEN_URL, payload)
    except WechatError:
        # 个别账号未开通 stable_token，回退老接口
        url = (
            f"{API_BASE}/token?grant_type=client_credential"
            f"&appid={urllib.parse.quote(app_id)}&secret={urllib.parse.quote(app_secret)}"
        )
        result = _http_json(url)
    cache[app_id] = {
        "accessToken": result["access_token"],
        "expireAt": _now() + int(result.get("expires_in", 7200)),
    }
    _write_json(TOKEN_CACHE, cache)
    return result["access_token"]


def _now():
    import time

    return int(time.time())


def clear_token_cache():
    try:
        os.remove(TOKEN_CACHE)
    except FileNotFoundError:
        pass


def upload_material(token, file_bytes, filename, app_id=""):
    """上传永久素材，带 md5 去重缓存。返回 {media_id, url}。"""
    digest = hashlib.md5(file_bytes).hexdigest()
    cache_key = f"{digest}:{app_id}" if app_id else digest
    cache = _read_json(UPLOAD_CACHE, {})
    cached = cache.get(cache_key)
    if cached and cached.get("media_id"):
        return cached

    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = "----FormBoundary" + uuid.uuid4().hex
    parts = []
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="media"; '
            f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'
        ).encode("utf-8")
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    req = urllib.request.Request(
        f"{ADD_MATERIAL_URL}?access_token={token}&type=image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errcode", 0) != 0:
        raise WechatError(result["errcode"], result.get("errmsg", ""))
    if str(result.get("url", "")).startswith("http://"):
        result["url"] = result["url"].replace("http://", "https://", 1)
    cache[cache_key] = {
        "media_id": result.get("media_id", ""),
        "url": result.get("url", ""),
        "updated_at": _now(),
    }
    _write_json(UPLOAD_CACHE, cache)
    return result


def add_draft(token, article):
    result = _http_json(DRAFT_ADD_URL, {"articles": [article]}, token=token)
    return result.get("media_id", "")


def count_drafts(token):
    return _http_json(DRAFT_COUNT_URL, {}, token=token).get("total_count", -1)


def get_draft(token, media_id):
    return _http_json(DRAFT_GET_URL, {"media_id": media_id}, token=token)


def delete_draft(token, media_id):
    return _http_json(f"{API_BASE}/draft/delete", {"media_id": media_id}, token=token)


# ---------------------------------------------------------------------------
# 图片处理
# ---------------------------------------------------------------------------


def upload_content_images(html, token, base_dir, app_id):
    """正文里的本地/远程图片上传微信图床并替换 src。返回 (html, first_media_id)。"""
    root = css_inline.parse_html(html)
    first_media_id = ""

    for img in list(root.iter_descendants()):
        if img.tag != "img":
            continue
        src = img.get("src", "")
        if not src or src.startswith("https://mmbiz.qpic.cn"):
            continue
        try:
            file_bytes, filename = _load_image(src, base_dir)
        except Exception as exc:
            print(f"[warn] 图片读取失败，跳过 {src}: {exc}", file=sys.stderr)
            continue
        try:
            result = upload_material(token, file_bytes, filename, app_id)
        except WechatError as exc:
            print(f"[warn] 图片上传失败，保留原 src {src}: {exc}", file=sys.stderr)
            continue
        if not first_media_id:
            first_media_id = result.get("media_id", "")
        img.set("src", result.get("url", src))
        print(f"[ok] 已上传 {filename} → {result.get('url', '')[:60]}...")

    new_html = "".join(
        css_inline.serialize(c) if not isinstance(c, str) else c
        for c in root.children
    )
    return new_html, first_media_id


def _load_image(src, base_dir):
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=60) as resp:
            return resp.read(), os.path.basename(src.split("?")[0]) or "image.jpg"
    path = src
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    path = urllib.parse.unquote(path)
    with open(path, "rb") as f:
        return f.read(), os.path.basename(path)


# ---------------------------------------------------------------------------
# 渲染 + 发布主流程
# ---------------------------------------------------------------------------


def load_theme_css(theme_id, themes_dir):
    path = os.path.join(themes_dir, f"{theme_id}.css")
    if not os.path.exists(path):
        available = sorted(
            f[:-4] for f in os.listdir(themes_dir) if f.endswith(".css")
        )
        raise SystemExit(
            f"未知主题 {theme_id}，可用主题：{', '.join(available)}"
        )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_highlight_css(hl_id, themes_dir):
    path = os.path.join(themes_dir, "highlight", f"{hl_id}.css")
    if not os.path.exists(path):
        available = sorted(
            f[:-4]
            for f in os.listdir(os.path.join(themes_dir, "highlight"))
            if f.endswith(".css")
        )
        raise SystemExit(
            f"未知高亮主题 {hl_id}，可用：{', '.join(available)}"
        )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_article(markdown_text, theme="default", highlight="solarized-light",
                   footnote=True, mac_style=True, themes_dir=None):
    """Markdown → 微信可用的内联样式 HTML。"""
    if themes_dir is None:
        themes_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "themes"
        )
    meta, body = md_render.parse_frontmatter(markdown_text)

    description = meta.get("description") or meta.get("digest") or ""
    if description:
        body = "> " + str(description) + "\n\n" + body

    body_html = md_render.render_markdown(body)

    footnote_block = ""
    if footnote:
        body_html, footnote_block = md_render.add_footnotes(body_html)

    theme_css = load_theme_css(theme, themes_dir)
    hl_css = load_highlight_css(highlight, themes_dir)
    final_html = css_inline.render_styled(
        body_html,
        theme_css,
        hl_css=hl_css,
        mac_style=mac_style,
        add_footnote_html=footnote_block,
    )
    return meta, final_html


def main():
    parser = argparse.ArgumentParser(description="发布 Markdown 图文到公众号草稿箱")
    parser.add_argument("markdown", help="Markdown 文件路径")
    parser.add_argument("--theme", default="default", help="排版主题（默认 default）")
    parser.add_argument(
        "--highlight", default="solarized-light", help="代码高亮主题"
    )
    parser.add_argument("--no-footnote", action="store_true", help="链接不转脚注")
    parser.add_argument(
        "--no-mac-style", action="store_true", help="代码块不加 Mac 圆点"
    )
    parser.add_argument(
        "--render-only", metavar="OUT.html", help="只渲染到本地文件，不发布"
    )
    parser.add_argument("--cover", help="覆盖 frontmatter 的封面图路径")
    parser.add_argument("--author", help="覆盖作者")
    parser.add_argument("--digest", help="文章摘要（≤120 字）")
    parser.add_argument("--source-url", help="原文链接")
    args = parser.parse_args()

    md_path = os.path.abspath(args.markdown)
    with open(md_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()
    base_dir = os.path.dirname(md_path)

    meta, html = render_article(
        markdown_text,
        theme=args.theme,
        highlight=args.highlight,
        footnote=not args.no_footnote,
        mac_style=not args.no_mac_style,
    )

    title = meta.get("title", "")
    if not title:
        raise SystemExit("frontmatter 缺少 title（必填）")

    if args.render_only:
        with open(args.render_only, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[ok] 已渲染 → {args.render_only}")
        return

    # ---- 发布 ----
    app_id = os.environ.get("WECHAT_APP_ID", "")
    app_secret = os.environ.get("WECHAT_APP_SECRET", "")
    if not app_id or not app_secret:
        raise SystemExit(
            "缺少凭证：请 export WECHAT_APP_ID / WECHAT_APP_SECRET，"
            "或 source 凭证文件后重试"
        )

    token = get_access_token(app_id, app_secret)

    count_before = count_drafts(token)
    html, first_media_id = upload_content_images(html, token, base_dir, app_id)

    cover = args.cover or meta.get("cover", "")
    thumb_media_id = ""
    if cover:
        file_bytes, filename = _load_image(cover, base_dir)
        result = upload_material(token, file_bytes, filename, app_id)
        thumb_media_id = result.get("media_id", "")
    elif first_media_id:
        thumb_media_id = first_media_id
    if not thumb_media_id:
        raise SystemExit("必须提供封面图（frontmatter cover 或正文至少一张图片）")

    digest = args.digest or meta.get("digest") or meta.get("description") or ""
    article = {
        "title": str(title),
        "author": str(args.author or meta.get("author", "")),
        "digest": str(digest)[:120],
        "content": html,
        "content_source_url": str(args.source_url or meta.get("source_url", "")),
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }

    try:
        media_id = add_draft(token, article)
    except WechatError as exc:
        if exc.errcode == 40001:
            clear_token_cache()
            token = get_access_token(app_id, app_secret, force_refresh=True)
            article["thumb_media_id"] = thumb_media_id
            media_id = add_draft(token, article)
        else:
            raise

    # ---- 闭环自检（防止静默失败） ----
    count_after = count_drafts(token)
    if count_after != count_before + 1:
        raise SystemExit(
            f"[自检失败] 草稿数量发布前 {count_before} / 发布后 {count_after}，"
            f"media_id={media_id}，请到公众号后台核实"
        )
    draft = get_draft(token, media_id)
    news = (draft.get("news_item") or [{}])[0]
    if news.get("title") != str(title):
        raise SystemExit(
            f"[自检失败] 读回标题不匹配：{news.get('title')!r} != {title!r}"
        )

    print(f"[ok] 发布成功 media_id={media_id}")
    print(f"[ok] 自检通过：草稿 {count_before} → {count_after}，标题一致")
    print("前往公众号后台「草稿箱」查看并群发：https://mp.weixin.qq.com/")


if __name__ == "__main__":
    main()
