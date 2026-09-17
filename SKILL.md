---
name: wechat-publisher
slug: wechat-publisher
version: 2.0.0
displayName: 微信公众号发布助手
display_name: 微信公众号发布助手
display_name_en: WeChat Publisher
description: 一键发布 Markdown 到微信公众号草稿箱。支持图文消息（长文）和图片消息（贴图）两种模式。
description_zh: 一键发布 Markdown 到微信公众号草稿箱，支持图文长文与图片贴图两种模式；纯 Python 标准库自闭环实现，无需安装任何外部 CLI，图文正文可直接内联 SVG 矢量图。
description_en: Publish Markdown to WeChat Official Account drafts. Self-contained pure-Python toolchain with zero external CLI dependencies; supports rich articles and image posts, inline SVG works in article bodies.
allowed-tools: null
---

# wechat-publisher

**一键发布 Markdown 到微信公众号草稿箱（自闭环，零外部依赖）**

v2.0 起渲染与发布引擎全部内置（纯 Python 标准库），不再依赖任何第三方
排版/发布 CLI——渲染、样式内联、代码高亮、图片上传、草稿创建、发布自检
全部在本 skill 内完成，任何装有 Python 3.9+ 的机器克隆即用。

支持两种发布模式：
- **图文消息（长文）**：`publish.sh` / `publish_article.py`，富文本排版 + 代码高亮 + 链接转脚注
- **图片消息（贴图）**：`wechat-image-post.py`，多图横滑浏览，图片由 `image_info` 承载

## 功能概览

| 模式 | 脚本 | 说明 |
|------|------|------|
| 图文消息 | `scripts/publish.sh` → `publish_article.py` | 自研渲染引擎：Markdown → 主题化内联样式 HTML |
| 图片消息 | `scripts/wechat-image-post.py` | 多图发布为横滑贴图（需 requests） |

## 架构（自闭环渲染引擎）

```
scripts/
├── publish_article.py   # 图文发布主入口（frontmatter/图片替换/封面/草稿/自检）
├── md_render.py         # Markdown → HTML 渲染器 + mini 语法高亮（hljs 兼容）
├── css_inline.py        # 轻量 DOM + CSS 内联引擎（变量解析/伪元素展开/微信兼容后处理）
├── wechat-image-post.py # 贴图发布（newspic）
├── svg2wechat.py        # SVG → 微信内联片段转换器
├── setup.sh             # 凭证加载
└── themes/
    ├── *.css            # 12 个排版主题
    └── highlight/*.css  # 9 个代码高亮主题
```

渲染管线：Markdown 解析 → `<section id="article">` 包裹 → 主题 CSS
内联（CSS 变量解析、按出现顺序层叠）→ 伪元素（::before/::after）展开为
真实元素 → 代码高亮 CSS 内联 → 链接转脚注 → 微信兼容后处理（code 换行
转 `<br>`、空格转 U+00A0、li 包裹 section、嵌套列表扁平化）。

发布管线：stable_token（本地缓存，600s 提前刷新）→ 正文图片上传替换
（md5 去重缓存）→ 封面上传 → `draft/add` → `draft/count` + `draft/get`
闭环自检（防静默失败）。

## 图片格式支持边界（2026-09-17 线上实测）

**两种模式对 SVG 的支持完全不同，别混用：**

| 模式 | 能否用 SVG | 怎么做 |
|------|-----------|--------|
| 图文消息（长文） | 能，直接用内联 `<svg>` | 用 `scripts/svg2wechat.py` 转成响应式片段贴进正文 |
| 图片消息（贴图） | 不能，必须转位图 | SVG 先渲染成 2x PNG 再发布 |

贴图路径为什么不行，两条路都堵死：

1. **图片入口**：贴图图片走 `material/add_material` 拿 `image_media_id`，该接口对 SVG 文件返回 `40113 unsupported file type`，物理上收不进去。
2. **caption 入口**：贴图的 `content` 是纯文本 caption，**不是 HTML**。实测把 `<svg>` 标签塞进去，服务端会原样存下、不做转义，但读者端只当字面文本渲染——结果就是在贴图里露出一行 `<svg xmlns=...>` 代码。

> 判定依据：`draft/get` 能存下标签 ≠ 读者端会解析。贴图类型在设计上就不解析正文 HTML。

内联 SVG 的正确用法见下文「SVG 图片支持情况」章节。

---

## 模式一：图文消息（长文）

### 1. 准备 Markdown 文件

```markdown
---
title: 文章标题（必填）
cover: ./assets/cover.jpg    # 封面图（可选，缺省取正文第一张图）
description: 文章摘要        # 可选，渲染为开头引用块 + 草稿摘要
author: 作者名               # 可选
theme: lapis                # 可选，也可用命令行 --theme 指定
---

# 正文开始

你的内容，支持 Markdown 语法...
```

### 2. 发布命令

```bash
source ~/.wechat-credentials.env
bash ~/.workbuddy/skills/wechat-publisher/scripts/publish.sh /path/to/article.md
```

指定主题与高亮：

```bash
./scripts/publish.sh article.md lapis solarized-light
```

直接调 Python 入口（全部选项）：

```bash
python3 scripts/publish_article.py article.md \
  --theme lapis --highlight github \
  --no-footnote --no-mac-style \
  --render-only preview.html   # 只渲染不发布，本地预览
```

**主题**（`scripts/themes/`）：default / juejin_default / lapis / maize /
medium_default / orangeheart / phycat / pie / purple / rainbow /
toutiao_default / zhihu_default

**高亮**（`scripts/themes/highlight/`）：atom-one-dark / atom-one-light /
dracula / github-dark / github / monokai / solarized-dark /
solarized-light / xcode

### 3. 技术细节

- **代码高亮**：内置 mini 高亮器（python/js/ts/cpp/c/java/go/rust/bash/
  json/yaml/css/sql），输出 hljs 兼容 class，9 套高亮主题即插即用
- **链接转脚注**：公众号正文外链会被过滤，默认把 `<a>` 转为斜体文本 +
  上标序号，文末生成「引用链接」块（`--no-footnote` 关闭）
- **图片上传**：本地/网络图片自动上传 `material/add_material` 并替换
  src，md5 去重（`~/.config/wechat-publisher/upload-cache.json`）
- **token**：stable_token + 本地缓存（`~/.config/wechat-publisher/token.json`），
  40001 自动清缓存重试
- **发布自检**：每次发布后自动 `draft/count` 前后对比 + `draft/get` 读回
  标题校验，失败即报错，不会静默成功

### 4. 常见错误排查

| 错误码 | 原因 | 解决方案 |
|--------|------|----------|
| 40164 | IP 不在白名单 | 公众号后台添加运行机器 IP |
| 40001 | token 失效 | 自动重试；仍失败删 `~/.config/wechat-publisher/token.json` |
| 40007 | media_id 无效 | 图片需走永久素材接口（脚本已内置） |
| 40005/40113 | SVG 直传 | 转 PNG，或用 `svg2wechat.py` 内联进正文 |
| 45004 | digest/封面超限 | 封面 ≤64KB，摘要 ≤120 字 |
| 40125 | AppSecret 错误 | 后台重置密码并更新凭证文件 |

---

## 模式二：图片消息（贴图）

直接调用 Python 脚本（依赖 requests）。

### 1. 准备 Markdown 文件

> **格式规范（与小红书笔记对齐）**：所有字段写在 frontmatter（`---` 之间），正文放图片 `![]()` 引用和纯文本 caption。

```markdown
---
title: 今日份的少女图鉴
cover: ./assets/cover.jpg    # 封面图路径（必填，脚本自动处理缩放≤64KB）
tags: ["少女", "写真", "氛围感"]   # 话题标签（可选，仅作记录）
author: WorkBuddy           # 作者（可选，≤8 字符纯文本）
---

一组精选图片，分享给大家。

![](01.jpeg)
![](02.jpeg)
```

### 2. 发布命令

```bash
source ~/.wechat-credentials.env
$HOME/.workbuddy/binaries/python/envs/default/bin/python3 \
  ~/.workbuddy/skills/wechat-publisher/scripts/wechat-image-post.py /path/to/post.md
```

> **注意**：系统 `python3` 没装 requests，用隔离 venv 的 python 跑。

### 3. 技术细节

- **封面图**：首张图片自动作为封面（需 ≤64KB，自动缩放）
- **图片上传**：全部走 `material/add_material` 永久素材接口
- **Payload 结构**：`article_type=newspic` + `image_info.image_list`
- **正文限制**：`content` 字段为纯文本 caption（newspic 类型不支持 HTML）

### 4. 常见错误排查

| 错误码 | 原因 | 解决方案 |
|--------|------|----------|
| 40007 | media_id 无效 | 确保所有图片通过 `material/add_material` 上传 |
| 45004 | digest/content 超限 | 缩短纯文本 caption，封面图需 ≤64KB |
| 45166 | caption 含 URL 风格路径 | 零 `http://` / `github.com` / 作者 ID，只留产品名 |
| 45110 | author 超限 | ≤8 字符纯文本，不能含注释 |

---

## SVG 图片支持情况（2026-09-17 线上实测）

**结论：微信图床不收 SVG 文件本体。图文和贴图都必须先转位图。**

| 路径 | 结果 |
|------|------|
| `media/uploadimg`（正文内嵌图）传 SVG | 40005 invalid file type |
| `material/add_material?type=image`（永久素材）传 SVG | 40113 unsupported file type |
| `media/upload?type=image`（临时素材）传 SVG | 40005 |
| 正文内联 `<svg>` 标签 | 可入库，但 `id` 属性被剥离（详见下） |
| 正文 `data:image/svg+xml;base64` | 入库保留，实际不显示，别用 |
| SVG 渲染成 PNG 后上传 | 正常 |

**改 Content-Type 谎报 `image/png` 无效** —— 微信是解析文件内容判定类型，不看请求头。

### 标准做法：SVG → 高分辨率 PNG

```bash
$HOME/.workbuddy/binaries/python/envs/default/bin/python3 \
  ~/.workbuddy/skills/svg-studio/scripts/render.py input.svg --scale 2 -o output.png
```

微信会把正文图压成宽 640px 缩略图，手机端可点开原图，所以传 2×/3× 位图点开仍清晰。

### 内联 `<svg>` 的三个坑（实测读回原文比对）

微信把正文当 **HTML** 解析后重新序列化：

1. **`id` 属性 100% 被剥离** —— `<marker id="m0a">` 读回后 `id` 消失，导致 `url(#m0a)` 悬空。**不要用 `id` 引用**：`<defs>` + `marker`/`linearGradient`/`clipPath` 全部失效，箭头/渐变/裁剪必须展开成显式路径与实色。
2. **属性名小写化** —— `viewBox` → `viewbox`、`refX` → `refx`。浏览器有 SVG 属性名修正表，渲染时通常能纠正回来，风险可控。
3. **体积膨胀 2.3 倍** —— 自闭合标签展开为成对标签，属性值单引号实体化为 `&#39;`（10KB → 24KB）。

另外官方明确：不支持外部引用的 SVG、`<animate>` 动效部分编辑器不兼容、正文不能只有图必须有文字。

### 正文渲染已确认可行（2026-09-17 实测）

`draft/get` 返回的是**存储的原文**，不是渲染结果，看到标签"保留"不等于读者端会显示。要下定论必须在后台草稿箱点预览到手机。

**已确认的三件事**：

1. **内联 `<svg>` 在读者端正常渲染**，这条路走得通。
2. **响应式宽高是关键变量** —— 固定 `width="1120"` 在手机上横向溢出，改成 `width:100%;height:auto` 后显示正常。
3. **`id` 剥离会让箭头直接消失** —— 本地复现：把同一张图里全部 `id` 属性剥掉再渲染，10 个箭头三角形全部消失、只剩光秃的线。机制是 `url(#m0a)` 找不到目标，marker 不渲染。

**所以「展开成显式路径」不是可选项，是必需的** —— 依赖 `id` 的 `marker` / `linearGradient` / `clipPath` 在微信里一律失效。

### 一键转换：`scripts/svg2wechat.py`

既然内联 `<svg>` 在正文里能渲染，本脚本把转换过程自动化：

```bash
PY=$HOME/.workbuddy/binaries/python/envs/default/bin/python3
SKILL=~/.workbuddy/skills/wechat-publisher/scripts

# 单文件 -> 可直接粘进公众号编辑器的 HTML 片段
$PY $SKILL/svg2wechat.py input.svg -o out.html

# 只要处理后的 svg
$PY $SKILL/svg2wechat.py input.svg --svg-only -o out.svg

# 批量
$PY $SKILL/svg2wechat.py images/*.svg --svg-only -o-dir out/
```

自动完成三件事：去掉 XML 声明与固定宽高改成 `width:100%` 响应式、把 marker 箭头展开成显式 `<path>` 三角形（**支持一张图里多个 marker**，按每条线的 `stroke-width` 精确缩放）、输出可直接粘贴的片段。

**读输出里的告警**：若报 `unsupported_refs`（`linearGradient` / `clipPath` / `filter` 之类），说明该图还有本工具没展开的 id 引用，微信里同样会失效，需要手工展开成实色或显式路径。

几何正确性已用 40 张真实插图回归验证：同尺寸渲染对比，像素差异 0.004%（仅抗锯齿边界）。

### 内嵌 SVG 直接写进 Markdown

图文模式下，Markdown 里的原始 HTML 块（含多行 SVG）会**原样透传**进正文，
配合 `svg2wechat.py` 预处理后的片段即可直接内联矢量图：

````markdown
---
title: 带矢量插图的文章
---

<section><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 400" style="width:100%;height:auto">
<!-- svg2wechat.py 处理后的内容 -->
</svg></section>
````

---

## 故障排查

### 1. IP 不在白名单
```bash
curl ifconfig.me  # 获取公网 IP
# 登录微信公众平台 → 设置与开发 → 基本配置 → IP 白名单 → 添加
```

### 2. 环境变量未设置
```bash
source ./scripts/setup.sh
# 或
grep -rln "WECHAT_APP_ID" ~/WorkBuddy 2>/dev/null  # 凭据可能在其他工作目录
```

### 3. wechat-image-post.py 报 `ModuleNotFoundError: No module named 'requests'`（贴图）
用隔离 venv 的 python 跑（见模式二发布命令）。图文模式（publish_article.py）纯标准库，系统 python3 直接跑。

### 4. 封面图尺寸建议

推荐 **1080×864 像素，且 ≤ 64KB**。一行命令制作：

```bash
magick source.png \
  -resize 1080x864^ -gravity center -extent 1080x864 \
  -quality 70 \
  cover.jpg
```

详细排查指南见 [references/troubleshooting.md](references/troubleshooting.md)。

---

## 参考资料

- [微信公众号 draft/add 文档](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)
- [微信公众号素材管理文档](https://developers.weixin.qq.com/doc/offiaccount/Asset_Management/Adding_Permanent_Assets.html)
