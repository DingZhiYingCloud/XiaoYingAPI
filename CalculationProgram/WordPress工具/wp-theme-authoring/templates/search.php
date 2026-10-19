<?php
/**
 * 搜索结果模板（可复制骨架）
 *
 * 职责：输出搜索关键词与命中数量、搜索表单，列表本体复用公共列表片段。
 * 来源：参考主题的 search.php（经典 PHP 主题）。
 * 落地位置：新主题根目录 search.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme 替换为你的主题短名。
 * TODO 2. 「搜索结果：」「共 N 篇」文案按站点语言自行替换。
 *
 * 标题层级与空态处理：
 * 1. h1 落在本文件（带搜索词），列表卡片标题用 h2，由 template-parts/post-list.php 输出，一页仍只有一个 h1；
 * 2. 无结果时的空态文案由 post-list 片段负责，且它在搜索页会自动带上关键词
 *    （「没有找到与「xxx」相关的内容」），本文件不要再重复输出一份空态，否则会出现两段提示。
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

// 命中数量必须取全局 $wp_query（WordPress 的主查询对象），不是 get_queried_object()。
$mytheme_search_query = get_search_query();
$mytheme_found_posts  = (int) $wp_query->found_posts;
?>
<div class="container mx-auto max-w-6xl px-4 py-8 space-y-6">
	<header class="space-y-2">
		<h1 class="text-2xl font-bold">搜索结果：<?php echo esc_html( $mytheme_search_query ); ?></h1>
		<p class="text-base-content/70">共 <?php echo esc_html( (string) $mytheme_found_posts ); ?> 篇</p>
	</header>
	<?php get_search_form(); ?>
	<?php get_template_part( 'template-parts/post-list' ); ?>
</div>
<?php
get_footer();
