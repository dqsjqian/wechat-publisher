# wechat-publisher

**一键发布 Markdown 到微信公众号草稿箱，自闭环零依赖**

纯 Python 标准库实现完整工具链：Markdown 渲染、主题排版、代码高亮、
CSS 内联、图片上传、草稿创建、发布自检——不依赖任何第三方 CLI，
克隆即用，只需要 Python 3.9+。

---

## 功能特性

- **自闭环渲染引擎** - 自研 Markdown → 公众号 HTML 管线，无需安装 Node.js / npm 包
- **两种发布模式** - 图文消息（长文）与图片消息（贴图），覆盖公众号两种内容形态
- **多主题支持** - lapis、phycat、orangeheart 等 12 个内置排版主题
- **代码高亮** - 9 种高亮主题，内置 mini 语法高亮器（Python/C++/JS/Go/Rust 等 14 种语言）
- **CSS 内联引擎** - 主题样式自动内联为 inline style（公众号编辑器只认元素级样式），支持 CSS 变量与伪元素展开
- **链接转脚注** - 公众号正文外链会被过滤，自动转为文末引用块
- **SVG 矢量图** - 图文正文可直接内联 SVG（自动展开箭头 marker、改响应式宽度）
- **发布自检** - 每次发布后自动 draft/count 对比 + draft/get 读回校验，杜绝静默失败
- **智能缓存** - access_token 本地缓存自动续期，图片 md5 去重不重复占素材额度
- **安全设计** - 凭证只从环境变量或本地凭证文件读取，不进仓库

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/dqsjqian/wechat-publisher.git
cd wechat-publisher
```

### 2. 配置 API 凭证

创建 `~/.wechat-credentials.env`：

```bash
export WECHAT_APP_ID=your_wechat_app_id
export WECHAT_APP_SECRET=your_wechat_app_secret
```

凭证文件路径可用 `WECHAT_CRED_FILE` 覆盖。

**IP 白名单**：确保运行机器的公网 IP 已加入公众号后台白名单，否则接口会报 `40164`。

**如何获取凭证：**
1. 登录微信公众号后台：https://mp.weixin.qq.com/
2. 设置与开发 → 基本配置 → 开发者ID(AppID) 和 开发者密码(AppSecret)
3. 同页面添加服务器 IP 到白名单

### 3. 发布测试文章

```bash
./scripts/publish.sh example.md
```

### 4. 查看草稿箱

前往微信公众号后台查看：https://mp.weixin.qq.com/

---

## 模式一：图文消息（长文）

### Markdown 格式要求

文件顶部**必须**包含 frontmatter：

```markdown
---
title: 文章标题（必填！）
cover: ./assets/cover.jpg  # 封面图（可选，缺省取正文第一张图）
description: 文章摘要      # 可选：渲染为开头引用块 + 草稿摘要
author: 作者名             # 可选
---

# 正文开始

你的内容...
```

**封面图：**
- **相对路径**（推荐，相对于 md 文件目录）
- **绝对路径** / **网络图片**
- **尺寸建议**：1080×864、≤64KB

### 发布命令

```bash
# 基本用法（默认 lapis 主题）
./scripts/publish.sh article.md

# 指定主题和代码高亮
./scripts/publish.sh article.md lapis solarized-light

# 先本地预览，不发布
python3 scripts/publish_article.py article.md --render-only preview.html
```

**主题**：default / juejin_default / lapis / maize / medium_default /
orangeheart / phycat / pie / purple / rainbow / toutiao_default / zhihu_default

**高亮**：atom-one-dark / atom-one-light / dracula / github-dark / github /
monokai / solarized-dark / solarized-light / xcode

完整选项见 `python3 scripts/publish_article.py --help`。

---

## 模式二：图片消息（贴图）

多图横滑浏览形态，图片由 `image_info` 承载（依赖 `requests`）。

```markdown
---
title: 今日份的图鉴
cover: ./assets/cover.jpg    # 必填，脚本自动缩放到 ≤64KB
tags: ["标签1", "标签2"]      # 可选，仅作记录
author: 作者名                # 可选，≤8 字符纯文本
---

正文文本作为 caption 显示，不支持 Markdown 格式。

![](01.jpeg)
![](02.jpeg)
```

```bash
pip install requests
source ./scripts/setup.sh
python3 scripts/wechat-image-post.py /path/to/post.md
```

**注意事项：**
- `content` 是**纯文本 caption**，不支持任何标签
- caption 里不要出现 URL 风格的路径，会触发 `45166 invalid content`
- `author` 字段 ≤ 8 字符纯文本

---

## 主题预览

| 主题 | 风格 | 适合场景 |
|------|------|----------|
| **lapis** | 蓝色优雅 | 技术文章、教程（推荐） |
| **phycat** | 薄荷绿清新 | 博客、随笔 |
| **default** | 经典简约 | 通用场景 |
| **orangeheart** | 橙心暖调 | 产品介绍 |
| **purple** | 紫色神秘 | 设计、创意 |

查看完整主题列表：[references/themes.md](references/themes.md)

---

## SVG 矢量图支持

两种模式的结论完全不同，实测确认（2026-09-17）：

| 模式 | 能否直接用 SVG |
|------|---------------|
| 图文消息（长文） | 可以，内联 `<svg>` 标签 |
| 图片消息（贴图） | 不行，必须先渲染成 PNG |

微信图片素材接口只收 bmp / png / jpeg / jpg / gif，SVG 文件本体一律拒绝
（`40005` / `40113`），改 Content-Type 也没用——服务端按文件内容判定类型。

### 图文消息：一键转换

```bash
python3 scripts/svg2wechat.py 图.svg -o 片段.html
```

脚本自动完成两件事：

1. **改响应式** —— 去掉固定 `width/height`，换成 `width:100%;height:auto`，手机窄屏不溢出
2. **展开箭头 marker** —— 微信会剥掉正文里所有 `id` 属性，导致 `marker-end="url(#id)"` 引用悬空、箭头直接消失；脚本把每个箭头提前算成显式 `<path>` 三角形

转换后的片段可直接内嵌进 Markdown（原始 HTML 块会原样透传进正文）。

### 贴图：先转位图

```bash
# 任意 SVG → PNG 渲染器均可，2x 缩放保证点开清晰
python3 your-renderer.py 图.svg --scale 2 -o 图.png
```

详细原理和实测数据见 [SKILL.md](SKILL.md) 的「SVG 图片支持情况」章节。

---

## 故障排查

**1. `40164 (IP地址不在白名单中)`** → 公众号后台添加 IP 白名单

**2. `40125` AppSecret 错误** → 后台重置并更新凭证文件

**3. `40001 invalid credential`** → 脚本自动清缓存重试；仍失败手动删
`~/.config/wechat-publisher/token.json`

**4. `40005 / 40113` SVG 直传** → 转 PNG 或用 `svg2wechat.py` 内联进正文

**5. `45166 invalid content`（贴图）** → caption 只留纯文本，去掉 URL 风格路径

**6. 发布成功但看不到文章？** → 文章在草稿箱，需到后台手动群发

查看完整故障排查指南：[references/troubleshooting.md](references/troubleshooting.md)

---

## 项目结构

```
wechat-publisher/
├── SKILL.md                       # 完整文档（含实测数据与坑位记录）
├── README.md                      # 本文件
├── example.md                     # 测试文章示例
├── scripts/
│   ├── publish_article.py         # 图文发布主入口（纯标准库）
│   ├── md_render.py               # Markdown 渲染器 + mini 语法高亮
│   ├── css_inline.py              # CSS 内联引擎（轻量 DOM）
│   ├── publish.sh                 # 图文发布 shell 包装
│   ├── setup.sh                   # 凭证加载
│   ├── wechat-image-post.py       # 图片贴图发布（需 requests）
│   ├── wechat-image-post.sh       # 上者的 shell 包装
│   ├── svg2wechat.py              # SVG → 微信内联片段转换器
│   └── themes/
│       ├── *.css                  # 12 个排版主题
│       ├── highlight/*.css        # 9 个代码高亮主题
│       └── LICENSE                # 样式资产来源说明
└── references/
    ├── themes.md                  # 主题列表和使用说明
    └── troubleshooting.md         # 详细故障排查指南
```

---

## 高级用法

### 自定义主题

主题就是普通 CSS 文件（选择器以 `#article` 为容器前缀），放进
`scripts/themes/` 即可按文件名使用：

```bash
cp my-theme.css scripts/themes/
python3 scripts/publish_article.py article.md --theme my-theme
```

### 批量发布

```bash
for file in articles/*.md; do
    ./scripts/publish.sh "$file"
done
```

### CI / 自动化

`publish_article.py` 所有输出走 stdout/stderr，退出码非 0 即失败
（含自检失败），适合接自动化流水线。

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。
样式资产的来源说明见 [scripts/themes/LICENSE](scripts/themes/LICENSE)。

---

## 联系方式

- **GitHub**: [@dqsjqian](https://github.com/dqsjqian)
- **Issues**: [提交问题](https://github.com/dqsjqian/wechat-publisher/issues)

---

**如果这个项目对你有帮助，请给个 Star！**
