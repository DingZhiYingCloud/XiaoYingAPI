<?php
/**
 * 归档模板（可复制骨架）
 *
 * 职责：输出分类 / 标签 / 日期 / 作者等归档的 h1 标题与术语描述，列表本体复用公共列表片段。
 * 来源：参考主题的 archive.php（经典 PHP 主题）。
 * 落地位置：新主题根目录 archive.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme 替换为你的主题短名（本文件目前只用到 get_template_part 的路径，仍建议统一）。
 * TODO 2. h1 文案规则按需调整，但**不要**在分类 / 标签名前再加「分类：」「标签：」前缀，标题会变冗余。
 *
 * 标题层级与空态处理：
 * 1. h1 落在本文件：分类 / 标签归档只显示术语名称（single_term_title( '', false ) 不带前缀），
 *    日期 / 作者等其它归档沿用 WordPress 生成的归档标题；列表卡片标题用 h2，由 post-list 片段输出，
 *    一页仍然只有一个 h1。
 * 2. 归档描述可能为空（术语没填描述、日期 / 作者归档没有描述）：the_archive_description() 在描述为空时
 *    会连 $before / $after 一起跳过、整段不输出，所以不需要自己写 if，也不会留下空容器。
 *
 * 依赖：template-parts/post-list.php（列表本体）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header();
?>
<div class="container mx-auto max-w-6xl px-4 py-8 space-y-6">
	<header class="space-y-2">
		<?php
		if ( is_category() || is_tag() ) {
			// 分类 / 标签归档：只显示术语名称，自己包 h1，避免 WordPress 默认的「分类：」前缀。
			echo '<h1 class="text-2xl font-bold">' . esc_html( single_term_title( '', false ) ) . '</h1>';
		} else {
			// 日期、作者、自定义分类法等其他归档：沿用 WordPress 生成的归档标题。
			the_archive_title( '<h1 class="text-2xl font-bold">', '</h1>' );
		}

		// 描述为空时本行不输出任何内容（含容器），不会留下空的 <div>。
		the_archive_description( '<div class="text-base-content/70">', '</div>' );
		?>
	</header>
	<?php get_search_form(); ?>
	<?php get_template_part( 'template-parts/post-list' ); ?>
</div>
<?php
get_footer();
