---
name: "wp-theme-authoring"
description: "编写、改造或重构 WordPress 主题时使用（经典 PHP 主题，非 FSE/区块主题）：创建主题骨架与目录结构、编写模板（首页/文章列表/文章详情/页面/归档/搜索/404）、添加评论/分页/面包屑/搜索/侧栏与相关文章/SEO 补齐、用 Tailwind 4 + daisyUI 5 预编译样式、打包与上线。当任务涉及 wp-content/themes 下的主题代码、functions.php、模板层级，或用户提出「给 WordPress 做个主题 / 加个主题模块 / 改主题模板样式」时触发。"
---

# WordPress 主题编写规范（经典 PHP 主题 + Tailwind 4 + daisyUI 5）

一句话定位：把「**经典 PHP 主题 + Tailwind CSS 4 + daisyUI 5 预编译**」这套写法锁死为唯一实现路径，照抄即可，不引入其它范式。

本技能自带 `references/`（规范主体）与 `templates/`（可直接复制的骨架）。整体自包含，复制到任意新项目后无需参照原始主题仓库。

---

## 一、技术栈锁定声明（不得擅自更换）

| 项 | 锁定值 | 说明 |
| --- | --- | --- |
| 主题类型 | **经典 PHP 主题** | 不使用 FSE / 区块主题，不写 `theme.json`、不用 `templates/*.html` |
| WordPress | ≥ 6.5（实测 7.1） | 使用 REST API、`WP_Term`、`wp_get_attachment_image_attributes` 等 |
| PHP | ≥ 7.4（实测 8.2） | 主题不使用 PHP 8 专有语法；`mbstring` 为**必需**扩展 |
| 样式 | Tailwind CSS 4（4.3.3）+ daisyUI 5（5.7.38） | 只写工具类与组件类，工具类不足以表达的才写自定义 CSS |
| 构建 | Node **仅构建期**需要（实测 node 20 / npm 10） | `npm run build:css` 产出静态 `assets/css/tailwind.css` |
| 运行期 | 前台**不依赖 Node、不依赖 WindPress** | 不下载编译器到浏览器、不依赖 esm.sh、无首屏样式闪烁 |

---

## 二、项目结构速查

```
your-theme/
├── style.css                    仅主题头（Theme Name / Version 等），真实样式在 assets/css/
├── functions.php                主题入口：常量 + 加载 inc + 资源入队 + add_theme_support
├── header.php / footer.php      页头（含 <main> 开标签）/ 页脚（闭合 <main>）
├── front-page.php               首页
├── home.php / archive.php / search.php / index.php
│                                文章列表 / 归档 / 搜索 / 兜底（共用 template-parts/post-list.php）
├── single.php                   文章详情（面包屑 + 正文 + 标签 + 上下篇 + 侧栏 + 评论）
├── page.php / 404.php / searchform.php / comments.php
├── inc/
│   ├── config.php               集中配置层（所有常量 + defined() 保护）
│   ├── class-mailcx-client.php  上游 API 业务客户端
│   ├── friend-links.php         数据层（服务端取数 + 缓存 + 失败兜底）
│   ├── rest-api.php             REST 转发（参数校验 + 限流 + 白名单过滤）
│   ├── seo.php                  SEO 补齐（keywords / alt / canonical）
│   └── comments.php             评论区渲染与表单（回调、头像、评论数、表单字段）
├── template-parts/
│   ├── post-list.php            列表片段（网格卡片 + 分页 + 空态）
│   └── related-posts.php        侧栏模块示例（相关文章）
├── assets/
│   ├── css/tailwind.css         ★ 预编译产物（随主题分发，不手改）
│   ├── css/theme.css            少量自定义样式（正文字号 / iframe / 分页外观）
│   ├── css/src/main.css         Tailwind 构建入口（改样式时才需要）
│   ├── js/mailbox.js            前端脚本
│   └── img/                     品牌图标 / favicon
├── package.json                 样式构建脚本（仅开发期需要 Node）
├── screenshot.png               后台主题缩略图（1200×900）
└── 部署文档.md                  部署与排错说明
```

---

## 三、文章详情页布局速查（最容易写错的地方）

```
<div class="container mx-auto max-w-6xl px-4 py-8">                          页面容器
  <div class="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-8">   两栏容器
    <div class="min-w-0 lg:col-start-1 lg:row-start-1">                      左栏第 1 行：正文 + 上下篇导航
    <aside class="lg:col-start-2 lg:row-span-2 lg:row-start-1" aria-label="侧栏">          右栏：跨两行
      <div class="space-y-4 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
        <?php get_template_part( 'template-parts/related-posts' ); ?>        新模块直接往里追加
    <div class="lg:col-start-1 lg:row-start-2">                              左栏第 2 行：评论区
```

- 断点 `lg` = 1024px；`lg` 以下退化为单栏，顺序由 DOM 决定：**正文 → 侧栏 → 评论区**。
- `aside` 必须 `lg:row-span-2`，内层必须再包一层 sticky 容器；两处原因见 `references/03-布局与模板骨架.md`。

---

## 四、references 索引

| 分册 | 写什么 | 什么时候读 |
| --- | --- | --- |
| `01-技术栈与项目结构.md` | 环境要求、目录树与文件职责、`inc/` 分层、命名约定、`add_theme_support` 清单 | 建新主题、决定「新功能放哪个文件」时 |
| `02-样式与构建.md` | Tailwind 4 + daisyUI 5 预编译、`@source` 扫描范围、构建/监听命令、产物自检与排错 | 任何一次改动类名、样式不生效、样式迁移时 |
| `03-布局与模板骨架.md` | h1 唯一性、容器宽度、两栏 + sticky 侧栏、面包屑、列表/归档/搜索/404 骨架、浏览器验收脚本 | 写任何模板文件、调整布局时 |
| `04-能力模块清单.md` | 评论/分页/面包屑/搜索/侧栏/特色图/图集/视频/音频/目录/评分等模块清单与落点、按项目类型的推荐组合 | 新项目选型、确定「本项目要做哪些功能」时 |
| `05-代码片段库.md` | 可直接复制的片段：面包屑、评论回调与表单、评论数徽标、分页、渐变描边侧栏卡片、相关文章取数等 | 需要具体实现代码时 |
| `06-SEO与Yoast集成.md` | 与 Yoast 的职责边界、keywords / alt / feed / canonical 片段、验收与常见错误 | 处理 SEO、加 head 输出时 |
| `07-性能安全与部署.md` | 密钥管理、REST 转发与限流、HTML 白名单 + sandbox、filemtime 版本号、打包与上线检查 | 涉及接口、安全、打包上线时 |
| `08-AI执行清单.md` | 动手前 / 实现中 / 完成前 三段可勾选清单 + 禁止事项 + 自检命令 | **每次任务开始与交付前**必读 |
| `09-开工提示词模板.md` | 给新项目一次性交代需求的可复制提示词模板（项目/环境/页面/内容类型/能力模块/SEO/交付要求） | **新项目开工第一步** |

## 五、templates 索引

| 骨架（`templates/` 下） | 落地到新主题的位置 | 用途 |
| --- | --- | --- |
| `package.json` | 主题根 | 样式构建脚本（`build:css` / `watch:css`） |
| `main.css` | `assets/css/src/main.css` | Tailwind 构建入口（`@import` + `@plugin` + `@source` 扫描范围） |
| `functions.php` | 主题根 | 主题入口骨架：常量、加载 `inc/`、资源入队、`add_theme_support`（含 `register_nav_menus()`） |
| `header.php` | 主题根 | 页头（`<head>` / 品牌 / 导航 / 打开 `<main>`） |
| `footer.php` | 主题根 | 页脚（品牌 / 友情链接栏（有数据才输出）/ 版权 / 闭合 `<main>`） |
| `config.php` | `inc/config.php` | 集中配置骨架（常量 + `defined()` 保护） |
| `single.php` | 主题根 | 文章详情：两栏 + sticky 侧栏 + 面包屑 + 上下篇 + 评论 |
| `index.php` | 主题根 | 兜底列表页 |
| `archive.php` | 主题根 | 归档页（分类/标签/日期/作者） |
| `search.php` | 主题根 | 搜索结果页 |
| `404.php` | 主题根 | 404 页（搜索 + 最近文章 + 返回首页） |
| `page.php` | 主题根 | 单页 |
| `comments.php` | 主题根 | 评论区：列表回调 + 分页 + 空态 + 表单 |
| `inc/comments.php` | `inc/comments.php` | 评论渲染回调、占位头像、评论数徽标、评论表单样式（`comments.php` / `single.php` / `post-list.php` 依赖它，必须一并复制） |
| `inc/seo.php` | `inc/seo.php` | SEO 补齐（keywords / 关键词字段 / 图片 alt / 静态首页 canonical 与 og:url） |
| `post-list.php` | `template-parts/post-list.php` | 列表片段：网格卡片 + 分页 + 空态 |
| `assets/css/theme.css` | `assets/css/theme.css` | 少量自定义样式（正文排版 / 嵌入内容 / 分页外观） |
| `部署文档模板.md` | 主题根（`部署文档.md`） | 部署说明模板（环境、配置、排错、上线清单） |
| `打包命令.md` | 主题根 | 打包命令与排除项（`node_modules`、工作物料） |

> 模板文件（`header.php` / `footer.php` / `index.php` / `archive.php` / `search.php` / `404.php` / `page.php`）与 `inc/seo.php`、`assets/css/theme.css` 均已提供骨架，按上表「落地位置」复制；布局与 h1 落点约定见 `references/03-布局与模板骨架.md`。

> `templates/` 内的文件若带目录层级存放（如 `templates/assets/css/src/main.css`、`templates/inc/config.php`），按上表「落地位置」直接复制即可。

---

## 六、复制到新项目后的落地步骤

1. 把整个 `wp-theme-authoring/` 目录复制到新项目的 `.trae/skills/` 下。
2. 在新主题目录按 `templates/` 放置 `package.json` 与 `assets/css/src/main.css`，执行 `npm install` + `npm run build:css`，确认生成 `assets/css/tailwind.css`。
3. 按 `04-能力模块清单.md` 勾选本项目需要的能力模块（评论 / 分页 / 面包屑 / 搜索 / 侧栏 / 特色图 / 图集 / 视频 / 音频 / 目录等），只实现被勾选项。
4. 按 `08-AI执行清单.md` 逐条执行「动手前 → 实现中 → 完成前」清单，交付前完成构建与浏览器几何验收。

---

## 七、AI 执行清单摘要

1. **动手前**：确认是经典主题（非 FSE）；列出本项目要落地的文件清单与要勾选的能力模块；不确定就提问，不擅自扩大范围。
2. **改类名 = 必须重新构建**：任何新增/修改的 Tailwind / daisyUI 类名都要在该主题目录执行 `npm run build:css`，否则样式不生效。
3. **布局照抄 03 分册**：文章详情页的两栏 + sticky 侧栏类名一个字都不要改；每页只允许一个 `h1`。
4. **禁区**：不重复输出 Yoast 已负责的 SEO 标签；不把密钥/`app_secret` 下发前端；非必要不写自定义 CSS；不改动与本任务无关的既有代码。
5. **交付前**：`php -l` 语法检查 + 重新构建 + 在浏览器里读计算样式与几何值验收（两栏成立 / sticky 生效 / 窄屏顺序 / 无横向溢出）。

> 完整清单与禁止事项见 `references/08-AI执行清单.md`。
