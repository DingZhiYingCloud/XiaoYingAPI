<?php
/**
 * 主题侧 SEO 补齐（可复制骨架）
 *
 * 职责：只补齐 Yoast 未覆盖的 4 件事，其余 SEO 标签一律交给插件输出。
 *   1. 输出 <meta name="keywords">（Yoast 早已不再输出；关键词逐级回退，天然每页不同）；
 *   2. 提供「SEO 关键词」自定义字段 meta box（文章 + 页面），供人工覆写关键词；
 *   3. 特色图片 alt 为空时按「附件标题 → 当前文章标题 → 站点名」三级回退回填；
 *   4. 修正静态首页的 canonical 与 og:url，统一指向站点根，避免重复页面。
 *
 * 来源：改写自参考实现的 inc/seo.php（逻辑与回退链不变，仅把前缀统一为 mytheme_ / MYTHEME_）。
 * 落地位置：新主题根目录 inc/seo.php，并在 functions.php 的 require_once 列表里启用本文件
 *          （文件不存在时不要 require，否则直接致命报错）。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme / MYTHEME_ 替换为你的主题短名（例：acme → acme_ / ACME_），函数名、常量名、
 *          nonce 名与 meta box id 一并改并保持统一。
 * TODO 2. 本文件不依赖其它 inc 文件，可单独启用；常量就近定义在文件头（用 defined() 保护，可在 wp-config.php 覆盖）。
 *
 * 纪律（铁律）：Yoast SEO 是唯一的 SEO 主引擎，已负责 <title>、meta description、rel="canonical"、
 * meta robots、Open Graph、Twitter Card、application/ld+json、sitemap 与 robots.txt；
 * 本文件绝不重复输出上述任何标签，需要改值只用过滤器。分工详见 references/06-SEO与Yoast集成.md。
 *
 * 依赖：WordPress 自带函数 +（可选）Yoast SEO；Yoast 未启用时相关分支静默降级，不报错。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 「SEO 关键词」自定义字段的 meta key。
 * 用 defined() 保护，便于在 wp-config.php 里提前定义覆盖。
 */
if ( ! defined( 'MYTHEME_SEO_KEYWORDS_META' ) ) {
	define( 'MYTHEME_SEO_KEYWORDS_META', '_mytheme_seo_keywords' );
}

/**
 * 站点名称在关键词、alt 等场景下的兜底值。
 *
 * @return string
 */
function mytheme_get_site_name() {
	return (string) get_bloginfo( 'name' );
}

/**
 * 把逗号分隔的字符串切成关键词数组（去空、去首尾空白）。
 * 为什么需要：meta box 与 Yoast 焦点关键词存的都是「逗号分隔字符串」，统一在这里切分。
 *
 * @param mixed $value 待切分的值，非字符串一律视为空。
 * @return string[] 关键词数组，可能为空数组。
 */
function mytheme_split_keywords( $value ) {
	if ( ! is_string( $value ) || '' === trim( $value ) ) {
		return array();
	}

	return array_filter( array_map( 'trim', explode( ',', $value ) ), 'strlen' );
}

/**
 * 收集当前页面的 SEO 关键词。
 *
 * 为什么需要：Yoast 不再输出 meta keywords，而「每页给 1–3 个精准词」既要有内容依据、
 * 又要天然逐页不同，所以在主题侧按页面类型逐级回退（取到非空即停止）：
 * 1. 当前文章 / 页面的「SEO 关键词」自定义字段；
 * 2. Yoast 焦点关键词（文章、页面读 post meta；分类、标签见 2c）；
 * 2b. 文章列表页（后台「设置 → 阅读」指定的文章页）：该页面的自定义字段 → Yoast 焦点关键词；
 * 2c. 分类 / 标签归档：term meta → Yoast 的 wpseo_taxonomy_meta（经插件 API 读）；
 * 3. 文章详情：所属分类名 + 标签名；
 * 4. 分类 / 标签归档：该术语名 + 父级术语名（若有）；
 * 5. 兜底：站点名。
 *
 * @return string[] 去重去空、最多 10 个词的关键词数组。
 */
function mytheme_get_seo_keywords() {
	$queried_id = get_queried_object_id();
	$keywords   = array();

	// 1. 主题自定义字段（文章 / 页面）。
	if ( is_singular() ) {
		$keywords = mytheme_split_keywords( get_post_meta( $queried_id, MYTHEME_SEO_KEYWORDS_META, true ) );
	}

	// 2. Yoast 焦点关键词（文章 / 页面的 post meta）。
	if ( empty( $keywords ) && is_singular() ) {
		$keywords = mytheme_split_keywords( get_post_meta( $queried_id, '_yoast_wpseo_focuskw', true ) );
	}

	// 2b. 文章列表页（后台「设置 → 阅读」指定的文章页）：该页面的自定义字段与 Yoast 焦点关键词。
	if ( empty( $keywords ) && is_home() ) {
		$posts_page_id = (int) get_option( 'page_for_posts' );

		if ( $posts_page_id > 0 ) {
			$keywords = mytheme_split_keywords( get_post_meta( $posts_page_id, MYTHEME_SEO_KEYWORDS_META, true ) );

			if ( empty( $keywords ) ) {
				$keywords = mytheme_split_keywords( get_post_meta( $posts_page_id, '_yoast_wpseo_focuskw', true ) );
			}
		}
	}

	// 2c. 分类 / 标签归档：Yoast 把术语的 SEO 数据存在 option wpseo_taxonomy_meta 里（不是 term meta），
	// 因此后台编辑术语时写入的焦点关键词要经插件 API 读取，否则后台改动不会反映到 keywords；
	// 用 class_exists() 兜底，未装 Yoast 时不报错。
	if ( empty( $keywords ) && ( is_category() || is_tag() ) ) {
		$keywords = mytheme_split_keywords( get_term_meta( $queried_id, '_yoast_wpseo_focuskw', true ) );

		if ( empty( $keywords ) && class_exists( 'WPSEO_Taxonomy_Meta' ) ) {
			$term = get_queried_object();

			if ( $term instanceof WP_Term ) {
				$keywords = mytheme_split_keywords( (string) WPSEO_Taxonomy_Meta::get_term_meta( $term, $term->taxonomy, 'focuskw' ) );
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
		$keywords[] = mytheme_get_site_name();
	}

	return array_slice( array_values( array_unique( $keywords ) ), 0, 10 );
}

/**
 * 输出 <meta name="keywords">。
 *
 * 为什么需要且为什么只在这里输出：Yoast 不输出该标签，主题补齐即可；
 * 但搜索结果页与 404 页由 Yoast 置为 noindex，这里同步不输出；
 * 关键词为空时也不输出，避免出现空的 keywords 标签。
 */
function mytheme_output_seo_keywords() {
	if ( is_search() || is_404() ) {
		return;
	}

	$keywords = mytheme_get_seo_keywords();
	if ( empty( $keywords ) ) {
		return;
	}

	echo '<meta name="keywords" content="' . esc_attr( implode( ',', $keywords ) ) . '">' . "\n";
}
add_action( 'wp_head', 'mytheme_output_seo_keywords' );

/**
 * 注册「SEO 关键词」meta box（文章 + 页面，使用默认位置）。
 *
 * 为什么需要：逐级回退只能拿到分类名 / 标签名这类通用词，运营想指定精准词时需要一个入口。
 */
function mytheme_register_seo_keywords_meta_box() {
	// 站点启用 Classic Editor，默认位置（advanced）即编辑器下方，满足使用习惯。
	add_meta_box( 'mytheme-seo-keywords', 'SEO 关键词', 'mytheme_render_seo_keywords_meta_box', array( 'post', 'page' ) );
}
add_action( 'add_meta_boxes', 'mytheme_register_seo_keywords_meta_box' );

/**
 * 渲染「SEO 关键词」meta box。
 *
 * @param WP_Post $post 当前编辑的文章 / 页面对象。
 */
function mytheme_render_seo_keywords_meta_box( $post ) {
	wp_nonce_field( 'mytheme_save_seo_keywords', 'mytheme_seo_keywords_nonce' );
	?>
	<p>
		<input
			type="text"
			class="widefat"
			id="<?php echo esc_attr( MYTHEME_SEO_KEYWORDS_META ); ?>"
			name="<?php echo esc_attr( MYTHEME_SEO_KEYWORDS_META ); ?>"
			value="<?php echo esc_attr( (string) get_post_meta( $post->ID, MYTHEME_SEO_KEYWORDS_META, true ) ); ?>"
			placeholder="逗号分隔，例如：虚拟邮箱,临时邮箱"
		>
	</p>
	<?php
}

/**
 * 保存「SEO 关键词」自定义字段。
 *
 * 为什么需要三重校验：字段存在性挡住自动保存 / 快速编辑（这些场景没有该 $_POST 键），
 * nonce 挡住伪造提交，current_user_can() 挡住越权改他人文章。
 *
 * @param int $post_id 被保存的文章 / 页面 ID。
 */
function mytheme_save_seo_keywords( $post_id ) {
	// 自动保存、快速编辑等场景没有该字段，直接跳过。
	if ( ! isset( $_POST['mytheme_seo_keywords_nonce'] ) ) {
		return;
	}

	// nonce 区分大小写，不能用 sanitize_key（会转小写导致校验失败）。
	$nonce = sanitize_text_field( wp_unslash( $_POST['mytheme_seo_keywords_nonce'] ) );
	if ( ! wp_verify_nonce( $nonce, 'mytheme_save_seo_keywords' ) ) {
		return;
	}

	if ( ! current_user_can( 'edit_post', $post_id ) ) {
		return;
	}

	$keywords = isset( $_POST[ MYTHEME_SEO_KEYWORDS_META ] )
		? sanitize_text_field( wp_unslash( $_POST[ MYTHEME_SEO_KEYWORDS_META ] ) )
		: '';

	// 清空输入即删除该字段，不留空 meta 行（否则回退链会读到空字符串）。
	if ( '' === $keywords ) {
		delete_post_meta( $post_id, MYTHEME_SEO_KEYWORDS_META );
		return;
	}

	update_post_meta( $post_id, MYTHEME_SEO_KEYWORDS_META, $keywords );
}
add_action( 'save_post', 'mytheme_save_seo_keywords' );

/**
 * 特色图片 alt 回退：alt 为空时依次用附件标题、当前文章标题、站点名回填。
 *
 * 为什么需要：alt 为空既伤图片搜索流量，也不符合无障碍要求；而附件标题常被忽略，故做三级回退。
 * 说明：不覆盖后台已填写的 alt（WordPress 会把 _wp_attachment_image_alt 放进 $attr['alt']）。
 * 注意：回调必须声明两个参数（10, 2），否则拿不到 $attachment。
 *
 * @param array   $attr       图片属性数组。
 * @param WP_Post $attachment 附件对象。
 * @return array 处理后的属性数组。
 */
function mytheme_filter_image_alt_fallback( $attr, $attachment ) {
	if ( ! empty( $attr['alt'] ) ) {
		return $attr;
	}

	$alt = trim( (string) get_the_title( $attachment ) );
	if ( '' === $alt ) {
		$alt = trim( (string) get_the_title() );
	}
	if ( '' === $alt ) {
		$alt = mytheme_get_site_name();
	}

	$attr['alt'] = $alt;

	return $attr;
}
add_filter( 'wp_get_attachment_image_attributes', 'mytheme_filter_image_alt_fallback', 10, 2 );

/**
 * 首页 canonical 修正：静态首页实体地址是 home_url( '/' )，而不是页面自身地址 /index.php/home/。
 *
 * 为什么必须改：站点用「静态首页 + 固定链接带 index.php」时，首页作为页面实体的地址是
 * /index.php/home/，而访客与 sitemap 认的是站点根 /，两者内容完全相同 → 产生重复页
 * （duplicate content），权重被摊薄。用 is_front_page()（而不是 is_home()）只修正静态首页。
 *
 * @param string $canonical Yoast 生成的 canonical。
 * @return string
 */
function mytheme_fix_front_page_canonical( $canonical ) {
	return is_front_page() ? home_url( '/' ) : $canonical;
}
add_filter( 'wpseo_canonical', 'mytheme_fix_front_page_canonical' );

/**
 * 首页 og:url 修正：与 canonical 保持一致，避免同一内容出现两个 Open Graph 地址。
 *
 * 为什么需要：若只改 canonical 不改 og:url，分享卡片的落地地址会与规范化地址打架。
 * 说明：只改值、不新增标签（新增 og 标签会与 Yoast 的输出重复）。
 *
 * @param string $url Yoast 生成的 og:url。
 * @return string
 */
function mytheme_fix_front_page_opengraph_url( $url ) {
	return is_front_page() ? home_url( '/' ) : $url;
}
add_filter( 'wpseo_opengraph_url', 'mytheme_fix_front_page_opengraph_url' );
