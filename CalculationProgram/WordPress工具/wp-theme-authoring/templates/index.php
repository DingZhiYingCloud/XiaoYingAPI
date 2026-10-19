<?php
/**
 * 兜底列表模板（可复制骨架）
 *
 * 职责：为「没有更具体模板命中」的列表请求输出页面骨架（页面级 h1 + 列表本体）。
 * 来源：参考主题的 index.php（经典 PHP 主题）。
 * 落地位置：新主题根目录 index.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme 替换为你的主题短名。
 * TODO 2. 「最新文章」文案按站点定位自选；若想直接用后台「文章页」的标题，可换成 single_post_title()。
 *
 * 说明：
 * 1. 列表本体（网格卡片 + 分页 + 空态）全在 template-parts/post-list.php，本文件只负责页面骨架与 h1；
 * 2. index.php 是模板层级的最后兜底：站点提供了 home.php 时文章列表页走 home.php，
 *    本文件只兜住其它没被更具体模板命中的请求（如自定义文章类型的归档），
 *    所以这里用 is_home() 分流 h1 文案，避免所有兜底页共用一个标题；
 * 3. 本文件不输出侧栏：列表页是 sm:grid-cols-2 / lg:grid-cols-3 的卡片网格，没有侧栏位；
 *    分页与分页外观同样由 post-list 片段与 assets/css/theme.css 的 .page-numbers 规则负责，本文件不用管。
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
	<?php
	if ( is_home() ) {
		// 站点文章列表页：用一句固定的页面标题最直观（页面级 h1 唯一）。
		echo '<h1 class="text-2xl font-bold">最新文章</h1>';
	} else {
		// 其它兜底请求：沿用 WordPress 生成的归档标题，与 archive.php 的呈现方式保持一致。
		the_archive_title( '<h1 class="text-2xl font-bold">', '</h1>' );
	}
	?>
	<?php get_template_part( 'template-parts/post-list' ); ?>
</div>
<?php
get_footer();
