# WordPress 主题编写规范（wp-theme-authoring）

> **定位**：一套可直接交给 AI 或开发者执行的 WordPress **经典 PHP 主题**编写规范 + 骨架模板。
> **形态**：技能包（`SKILL.md` + `references/` 九册规范 + `templates/` 可复制骨架）
> **适用范围**：`wp-content/themes` 下的主题代码、`functions.php`、模板层级、主题样式改造与上线打包。

## 0. 一句话说明

把「**经典 PHP 主题 + Tailwind CSS 4 + daisyUI 5 预编译**」锁死为唯一实现路径：新建主题、加页面、改布局、补 SEO、打包上线，都照这里的规范与骨架抄，不引入其它范式。

**明确不做**：FSE / 区块主题、`theme.json`、`templates/*.html`。

## 1. 技术栈锁定

| 项 | 锁定值 |
| --- | --- |
| 主题类型 | 经典 PHP 主题（非 FSE / 非区块主题） |
| WordPress | ≥ 6.5 |
| PHP | ≥ 7.4，`mbstring` 必需 |
| 样式 | Tailwind CSS 4（4.3.3）+ daisyUI 5（5.7.38） |
| 构建 | Node 仅构建期需要（`npm run build:css`） |
| 运行期 | 前台不依赖 Node、不依赖 WindPress，无首屏样式闪烁 |

## 2. 文件清单

```
wp-theme-authoring/
├── SKILL.md                    技能入口：定位、技术栈、结构速查、索引
├── references/                 规范主体（按需查阅）
│   ├── 01-技术栈与项目结构.md
│   ├── 02-样式与构建.md
│   ├── 03-布局与模板骨架.md
│   ├── 04-能力模块清单.md
│   ├── 05-代码片段库.md
│   ├── 06-SEO与Yoast集成.md
│   ├── 07-性能安全与部署.md
│   ├── 08-AI执行清单.md
│   └── 09-开工提示词模板.md
└── templates/                  可直接复制到新主题的骨架
    ├── functions.php / header.php / footer.php
    ├── index.php / archive.php / search.php / single.php / page.php / 404.php
    ├── comments.php
    ├── inc/（config.php / comments.php / seo.php）
    ├── template-parts/post-list.php
    ├── assets/css/（theme.css / src/main.css）
    ├── package.json
    ├── 打包命令.md
    └── 部署文档模板.md
```

## 3. 怎么用

1. **先读 `SKILL.md`**：确认技术栈、目录结构与 references / templates 索引。
2. **新项目开工**：用 `references/09-开工提示词模板.md` 一次性交代需求（项目、环境、页面、内容类型、能力模块、SEO、交付要求）。
3. **动手前 / 交付前**：过一遍 `references/08-AI执行清单.md` 的三段清单与禁止事项。
4. **搭骨架**：按 `SKILL.md` 第五节的「落地位置」表，把 `templates/` 里的文件复制到新主题对应路径。
5. **改样式**：只改 `assets/css/src/main.css`，然后 `npm run build:css` 产出 `assets/css/tailwind.css`；不要手改编译产物。
6. **打包上线**：按 `templates/打包命令.md` 排除 `node_modules` 与工作物料，按 `templates/部署文档模板.md` 写部署说明。

## 4. 最容易写错的地方

- 文章详情页是「左栏正文 + 右栏 sticky 侧栏（`lg:row-span-2`）+ 左栏评论区」，`lg` 以下按 DOM 顺序退化为单栏。
- 每页只允许一个 `h1`，标题层级与容器宽度见 `references/03-布局与模板骨架.md`。
- `comments.php` / `single.php` / `post-list.php` 依赖 `inc/comments.php`，必须一并复制。
- `inc/seo.php` 与 Yoast 的职责边界见 `references/06-SEO与Yoast集成.md`，不要重复输出。

## 5. 说明

本目录是技能包的展示 / 下载副本，原件位于开发仓库的 `wordpress插件/wp-theme-authoring`。原件更新后，重新覆盖本目录即可。
