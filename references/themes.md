# 排版主题列表

内置 12 个排版主题 + 9 个代码高亮主题，全部内置于 `scripts/themes/`，无需联网安装。

## 排版主题（scripts/themes/*.css）

**常用主题：**

1. **default** - 默认主题
   - 简洁、通用
   - 适合大部分文章

2. **lapis** - 青金石（推荐）
   - 优雅的蓝色调
   - 适合技术文章

3. **phycat** - 薄荷绿
   - 清新、层级分明
   - 适合科技类内容

4. **orangeheart** - 橙心
   - 暖色调
   - 适合随笔、产品介绍

**全部主题：**

| 主题 | 风格 |
|------|------|
| default | 经典简约 |
| juejin_default | 掘金风 |
| lapis | 蓝色优雅（推荐） |
| maize | 玉米黄 |
| medium_default | Medium 风 |
| orangeheart | 橙心 |
| phycat | 薄荷绿 |
| pie | 派阅风 |
| purple | 紫色简约 |
| rainbow | 彩虹活力 |
| toutiao_default | 头条风 |
| zhihu_default | 知乎风 |

## 代码高亮主题（scripts/highlight-themes/*.css）

### 亮色主题
- `atom-one-light` - Atom 编辑器亮色
- `github` - GitHub 风格
- `solarized-light` - Solarized 亮色（默认）
- `xcode` - Xcode 默认

### 暗色主题
- `atom-one-dark` - Atom 编辑器暗色
- `dracula` - Dracula 主题
- `github-dark` - GitHub 暗色
- `monokai` - Monokai 经典
- `solarized-dark` - Solarized 暗色

## 使用方式

```bash
# 指定排版主题 + 高亮主题
./scripts/publish.sh article.md lapis solarized-light

# 直接调 Python 入口
python3 scripts/publish_article.py article.md --theme lapis --highlight github
```

## 自定义主题

主题就是一个普通 CSS 文件，选择器以 `#article` 为容器前缀（对应输出 HTML
的 `<section id="article">`）。放进 `scripts/themes/` 即可按文件名使用：

```bash
cp my-theme.css scripts/themes/my-theme.css
python3 scripts/publish_article.py article.md --theme my-theme
```

**主题定制要点：**

1. 参考现有主题的结构（如 `lapis.css`）
2. 支持 CSS 变量（`:root { --primary-color: ... }`），渲染时自动解析替换
3. `h1-h6 / blockquote / pre` 支持 `::before / ::after` 伪元素（自动展开为真实元素）
4. 伪类选择器（`:nth-child` 等）不支持，会被跳过
5. 用 `--render-only` 先本地预览再发布：

```bash
python3 scripts/publish_article.py article.md --theme my-theme --render-only preview.html
```

## 推荐组合

### 技术文章（默认推荐）
```bash
./scripts/publish.sh article.md lapis solarized-light
```

### 深色代码风格
```bash
./scripts/publish.sh article.md phycat dracula
```

### 简洁风格
```bash
./scripts/publish.sh article.md default github
```

## 更多选项

### 关闭 Mac 风格代码块圆点
```bash
python3 scripts/publish_article.py article.md --no-mac-style
```

### 关闭链接转脚注
```bash
python3 scripts/publish_article.py article.md --no-footnote
```

### 组合所有选项
```bash
python3 scripts/publish_article.py article.md \
  --theme lapis \
  --highlight solarized-light \
  --no-mac-style \
  --no-footnote
```
