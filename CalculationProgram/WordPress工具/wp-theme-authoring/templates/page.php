<?php
/**
 * 单页面模板（可复制骨架）
 *
 * 职责：输出面包屑、h1 标题与正文（页面默认不输出评论区）。
 * 来源：参考主题的 page.php（经典 PHP 主题），补上面包屑。
 * 落地位置：新主题根目录 page.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme- 替换为你的主题短名，并与 assets/css/theme.css 里正文容器的前缀保持一致
 *          （.mytheme-entry 两处必须同名，否则正文排版全部失效）。
 * TODO 2. 需要页面支持评论时，在 while 循环内的注释处加 comments_template()（默认不输出，与 comments.php 的约定一致）。
 *
 * 与 single.php 的差异（页面刻意精简，不要照搬 single.php 的复杂布局）：
 * 1. 没有日期 / 作者 / 分类 / 标签等元信息：页面是静态内容，没有时间与归档语义；
 * 2. 没有上一篇 / 下一篇导航：页面不是按时间排序的内容流；
 * 3. 没有右侧栏：页面用单栏窄容器（max-w-3xl）保证阅读宽度，不预留 20rem 侧栏；
 * 4. 面包屑只有两级（首页 › 当前页）：页面没有分类层级可展开。
 *
 * 标题层级：h1 落在本文件（页面标题），正文内的小标题由编辑器输出 h2 / h3。
 *
 * 依赖：assets/css/theme.css 的 .mytheme-entry 排版规则（默认不调用 comments_template()，故不依赖评论相关函数）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header();
?>
<div class="container mx-auto max-w-3xl px-4 py-8">
	<?php
	while ( have_posts() ) :
		the_post();
		?>
		<article class="card bg-base-100 shadow-sm">
			<div class="card-body">
				<?php // 面包屑两级：首页 › 当前页标题。daisyUI breadcrumbs 靠 <ul><li> 结构自动生成分隔符，不要手写 ›。 ?>
				<nav class="breadcrumbs text-sm" aria-label="面包屑">
					<ul>
						<li><a href="<?php echo esc_url( home_url( '/' ) ); ?>">首页</a></li>
						<li><span aria-current="page"><?php the_title(); ?></span></li>
					</ul>
				</nav>
				<h1 class="card-title"><?php the_title(); ?></h1>
				<?php // 正文容器类名固定 .mytheme-entry，排版规则写在 assets/css/theme.css（不要加内联样式）。 ?>
				<div class="mytheme-entry"><?php the_content(); ?></div>
			</div>
		</article>
		<?php
		// 页面默认不输出评论区（与 comments.php / inc/comments.php 的约定一致）；若某项目需要页面支持评论，在此加 comments_template()。
	endwhile;
	?>
</div>
<?php
get_footer();
