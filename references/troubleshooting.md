# 故障排查指南

wechat-publisher 的常见问题和解决方案。全部脚本纯 Python 标准库实现，
无 Node.js / npm 依赖。

## 1. IP 不在白名单

**错误信息：**
```
40164: invalid ip, not in whitelist
```

**原因：** 运行机器的公网 IP 未添加到微信公众号后台白名单。

**解决方法：**

1. 获取公网 IP：
   ```bash
   curl ifconfig.me
   ```
2. 登录公众号后台 https://mp.weixin.qq.com/
3. 设置与开发 → 基本配置 → IP 白名单 → 添加
4. 重试发布

---

## 2. 环境变量未设置

**错误信息：**
```
缺少凭证：请 export WECHAT_APP_ID / WECHAT_APP_SECRET
```

**解决方法：**

**方式 1: 使用 setup.sh**
```bash
source ./scripts/setup.sh
```

**方式 2: 手动设置（临时）**
```bash
export WECHAT_APP_ID=your_wechat_app_id
export WECHAT_APP_SECRET=your_wechat_app_secret
```

**方式 3: 凭证文件**（默认 `~/.wechat-credentials.env`，可用
`WECHAT_CRED_FILE` 指定其他路径）
```bash
export WECHAT_APP_ID=your_wechat_app_id
export WECHAT_APP_SECRET=your_wechat_app_secret
```

**获取凭证：** 公众号后台 → 设置与开发 → 基本配置 → 开发者ID(AppID) /
开发者密码(AppSecret)，同页面添加 IP 白名单。

---

## 3. Frontmatter 缺失（最常见）

**错误信息：**
```
frontmatter 缺少 title（必填）
```

**解决方法：**

**方案 1：有封面图**
```markdown
---
title: 你的文章标题
cover: /path/to/cover.jpg
---

# 正文开始
```

**方案 2：无封面图（正文有图片即可，自动用第一张图做封面）**
```markdown
---
title: 你的文章标题
---

# 正文

![配图](./images/pic.jpg)

内容...
```

**关键点：**
- `title` 必填；`cover` 可选（缺省时取正文第一张上传成功的图）
- frontmatter 必须在文件最顶部，用 `---` 包围
- `description` / `digest` 可选：会作为文章摘要，并渲染为正文开头引用块

---

## 4. 图片上传失败

**错误信息：**
```
40005: invalid file type
40113: unsupported file type
```

**可能原因：**

1. **SVG 文件** - 微信图床不收 SVG，必须先转 PNG（见下）
2. **图片路径错误** - 本地路径相对于 markdown 文件目录解析
3. **图片过大** - 单张限制 10MB
4. **网络图片无法访问**

**SVG 转 PNG：**
```bash
# 任意 SVG 渲染器均可，2x 缩放保证手机端点开清晰
python3 svg2wechat.py 图.svg --svg-only -o out.svg   # 内联进正文（无需转 PNG）
# 或转位图再上传
```

内联 SVG 进正文的完整方案见 SKILL.md「SVG 图片支持情况」章节。

**压缩图片（ImageMagick）：**
```bash
magick large.jpg -quality 80 -resize 1200x compressed.jpg
```

---

## 5. API 凭证错误 / token 失效

**错误信息：**
```
40125: invalid appsecret
40001: invalid credential
```

**解决方法：**

1. `40125`：AppSecret 错误，到后台重置并更新凭证文件
2. `40001`：脚本已内置自动重试（清缓存 + force_refresh），若仍失败：
   ```bash
   rm ~/.config/wechat-publisher/token.json
   ```
   然后重试。

**发布后自检：** 脚本每次发布后自动执行 `draft/count` 前后对比 +
`draft/get` 读回标题校验，静默失败会直接报错退出，不会误报成功。

---

## 6. 上传缓存问题

图片上传结果缓存在 `~/.config/wechat-publisher/upload-cache.json`
（md5 去重，同一张图不重复占素材额度）。如遇素材异常：

```bash
rm ~/.config/wechat-publisher/upload-cache.json
```

---

## 7. 网络连接问题

**测试连通性：**
```bash
curl -I https://api.weixin.qq.com
```

如需代理，Python 层会读取系统环境变量（`HTTPS_PROXY` 等），或：

```bash
export HTTPS_PROXY=http://proxy:port
```

---

## 8. 渲染预览（发布前必看）

先渲染到本地文件，用浏览器确认排版无误再发布：

```bash
python3 scripts/publish_article.py article.md --theme lapis --render-only preview.html
open preview.html
```

---

## 检查清单

- frontmatter 有 title
- 有封面图（cover 字段或正文至少一张图片，SVG 需先转位图）
- 环境变量已设置
- IP 在白名单中

---

**如果问题仍未解决，请提交 Issue：** https://github.com/dqsjqian/wechat-publisher/issues
