<?php
/**
 * 404 模板（可复制骨架）
 *
 * 职责：提示页面不存在，给出搜索入口、最近文章列表与返回首页按钮，避免访客直接关掉页面。
 * 来源：参考主题的 404.php（经典 PHP 主题），补上搜索表单与最近文章列表。
 * 落地位置：新主题根目录 404.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme- 替换为你的主题短名（含 aria-labelledby 的 id）。
 * TODO 2. 「页面不存在」「最近文章」等文案与取数篇数（posts_per_page，默认 5）按需调整。
 * TODO 3. 不需要最近文章列表时，把 WP_Query 与整个 section 一起删掉（WP_Query 与 wp_reset_postdata() 成对删除）。
 *
 * 排错提示：若服务器（nginx）在请求进入 WordPress **之前**就用 error_page 拦截了不存在的地址，
 * WordPress 根本收不到这个请求，主题的 404.php（以及 SEO 插件的 404 noindex）都不会生效，
 * 访客看到的会是服务器默认的 404 页。排查与改法见 references/07-性能安全与部署.md（「404 页面变成服务器默认页」一条）。
 *
 * 说明：最近文章用侧栏卡片风格的紧凑列表（缩略图 + 标题 + 日期），与文章详情页侧栏模块观感一致。
 *
 * 依赖：get_search_form()（核心函数；主题未提供 searchform.php 时自动回落到 WordPress 默认表单）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header();

// 最近文章：独立查询，不依赖调用方的主循环；取 5 篇已发布文章。
$mytheme_recent_query = new WP_Query(
	array(
		'posts_per_page'      => 5,
		'post_status'         => 'publish',
		'ignore_sticky_posts' => true,
		'no_found_rows'       => true,
	)
);
?>
<div class="container mx-auto max-w-3xl px-4 py-8 space-y-6">
	<?php // 主提示卡：居中窄容器，一个主按钮把人送回首页。 ?>
	<div class="card bg-base-100 shadow-sm">
		<div class="card-body items-center text-center">
			<h1 class="card-title">页面不存在</h1>
			<p class="text-base-content/70">你访问的页面可能已被删除，或地址输入有误。</p>
			<div class="w-full max-w-md"><?php get_search_form(); ?></div>
			<div class="card-actions mt-2">
				<a class="btn btn-primary" href="<?php echo esc_url( home_url( '/' ) ); ?>">返回首页</a>
			</div>
		</div>
	</div>

	<?php
	// 最近文章（紧凑列表）：给访客一个可继续点击的出口；一篇文章都没有时整块不输出，避免出现空区块。
	if ( $mytheme_recent_query->have_posts() ) :
		?>
		<section class="card bg-base-100 shadow-sm" aria-labelledby="mytheme-404-recent-heading">
			<div class="card-body gap-4">
				<h2 id="mytheme-404-recent-heading" class="card-title text-lg">最近文章</h2>
				<ul class="flex flex-col gap-3">
					<?php
					while ( $mytheme_recent_query->have_posts() ) :
						$mytheme_recent_query->the_post();
						?>
						<li>
							<a class="group flex items-start gap-3 rounded-box border-l-2 border-base-300/70 py-1.5 pr-1 pl-3 transition-colors hover:border-primary hover:bg-base-200/60" href="<?php the_permalink(); ?>">
								<figure class="aspect-[16/9] w-24 shrink-0 overflow-hidden rounded-box bg-base-200 ring-1 ring-base-300/70">
									<?php if ( has_post_thumbnail() ) : ?>
										<?php the_post_thumbnail( 'medium', array( 'class' => 'h-full w-full object-cover', 'loading' => 'lazy' ) ); ?>
									<?php endif; ?>
								</figure>
								<div class="min-w-0 flex-1">
									<h3 class="text-sm leading-snug font-medium line-clamp-2 group-hover:text-primary"><?php the_title(); ?></h3>
									<time class="text-xs text-base-content/60" datetime="<?php echo esc_attr( get_the_date( 'c' ) ); ?>"><?php echo esc_html( get_the_date( 'Y-m-d' ) ); ?></time>
								</div>
							</a>
						</li>
						<?php
					endwhile;
					?>
				</ul>
			</div>
		</section>
		<?php
	endif;

	// 本页用了自定义查询，必须还原全局 $post，避免影响后续输出。
	wp_reset_postdata();
	?>
</div>
<?php
get_footer();
