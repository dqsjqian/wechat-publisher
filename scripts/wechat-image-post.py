#!/usr/bin/env python3
"""
微信公众号贴图发布脚本 - 发布 news_pic 类型图文到草稿箱

frontmatter 规范（与小红书笔记对齐）：
  title: 标题             # 必填
  cover: ./cover.jpg      # 必填，封面图相对路径
  tags: ["标签1", "标签2"]  # 可选，仅作记录
  author: 作者名           # 可选

用法:
  python3 wechat-image-post.py /path/to/post.md
"""

import os
import re
import sys
import json
import requests
import argparse
from pathlib import Path

# ── 凭证配置 ─────────────────────────────────────────
APP_ID = os.environ.get("WECHAT_APP_ID", "")
APP_SECRET = os.environ.get("WECHAT_APP_SECRET", "")

# ── API ───────────────────────────────────────────────
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
UPLOAD_URL = "https://api.weixin.qq.com/cgi-bin/media/upload"
MATERIAL_ADD_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"


def get_access_token():
    """获取 access_token"""
    params = {"grant_type": "client_credential", "appid": APP_ID, "secret": APP_SECRET}
    resp = requests.get(TOKEN_URL, params=params, timeout=15)
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"获取 token 失败: {data}")
    return data["access_token"]


def upload_image(token: str, image_path: str, img_type: str = "image") -> str:
    """上传图片到永久素材库，返回 media_id（thumb类型返回thumb_media_id）"""
    url = f"{UPLOAD_URL}?access_token={token}&type={img_type}"
    with open(image_path, "rb") as f:
        files = {"media": (os.path.basename(image_path), f, "image/jpeg")}
        resp = requests.post(url, files=files, timeout=30)
    data = resp.json()
    # thumb 类型返回 thumb_media_id，普通 image 类型返回 media_id
    mid = data.get("media_id") or data.get("thumb_media_id")
    if not mid:
        raise RuntimeError(f"上传图片失败 [{image_path}] (type={img_type}): {data}")
    return mid


def upload_material(token: str, image_path: str, material_type: str = "image") -> str:
    """通过永久素材接口上传图片，返回 media_id"""
    url = f"{MATERIAL_ADD_URL}?access_token={token}&type={material_type}"
    with open(image_path, "rb") as f:
        files = {"media": (os.path.basename(image_path), f, "image/jpeg")}
        resp = requests.post(url, files=files, timeout=30)
    data = resp.json()
    if "media_id" not in data:
        raise RuntimeError(f"永久素材上传失败 [{image_path}]: {data}")
    return data["media_id"]


def add_draft(token: str, title: str, author: str, content: str, media_ids: list) -> dict:
    """发布图片消息到草稿箱（article_type=newspic）"""
    # 构建 image_list，首张图片自动作为封面
    image_list = [{"image_media_id": mid} for mid in media_ids]

    # digest 取 content 纯文本前54字
    digest = content[:54] + ("..." if len(content) > 54 else "")

    payload = {
        "articles": [
            {
                "title": title,
                "author": author or "",
                "digest": digest,
                "content": content,
                "content_source_url": "",
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
                "article_type": "newspic",
                "image_info": {
                    "image_list": image_list,
                },
            }
        ]
    }

    url = f"{DRAFT_URL}?access_token={token}"
    resp = requests.post(
        url,
        data=json.dumps(payload, ensure_ascii=False),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=15,
    )
    data = resp.json()
    return data


def parse_frontmatter(content: str):
    """解析 frontmatter，返回 (metadata_dict, 正文)

    支持格式（与小红书笔记 frontmatter 对齐）：
      title: 我的标题
      cover: ./cover.jpg
      tags: ["标签1", "标签2"]
      author: 作者名
    """
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    meta_str, body = parts[1], parts[2]
    meta = {}
    for line in meta_str.strip().split("\n"):
        if not line.strip() or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")  # 去首尾引号

        # tags: ["tag1", "tag2"] → 解析为 list
        if val.startswith("[") and val.endswith("]"):
            tags_raw = val[1:-1]
            tags = [t.strip().strip('"').strip("'") for t in tags_raw.split(",") if t.strip()]
            meta[key] = tags
        else:
            meta[key] = val
    return meta, body


def build_content(title: str, body_text: str, image_refs: list, base_dir: Path) -> str:
    """构建纯文本内容（newspic类型content不支持HTML，图片由image_info承载）"""
    # 提取纯文本段落（去掉 markdown 图片引用）
    lines = []
    for line in body_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("![]"):
            continue
        lines.append(line)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="发布微信公众号贴图（newspic）到草稿箱")
    parser.add_argument("content_file", help="Markdown 文件路径（含 frontmatter 和图片引用）")
    args = parser.parse_args()

    if not APP_ID or not APP_SECRET:
        print("❌ 错误：环境变量 WECHAT_APP_ID / WECHAT_APP_SECRET 未设置")
        print("   请先 source 凭据文件：")
        print("   source $HOME/.wechat-credentials.env")
        sys.exit(1)

    # 读取 markdown
    md_path = Path(args.content_file).expanduser().resolve()
    with open(md_path, encoding="utf-8") as f:
        raw = f.read()

    meta, body = parse_frontmatter(raw)
    title = meta.get("title", "").strip('"').strip("'")
    author = meta.get("author", "").strip('"').strip("'")
    tags = meta.get("tags", [])

    if not title:
        print("❌ frontmatter 缺少必填字段：title")
        sys.exit(1)

    base_dir = md_path.parent

    # 提取图片路径
    image_refs = []
    body_lines = body.strip().split("\n")
    text_lines = []
    for line in body_lines:
        if line.strip().startswith("![]"):
            ref = line.strip()[4:].strip("()[]")
            image_refs.append(ref)
        else:
            text_lines.append(line)

    if not image_refs:
        print("❌ 未找到图片（格式：![](path/to/image.jpg））")
        sys.exit(1)

    print(f"📝 标题: {title}")
    print(f"👤 作者: {author or '（未填写）'}")
    if tags:
        print(f"🏷️  标签: {', '.join(tags)}")
    print(f"📷 图片数: {len(image_refs)}")

    # 获取 token
    print("🔑 获取 access_token...")
    token = get_access_token()

    # 上传图片：newspic 类型全部用永久素材接口 material/add_material
    media_ids = []
    for ref in image_refs:
        img_path = base_dir / ref
        if not img_path.exists():
            print(f"⚠️  图片不存在，跳过: {img_path}")
            continue
        print(f"  ↑ 上传 {img_path.name} (material/image)...", end=" ", flush=True)
        mid = upload_material(token, str(img_path), "image")
        print(f"✓ {mid}")
        media_ids.append(mid)

    if not media_ids:
        print("❌ 没有成功上传任何图片")
        sys.exit(1)

    # 构建内容
    content_html = build_content(title, "\n".join(text_lines), image_refs, base_dir)

    # 发布草稿
    print("📤 发布到草稿箱...")
    result = add_draft(token, title, author, content_html, media_ids)

    if "media_id" in result:
        print(f"✅ 发布成功！Media ID: {result['media_id']}")
    else:
        print(f"❌ 发布失败: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
