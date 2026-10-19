# 06 · SEO 与 Yoast 集成

> 适用：处理 SEO、往 `<head>` 增加输出、调整首页 / 归档 / 搜索页的收录策略时。
> 相关分册：h1 唯一性与模板骨架见 `03-布局与模板骨架.md`；面包屑与相关文章片段见 `05-代码片段库.md`；上线后的 SEO 检查见 `07-性能安全与部署.md`。
> 参考实现：`inc/seo.php`（主题侧补齐）、`functions.php`（`add_theme_support`）。

一句话原则：**Yoast SEO 是唯一的 SEO 主引擎，主题只补齐 Yoast 不输出的东西——绝不重复输出 Yoast 已负责的任何标签。**

---

## 一、职责边界（谁输出什么）

| 输出项 | Yoast SEO | 主题（`inc/seo.php` / 模板） | 落地方式 |
| --- | --- | --- | --- |
| `<title>` | ✅ | ❌ | 主题只声明 `add_theme_support( 'title-tag' )` |
| `meta name="description"` | ✅ | ❌ | 取文章摘要 / 页面 Yoast 元描述 |
| `link rel="canonical"` | ✅ | ⚠️ 只**改值**（静态首页） | 过滤器 `wpseo_canonical`，不新增标签 |
| `meta name="robots"`（含 `noindex`） | ✅ | ❌ | 搜索页与 404 由 Yoast 自动 noindex |
| Open Graph（`og:*`） | ✅ | ⚠️ 只**改值**（静态首页 `og:url`） | 过滤器 `wpseo_opengraph_url` |
| Twitter Card | ✅ | ❌ | — |
| `application/ld+json` | ✅ | ❌ | Yoast 输出 WebSite（含站内搜索 `SearchAction`）/ WebPage / Breadcrumb / 文章 Article 等图，具体以站点配置为准 |
| sitemap | ✅ | ❌ | `/sitemap_index.xml`（Yoast 前台路由） |
| `robots.txt` | ✅ | ❌ | Yoast 输出并追加 `Sitemap:` 行 |
| `meta name="keywords"` | ❌（Yoast 早已不输出） | ✅ | 见 3.1 |
| 图片 alt 回退 | ❌ | ✅ | 见 3.3 |
| 每页唯一 `h1` | ❌ | ✅ | 模板层保证（见 `03-布局与模板骨架.md`） |
| 面包屑 / 相关文章内链 | ❌ | ✅ | 模板层，服务端渲染（见 `05-代码片段库.md`） |
| RSS feed 链接标签 | ❌ | ✅ | `add_theme_support( 'automatic-feed-links' )` |

**结论**：主题的 SEO 职责只有 5 件事——keywords 输出、SEO 关键词字段、图片 alt 回退、静态首页 canonical / og:url 修正、h1 唯一性与内链 / feed。

---

## 二、铁律：不得重复输出

1. 主题里**禁止**再写 `<meta name="description">`、`og:*`、`twitter:*`、`rel="canonical"`、`application/ld+json`——同一页面出现两套声明会互相冲突，搜索引擎择一，往往选错那套。
2. 主题里**禁止**在 `wp_head` 输出 `<title>`（由 `title-tag` + Yoast 负责）。
3. 需要“改” Yoast 的输出时，**只用过滤器改值**（`wpseo_canonical` / `wpseo_opengraph_url`），不要自己 echo 一份新的。
4. 主题不接管 sitemap / robots.txt；换域名后的重新生成走 Yoast 工具，不要手写 `robots.txt` 文件。

---

## 三、主题侧 4 类补齐（完整可复制）

以下代码即 `inc/seo.php` 全文（3.2 / 3.3 / 3.4 的片段追加在同一个文件里）。

### 3.1 `meta keywords` 输出与取值优先级

**落点文件**：`inc/seo.php`。

```php
<?php
/**
 * 主题侧 SEO 补齐
 *
 * 本文件只补齐 Yoast 未覆盖的部分，不重复输出 Yoast 的标签。
 * 本站 SEO 主引擎为 Yoast SEO，它已负责输出 <title>、meta description、rel="canonical"、
 * meta robots、Open Graph、Twitter Card、application/ld+json、
 * sitemap 与 robots.txt 指令；因此这里绝不重复输出上述任何标签，只做四件事：
 *
 * 1. 输出 <meta name="keywords">（Yoast 已不再输出；关键词来源逐级回退，天然每页不同）；
 * 2. 提供「SEO 关键词」自定义字段 meta box（文章 + 页面）；
 * 3. 特色图片 alt 为空时按「附件标题 → 当前文章标题 → 站点名」回填；
 * 4. 修正静态首页的 canonical 与 og:url（首页实体地址为 home_url( '/' )，避免与 /index.php/home/ 形成重复页面）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 「SEO 关键词」自定义字段的 meta key。
 * 也可按「配置集中在 inc/config.php」的约定移到 config.php，同样用 defined() 保护。
 */
define( 'XY_MBX_SEO_KEYWORDS_META', '_xy_mbx_seo_keywords' );

/**
 * 站点名称在关键词、alt 等场景下的兜底值。
 *
 * @return string
 */
function xy_mbx_get_site_name() {
	return (string) get_bloginfo( 'name' );
}

/**
 * 把逗号分隔的字符串切成关键词数组（去空、去首尾空白）。
 *
 * @param mixed $value 待切分的值，非字符串一律视为空。
 * @return string[] 关键词数组，可能为空数组。
 */
function xy_mbx_split_keywords( $value ) {
	if ( ! is_string( $value ) || '' === trim( $value ) ) {
		return array();
	}

	return array_filter( array_map( 'trim', explode( ',', $value ) ), 'strlen' );
}

/**
 * 收集当前页面的 SEO 关键词。
 *
 * 优先级（取到非空即停止，保证每页关键词天然不同）：
 * 1. 当前文章 / 页面的「SEO 关键词」自定义字段；
 * 2. Yoast 焦点关键词（文章、页面用 post meta；分类、标签用 term meta）；
 * 3. 文章详情：所属分类名 + 标签名；
 * 4. 分类 / 标签归档：该术语名 + 父级术语名（若有）；
 * 5. 兜底：站点名。
 *
 * @return string[] 去重去空、最多 10 个词的关键词数组。
 */
function xy_mbx_get_seo_keywords() {
	$queried_id = get_queried_object_id();
	$keywords   = array();

	// 1. 主题自定义字段（文章 / 页面）。
	if ( is_singular() ) {
		$keywords = xy_mbx_split_keywords( get_post_meta( $queried_id, XY_MBX_SEO_KEYWORDS_META, true ) );
	}

	// 2. Yoast 焦点关键词。
	if ( empty( $keywords ) && is_singular() ) {
		$keywords = xy_mbx_split_keywords( get_post_meta( $queried_id, '_yoast_wpseo_focuskw', true ) );
	}
	// 2b. 文章列表页（后台「设置 → 阅读」指定的文章页）：该页面的自定义字段与 Yoast 焦点关键词。
	if ( empty( $keywords ) && is_home() ) {
		$posts_page_id = (int) get_option( 'page_for_posts' );

		if ( $posts_page_id > 0 ) {
			$keywords = xy_mbx_split_keywords( get_post_meta( $posts_page_id, XY_MBX_SEO_KEYWORDS_META, true ) );

			if ( empty( $keywords ) ) {
				$keywords = xy_mbx_split_keywords( get_post_meta( $posts_page_id, '_yoast_wpseo_focuskw', true ) );
			}
		}
	}

	// 2c. 分类 / 标签归档：Yoast 把术语的 SEO 数据存在 option wpseo_taxonomy_meta 里（不是 term meta），
	// 因此后台编辑术语时写入的焦点关键词要经插件 API 读取，否则后台改动不会反映到 keywords。
	if ( empty( $keywords ) && ( is_category() || is_tag() ) ) {
		$keywords = xy_mbx_split_keywords( get_term_meta( $queried_id, '_yoast_wpseo_focuskw', true ) );

		if ( empty( $keywords ) && class_exists( 'WPSEO_Taxonomy_Meta' ) ) {
			$term = get_queried_object();

			if ( $term instanceof WP_Term ) {
				$keywords = xy_mbx_split_keywords( (string) WPSEO_Taxonomy_Meta::get_term_meta( $term, $term->taxonomy, 'focuskw' ) );
			}
		}
	}

	// 3. 文章详情：分类名 + 标签名。
	if ( empty( $keywords ) && is_singular( 'post' ) ) {
		$keywords = array_merge(
			wp_list_pluck( get_the_category(), 'name' ),
			wp_list_pluck( (array) get_the_tags(), 'name' )
		);
	}

	// 4. 分类 / 标签归档：术语名 + 父级术语名。
	if ( empty( $keywords ) && ( is_category() || is_tag() ) ) {
		$term       = get_queried_object();
		$keywords[] = $term->name;

		if ( ! empty( $term->parent ) ) {
			$parent_term = get_term( $term->parent, $term->taxonomy );
			if ( $parent_term && ! is_wp_error( $parent_term ) ) {
				$keywords[] = $parent_term->name;
			}
		}
	}

	// 5. 兜底：站点名。
	if ( empty( $keywords ) ) {
		$keywords[] = xy_mbx_get_site_name();
	}

	return array_slice( array_values( array_unique( $keywords ) ), 0, 10 );
}

/**
 * 输出 <meta name="keywords">。
 *
 * 搜索引擎结果页与 404 页不输出；关键词为空时不输出该标签（Yoast 主引擎的其他标签不受影响）。
 */
function xy_mbx_output_seo_keywords() {
	if ( is_search() || is_404() ) {
		return;
	}

	$keywords = xy_mbx_get_seo_keywords();
	if ( empty( $keywords ) ) {
		return;
	}

	echo '<meta name="keywords" content="' . esc_attr( implode( ',', $keywords ) ) . '">' . "\n";
}
add_action( 'wp_head', 'xy_mbx_output_seo_keywords' );
```

**取值优先级一览**

| 优先级 | 页面类型 | 取值来源 |
| --- | --- | --- |
| 1 | 文章 / 页面 | 自定义字段 `_xy_mbx_seo_keywords`（3.2 的 meta box 写入） |
| 2 | 文章 / 页面 | Yoast 焦点关键词 `_yoast_wpseo_focuskw`（post meta） |
| 2b | 文章列表页（`is_home()`） | `page_for_posts` 指定页面的自定义字段 → Yoast 焦点关键词 |
| 2c | 分类 / 标签归档 | term meta `_yoast_wpseo_focuskw` → `WPSEO_Taxonomy_Meta::get_term_meta( $term, $term->taxonomy, 'focuskw' )` |
| 3 | 文章详情 | 所属分类名 + 标签名（`get_the_category()` / `get_the_tags()`） |
| 4 | 分类 / 标签归档 | 术语名 + 父级术语名 |
| 5 | 其它 | 站点名 `get_bloginfo( 'name' )` |

统一收口：`array_unique()` 去重 → `array_slice( ..., 0, 10 )` 最多 10 个词 → `esc_attr()` 输出。

**注意事项**

- **`meta keywords` 对 Google / Bing 已经无效**（Google 自 2009 年起完全忽略该标签）。它现在只对部分中文搜索引擎残留一点参考价值，因此正确用法是：**只在有值时输出、每页只给 1–3 个精准词**，绝不堆砌。堆砌关键词在 Google 侧是纯风险（可能被视作关键词作弊），收益为零。
- 页面关键词天然随页面不同（分类名 / 标签名 / 术语名），这正是“不堆砌”的实现保障：不要改成在 `wp_head` 里写死一串站点级关键词。
- 术语的 Yoast 焦点关键词**不在 term meta**，而在 option `wpseo_taxonomy_meta`：必须走 `WPSEO_Taxonomy_Meta::get_term_meta()`，直接用 `get_term_meta()` 会读不到（先用 `class_exists()` 兜住，Yoast 未启用时不报错）。
- `is_search()` / `is_404()` 直接不输出，与 Yoast 的 noindex 保持一致。
- 该常量若移入 `inc/config.php`，用 `if ( ! defined( 'XY_MBX_SEO_KEYWORDS_META' ) ) { define( ... ); }` 保护，便于 `wp-config.php` 覆盖。

### 3.2 「SEO 关键词」meta box（含 nonce 与权限校验）

**落点文件**：`inc/seo.php`（追加）。

```php
/**
 * 注册「SEO 关键词」meta box（文章 + 页面，使用默认位置）。
 */
function xy_mbx_register_seo_keywords_meta_box() {
	// 站点启用 Classic Editor，默认位置（advanced）即编辑器下方，满足使用习惯。
	add_meta_box( 'xy-mbx-seo-keywords', 'SEO 关键词', 'xy_mbx_render_seo_keywords_meta_box', array( 'post', 'page' ) );
}
add_action( 'add_meta_boxes', 'xy_mbx_register_seo_keywords_meta_box' );

/**
 * 渲染「SEO 关键词」meta box。
 *
 * @param WP_Post $post 当前编辑的文章 / 页面对象。
 */
function xy_mbx_render_seo_keywords_meta_box( $post ) {
	wp_nonce_field( 'xy_mbx_save_seo_keywords', 'xy_mbx_seo_keywords_nonce' );
	?>
	<p>
		<input
			type="text"
			class="widefat"
			id="<?php echo esc_attr( XY_MBX_SEO_KEYWORDS_META ); ?>"
			name="<?php echo esc_attr( XY_MBX_SEO_KEYWORDS_META ); ?>"
			value="<?php echo esc_attr( (string) get_post_meta( $post->ID, XY_MBX_SEO_KEYWORDS_META, true ) ); ?>"
			placeholder="逗号分隔，例如：虚拟邮箱,临时邮箱"
		>
	</p>
	<?php
}

/**
 * 保存「SEO 关键词」自定义字段。
 *
 * @param int $post_id 被保存的文章 / 页面 ID。
 */
function xy_mbx_save_seo_keywords( $post_id ) {
	// 自动保存、快速编辑等场景没有该字段，直接跳过。
	if ( ! isset( $_POST['xy_mbx_seo_keywords_nonce'] ) ) {
		return;
	}

	// nonce 区分大小写，不能用 sanitize_key（会转小写导致校验失败）。
	$nonce = sanitize_text_field( wp_unslash( $_POST['xy_mbx_seo_keywords_nonce'] ) );
	if ( ! wp_verify_nonce( $nonce, 'xy_mbx_save_seo_keywords' ) ) {
		return;
	}

	if ( ! current_user_can( 'edit_post', $post_id ) ) {
		return;
	}

	$keywords = isset( $_POST[ XY_MBX_SEO_KEYWORDS_META ] )
		? sanitize_text_field( wp_unslash( $_POST[ XY_MBX_SEO_KEYWORDS_META ] ) )
		: '';

	// 清空输入即删除该字段，不留空 meta 行。
	if ( '' === $keywords ) {
		delete_post_meta( $post_id, XY_MBX_SEO_KEYWORDS_META );
		return;
	}

	update_post_meta( $post_id, XY_MBX_SEO_KEYWORDS_META, $keywords );
}
add_action( 'save_post', 'xy_mbx_save_seo_keywords' );
```

**注意事项**

- 三重校验缺一不可：字段存在性（自动保存 / 快速编辑没有该 `$_POST` 键）→ `wp_verify_nonce()` → `current_user_can( 'edit_post', $post_id )`。
- nonce 值**不要**用 `sanitize_key()` 处理：它会把值转小写，导致 `wp_verify_nonce()` 全场校验失败。用 `sanitize_text_field( wp_unslash( ... ) )`。
- 输入永远 `sanitize_text_field` + `wp_unslash`；输出永远 `esc_attr`。
- 存的是「逗号分隔的字符串」（与 3.1 的 `xy_mbx_split_keywords()` 对应），不是数组——不要在保存时 `implode( ',', ... )` 后又 `serialize`。

### 3.3 特色图片 alt 回退

**落点文件**：`inc/seo.php`（追加）。

```php
/**
 * 特色图片 alt 回退：alt 为空时依次用附件标题、当前文章标题、站点名回填。
 *
 * 说明：不覆盖后台已填写的 alt（WordPress 会把 _wp_attachment_image_alt 放进 $attr['alt']）。
 *
 * @param array   $attr       图片属性数组。
 * @param WP_Post $attachment 附件对象。
 * @return array 处理后的属性数组。
 */
function xy_mbx_filter_image_alt_fallback( $attr, $attachment ) {
	if ( ! empty( $attr['alt'] ) ) {
		return $attr;
	}

	$alt = trim( (string) get_the_title( $attachment ) );
	if ( '' === $alt ) {
		$alt = trim( (string) get_the_title() );
	}
	if ( '' === $alt ) {
		$alt = xy_mbx_get_site_name();
	}

	$attr['alt'] = $alt;

	return $attr;
}
add_filter( 'wp_get_attachment_image_attributes', 'xy_mbx_filter_image_alt_fallback', 10, 2 );
```

**注意事项**

- 回调必须声明 `10, 2` 两个参数，否则拿不到 `$attachment`。
- 只对**附件图片**生效（`wp_get_attachment_image()` 系列走过的路径）：`the_post_thumbnail()` 覆盖到了，但编辑器里手写的 `<img>` 与邮件正文里的 `<img>` 不在范围内——那两类 alt 由内容作者 / 上游负责。
- 优雅降级：附件标题 → 当前文章标题 → 站点名，三级都取不到才留空（不会输出 `alt=""` 之外的怪值）。
- 不要用 `get_the_title()` 之外的“当前页标题”来源（`wp_title` 已废弃）。

### 3.4 静态首页 canonical / og:url 修正

**落点文件**：`inc/seo.php`（追加）。

```php
/**
 * 首页 canonical 修正：静态首页实体地址是 home_url( '/' )，而不是页面自身地址 /index.php/home/。
 *
 * @param string $canonical Yoast 生成的 canonical。
 * @return string
 */
function xy_mbx_fix_front_page_canonical( $canonical ) {
	return is_front_page() ? home_url( '/' ) : $canonical;
}
add_filter( 'wpseo_canonical', 'xy_mbx_fix_front_page_canonical' );

/**
 * 首页 og:url 修正：与 canonical 保持一致，避免同一内容出现两个 Open Graph 地址。
 *
 * @param string $url Yoast 生成的 og:url。
 * @return string
 */
function xy_mbx_fix_front_page_opengraph_url( $url ) {
	return is_front_page() ? home_url( '/' ) : $url;
}
add_filter( 'wpseo_opengraph_url', 'xy_mbx_fix_front_page_opengraph_url' );
```

**为什么必须改**：站点用「静态首页 + 固定链接带 `index.php`」时，首页作为页面实体的地址是 `/index.php/home/`，而访客与 sitemap 认的是站点根 `/`，两者内容完全相同 → 产生重复页（duplicate content），权重被摊薄。canonical 与 `og:url` 必须统一指向 `home_url( '/' )`。

**注意事项**

- 用 `is_front_page()` 而不是 `is_home()`：`is_home()` 在「文章页作为首页」时也为真，而这里要改的只是**静态首页**。
- 两个过滤器只**改值**，不新增标签；`og:url` 与 canonical 必须一致，否则分享卡片的落地地址会与规范化地址打架。
- 站点根没有 `index.php` 前缀（固定链接干净）时这两个修正依然正确（`home_url( '/' )` 就是自身），属于幂等操作。

---

## 四、结构化数据与内链（主题侧只做这 4 件）

### 4.1 每页仅一个 `h1`

- `h1` 由**模板层**保证唯一：首页工作台 / 文章列表 / 归档 / 搜索 / 文章详情 / 页面各输出 1 个 `h1`（见 `03-布局与模板骨架.md`）。
- 列表卡片标题用 `h2`；侧栏模块标题用 `h2` 或 `h3`，不要用 `h1`。
- 正文里的 `h1` 由作者在编辑器里插入——约定「正文只用 h2 及以下」，可避免一页出现多个 `h1`。
- 结构化数据里的标题、面包屑由 Yoast 输出，主题**不要**再拼一份 JSON-LD。

### 4.2 面包屑

面包屑同时承担 SEO（层级内链 + Yoast 的 BreadcrumbList 数据）与可用性职责，必须**服务端渲染**在文章标题之上；完整代码见 `05-代码片段库.md` 片段 1。

### 4.3 相关文章内链

相关文章（同分类优先、不足用最新补齐）给蜘蛛提供稳定的站内入口，代码见 `05-代码片段库.md` 片段 10。取数逻辑写在模板片段里即可，不要做成前端异步请求（异步内容蜘蛛抓不到）。

### 4.4 RSS

在 `after_setup_theme` 里加一行即可让 `wp_head` 输出 `<link rel="alternate" type="application/rss+xml" ...>`：

```php
add_theme_support( 'automatic-feed-links' );
```

**注意事项**：feed 地址默认是 `/feed/`；不要手写 `<link>` 标签，交给 `add_theme_support` 输出（避免与核心重复）。

---

## 五、验收与核对方法（可复制）

### 5.1 核对「各只有一份」

先用带随机参数的 URL 绕过 CDN 缓存，再统计各标签出现次数——**每个都必须是 1**：

```powershell
# 在 PowerShell 执行：抓首页 HTML 并统计各标签数量
$url  = "https://你的域名/?nocache=$([guid]::NewGuid().ToString('N'))"
$html = (Invoke-WebRequest -Uri $url -UseBasicParsing).Content

$patterns = [ordered]@{
  'canonical' = 'rel="canonical"'
  'og:url'    = 'property="og:url"'
  'og:title'  = 'property="og:title"'
  'ld+json'   = 'application/ld\+json'
  'keywords'  = 'name="keywords"'
  'description' = 'name="description"'
  'h1'        = '<h1[\s>]'
}

foreach ($k in $patterns.Keys) {
  $n = ([regex]::Matches($html, $patterns[$k])).Count
  "{0,-12} {1}" -f $k, $n
}
```

浏览器侧对照（在目标页面打开控制台）：

```js
// 浏览器控制台：核对 head 里各标签数量与取值
const sels = {
  canonical: 'link[rel="canonical"]',
  ogUrl:     'meta[property="og:url"]',
  title:     'meta[property="og:title"]',
  desc:      'meta[name="description"]',
  robots:    'meta[name="robots"]',
  keywords:  'meta[name="keywords"]',
  jsonLd:    'script[type="application/ld+json"]',
  h1:        'h1',
};
for (const [k, s] of Object.entries(sels)) {
  const els = [...document.querySelectorAll(s)];
  console.log(k, els.length, els.map(e => e.href || e.content || e.textContent.slice(0, 80)));
}
```

### 5.2 搜索页 / 404 必须 noindex

```powershell
# 搜索页与随机 404 页都应含 noindex
$search = (Invoke-WebRequest "https://你的域名/?s=test&nocache=$([guid]::NewGuid().ToString('N'))" -UseBasicParsing).Content
$notFound = (Invoke-WebRequest "https://你的域名/一个不存在的路径-$([guid]::NewGuid().ToString('N'))/" -UseBasicParsing).Content
([regex]::Match($search, '<meta name="robots" content="([^"]*)"')).Groups[1].Value
([regex]::Match($notFound, '<meta name="robots" content="([^"]*)"')).Groups[1].Value
# 期望：两者都含 noindex（搜索页通常为 noindex, follow）
```

### 5.3 归档 index / noindex 策略

| 页面 | 期望 | 在哪里改 |
| --- | --- | --- |
| 分类 / 标签归档 | 默认 **index**（可收录，主题输出 `h1` + 描述 + 分页） | Yoast → 搜索外观 → 分类 / 标签 |
| 文章列表页（`page_for_posts`） | index | Yoast → 内容类型 → 文章页 |
| 搜索页 | noindex（Yoast 自动） | Yoast → 搜索外观 → 搜索页 |
| 404 | noindex（Yoast 自动） | 不可改 |
| 作者归档 / 日期归档 | 按需；单作者站点建议 noindex（内容重复） | Yoast → 搜索外观 → 归档 |

> 主题侧的 `meta keywords` 输出已与 noindex 策略解耦：搜索页与 404 不输出，其余页正常输出。

### 5.4 sitemap 与 robots.txt 必须是 https 且域名正确

```powershell
(Invoke-WebRequest "https://你的域名/robots.txt" -UseBasicParsing).Content
# 期望包含：Sitemap: https://你的域名/sitemap_index.xml（且不是 http、不是旧域名）

(Invoke-WebRequest "https://你的域名/sitemap_index.xml" -UseBasicParsing).Content
# 期望 <loc> 全部是 https://你的域名/...
```

**换域名 / 换协议后必做**：Yoast → 工具 → 重新索引；随后核对 sitemap 与 robots 中的域名（见第六节）。**若站点在 CDN 之后，robots.txt 常被 CDN 缓存，改完必须清一次 CDN 缓存**，否则搜索引擎抓到的还是旧文件。

---

## 六、常见错误清单

| 错误 | 后果 | 正确做法 |
| --- | --- | --- |
| 主题里又输出了一份 `canonical` / `og:*` / JSON-LD | 同页两套声明冲突，搜索引擎择一（常选错） | 只用 `wpseo_canonical` / `wpseo_opengraph_url` 过滤器改值 |
| `meta keywords` 塞满一长串同义词 | 对 Google / Bing 完全无效，还有作弊风险 | 只在有值时输出，每页 1–3 个精准词（本主题的取值优先级天然做到这点） |
| 忘记图片 alt 回退 | 所有特色图 `alt=""`，图片搜索无流量、无障碍不合格 | 挂 `wp_get_attachment_image_attributes` 做三级回退 |
| 静态首页 canonical 指向 `/index.php/home/` | 与站点根形成重复页，权重被摊薄 | `is_front_page()` 时统一返回 `home_url( '/' )`，`og:url` 同步 |
| CDN 场景下 robots.txt 里仍是 `http://` | 搜索引擎按 http 抓取，全站 301 或抓取失败 | 站点地址改成 https → Yoast 重新索引 → **清 CDN 缓存** |
| 换域名后忘记重新索引 | sitemap / canonical 仍是旧域名 | Yoast → 工具 → 重新索引；核对 `robots.txt` |
| 归档页忘了 `h1`，或列表卡片用 `h1` | 一页多个 `h1`，层级结构混乱 | 模板层保证每页唯一 `h1`，卡片标题用 `h2` |
| 相关文章 / 面包屑改成前端异步加载 | 蜘蛛抓不到内链，SEO 价值归零 | 服务端渲染进 HTML |
| 术语焦点关键词用 `get_term_meta()` 读 | 永远读不到（数据在 option `wpseo_taxonomy_meta`） | 走 `WPSEO_Taxonomy_Meta::get_term_meta()`，`class_exists()` 兜底 |
| 关掉 `automatic-feed-links` 或手写 feed `<link>` | 与核心输出重复或缺失 | 只保留 `add_theme_support( 'automatic-feed-links' )` |

---

## 七、换用其它 SEO 插件（Rank Math 等）的迁移提示

映射关系：

| 关注点 | Yoast SEO（参考实现） | Rank Math 等其它插件 |
| --- | --- | --- |
| 职责边界 | 插件负责 title / description / canonical / robots / OG / JSON-LD / sitemap / robots.txt | **完全一致**：插件全包，主题只补 keywords、alt、h1、内链、feed |
| canonical 改值过滤器 | `wpseo_canonical` | 钩子名不同 |
| `og:url` 改值过滤器 | `wpseo_opengraph_url` | 钩子名不同 |
| 焦点关键词 meta key | `_yoast_wpseo_focuskw` | meta key 不同 |
| 术语 SEO 数据位置 | option `wpseo_taxonomy_meta`，经 `WPSEO_Taxonomy_Meta::get_term_meta()` 读 | 多为 term meta，可直接 `get_term_meta()` |

迁移动作（顺序不能反）：

1. **先查插件文档确认钩子名与 meta key**，不要照抄 `wpseo_*` 前缀——钩子名写错不会报错，只是静默失效。
2. 若插件**自己输出 `meta keywords`**（少数插件仍默认开启），把主题的 `xy_mbx_output_seo_keywords()` 去掉，避免重复输出；插件不输出时主题才保留。
3. 保留 3.2 / 3.3 的 meta box 与 alt 回退（与插件无关），只需把 3.1 中读取焦点关键词的 meta key 换成新插件的。
4. 迁移后重跑第五节全部验收项（各标签一份、搜索页 noindex、sitemap / robots 域名正确）。

> 原则不变：**同一类标签只有一个来源**。换插件时先问「这个标签现在归谁」，确认没有第二个输出者，再动代码。
