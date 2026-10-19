<?php
/**
 * 单篇文章模板（可复制骨架）
 *
 * 职责：输出面包屑、h1 标题、元信息、特色图片、正文、标签与上下篇导航；左栏下方是评论区，右栏是可悬浮的侧栏。
 * 布局：lg（≥1024px）起两栏——左栏第 1 行正文、第 2 行评论区；右栏跨两行，内部 sticky 悬浮。
 *       窄屏退化为单栏，顺序由 DOM 决定：正文 → 侧栏 → 评论区（不要用 order-* 调整）。
 * 来源：本技能包 templates/ 骨架（写法：经典 PHP 主题 + Tailwind 4 + daisyUI 5 预编译）。
 * 落地位置：新主题根目录 single.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把 mytheme- 前缀替换为你的主题短名：正文容器 mytheme-entry 的排版规则写在 assets/css/theme.css，
 *          两处要一起改，改完重新执行 npm run build:css。
 * TODO 2. 侧栏模块换成你自己的：template-parts/related-posts 只是示例，文件不存在时 get_template_part() 会静默跳过。
 *          新增模块直接往内层 sticky 容器里追加一行 get_template_part()，不需要改任何类名。
 * TODO 3. 不需要侧栏或评论区时，整块删掉对应的 div（含 aside），并同步调整外层网格类名，否则会留下空列。
 *
 * 硬性纪律：
 * 1. 每页有且只有一个 h1（就是下面这个标题）；正文里的小标题由编辑器输出 h2 / h3。
 * 2. 两栏容器的类名一个字都不要改：minmax(0,1fr) 给正文留弹性宽度，20rem 是侧栏固定宽度。
 * 3. 面包屑最多四级，标签 / 日期等信息不要往里塞。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header();
?>
<div class="container mx-auto max-w-6xl px-4 py-8">
	<?php
	while ( have_posts() ) :
		the_post();
		?>
		<div class="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-8">
			<?php // 左栏第 1 行：正文与上下篇导航。min-w-0 防止长 URL / 宽表格把网格列撑破。 ?>
			<div class="min-w-0 lg:col-start-1 lg:row-start-1">
				<article class="card bg-base-100 shadow-sm">
					<div class="card-body">
						<?php
						// 面包屑：首页 › 文章列表页（未设置时省略）› 首个分类（无分类时省略）› 当前文章。
						$mytheme_posts_page_id   = (int) get_option( 'page_for_posts' );
						$mytheme_post_categories = get_the_category();
						?>
						<nav class="breadcrumbs text-sm" aria-label="面包屑">
							<ul>
								<li><a href="<?php echo esc_url( home_url( '/' ) ); ?>">首页</a></li>
								<?php if ( $mytheme_posts_page_id ) : ?>
									<li><a href="<?php echo esc_url( get_permalink( $mytheme_posts_page_id ) ); ?>">文章</a></li>
								<?php endif; ?>
								<?php if ( ! empty( $mytheme_post_categories ) ) : ?>
									<li><a href="<?php echo esc_url( get_category_link( $mytheme_post_categories[0] ) ); ?>"><?php echo esc_html( $mytheme_post_categories[0]->name ); ?></a></li>
								<?php endif; ?>
								<li><span aria-current="page"><?php the_title(); ?></span></li>
							</ul>
						</nav>
						<h1 class="card-title text-2xl"><?php the_title(); ?></h1>
						<div class="flex flex-wrap items-center gap-2 text-sm text-base-content/70">
							<time datetime="<?php echo esc_attr( get_the_date( 'c' ) ); ?>"><?php echo esc_html( get_the_date( 'Y-m-d' ) ); ?></time>
							<span><?php the_author(); ?></span>
							<?php
							// get_the_category_list() 不支持逐链接类名，这里只做一次最小替换，给每个分类链接加上 badge 类。
							$mytheme_categories = get_the_category_list( '' );
							if ( $mytheme_categories ) {
								echo '<span class="flex flex-wrap gap-1">' . str_replace( '<a ', '<a class="badge badge-sm badge-outline" ', $mytheme_categories ) . '</span>';
							}

							// 评论数徽标（只算真实评论，0 条时不输出），点击跳到评论区。
							// 依赖 inc/comments.php 的 mytheme_comment_count_badge()，该文件需一并复制。
							mytheme_comment_count_badge( null, true );
							?>
						</div>

						<?php
						// 特色图片：仅有特色图片时输出，位置在标题信息区之后、正文之前。
						if ( has_post_thumbnail() ) :
							?>
							<figure class="mt-4 overflow-hidden rounded-box">
								<?php the_post_thumbnail( 'large', array( 'class' => 'h-auto w-full object-cover' ) ); ?>
							</figure>
							<?php
						endif;
						?>

						<?php // 正文容器固定类名 mytheme-entry，其排版规则写在 assets/css/theme.css（不要再加内联样式）。 ?>
						<div class="mytheme-entry"><?php the_content(); ?></div>

						<?php
						$mytheme_tags = get_the_tags();
						if ( $mytheme_tags ) :
							?>
							<div class="mt-4 flex flex-wrap items-center gap-1">
								<?php foreach ( $mytheme_tags as $mytheme_tag ) : ?>
									<a class="badge badge-sm badge-primary" href="<?php echo esc_url( get_tag_link( $mytheme_tag ) ); ?>"><?php echo esc_html( $mytheme_tag->name ); ?></a>
								<?php endforeach; ?>
							</div>
							<?php
						endif;
						?>
					</div>
				</article>

				<nav class="mt-6 flex flex-wrap items-center justify-between gap-2 text-sm" aria-label="文章导航">
					<span class="link link-hover"><?php previous_post_link( '%link', '上一篇：%title' ); ?></span>
					<span class="link link-hover"><?php next_post_link( '%link', '下一篇：%title' ); ?></span>
				</nav>
			</div>

			<?php
			// 右栏：跨两行（正文行 + 评论区行），因此其内部可以 sticky 悬浮整个正文区。
			// 侧栏模块直接加在下面这个 sticky 容器里即可（相关文章 / 目录 / 订阅等）；
			// 模块间距由容器的 space-y-4 统一负责，模块自身不要再加 mt-*。
			?>
			<aside class="lg:col-start-2 lg:row-span-2 lg:row-start-1" aria-label="侧栏">
				<div class="space-y-4 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
					<?php
					// TODO: 换成你自己的侧栏模块（文件不存在时本行静默跳过，不会报错）。
					get_template_part( 'template-parts/related-posts' );

					// 后续新增模块直接往里加，例如：
					// get_template_part( 'template-parts/toc' );
					?>
				</div>
			</aside>

			<?php // 左栏第 2 行：评论区（评论列表 + 发表评论表单），模板为 comments.php。 ?>
			<div class="lg:col-start-1 lg:row-start-2">
				<?php comments_template(); ?>
			</div>
		</div>
		<?php
	endwhile;
	?>
</div>
<?php
get_footer();
