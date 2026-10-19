<?php
/**
 * 文章列表片段（可复制骨架）
 *
 * 职责：供 home.php / archive.php / search.php / index.php 共同复用，只做两件事：
 * 1. 循环输出响应式网格卡片（封面图或等高占位块、分类徽标、日期、评论数徽标、标题、摘要、阅读全文）；
 * 2. 有文章时输出分页，无文章时输出中文空态（搜索页空态带上搜索词）。
 * 来源：本技能包 templates/ 骨架（写法：经典 PHP 主题 + Tailwind 4 + daisyUI 5 预编译）。
 * 落地位置：新主题根目录 template-parts/post-list.php。
 *
 * 复制后必须改的地方：
 * TODO 1. mytheme_ / mytheme- 前缀统一替换为你的主题短名。
 * TODO 2. 评论数徽标调用 mytheme_comment_count_badge()，该函数在 inc/comments.php，需一并复制；
 *          不需要评论时删掉这一行即可。
 * TODO 3. 改动了下面的类名后，必须重新执行 `npm run build:css`。
 *
 * 标题层级（最容易写错）：
 * - 列表页的页面级 h1 在**调用方模板**里（home.php 用 single_post_title()、archive.php 用术语名、search.php 用搜索词）；
 * - 本片段是循环体，卡片标题**只能用 h2**，否则一页会出现多个 h1、破坏标题结构。
 *
 * 其他要点：
 * - 本片段依赖调用方已处于主循环上下文（have_posts() / the_post() 可用），自己不做 query_posts；
 * - 无封面时必须输出等高占位块（aspect-[16/9]），否则同一行卡片高度参差；
 * - 分页外观来自 assets/css/theme.css 的 .page-numbers 规则，不需要在模板里额外加类。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
?>
<?php if ( have_posts() ) : ?>
	<div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
		<?php
		while ( have_posts() ) :
			the_post();
			?>
			<article class="card bg-base-100 shadow-sm transition-shadow hover:shadow-md">
				<?php if ( has_post_thumbnail() ) : ?>
					<figure class="aspect-[16/9] overflow-hidden">
						<a class="block h-full w-full" href="<?php the_permalink(); ?>">
							<?php the_post_thumbnail( 'medium_large', array( 'class' => 'h-full w-full object-cover' ) ); ?>
						</a>
					</figure>
				<?php else : ?>
					<?php // 无特色图片时输出等高占位块，保证同一行卡片高度一致。 ?>
					<div class="flex aspect-[16/9] items-center justify-center bg-base-200 text-sm text-base-content/50">暂无封面</div>
				<?php endif; ?>
				<div class="card-body gap-2">
					<div class="flex flex-wrap items-center gap-2 text-sm text-base-content/70">
						<?php
						// get_the_category() 返回当前文章的全部分类，逐个输出为 badge 链接以支持多分类。
						foreach ( get_the_category() as $mytheme_category ) :
							?>
							<a class="badge badge-sm badge-outline" href="<?php echo esc_url( get_category_link( $mytheme_category ) ); ?>"><?php echo esc_html( $mytheme_category->name ); ?></a>
							<?php
						endforeach;
						?>
						<time datetime="<?php echo esc_attr( get_the_date( 'c' ) ); ?>"><?php echo esc_html( get_the_date( 'Y-m-d' ) ); ?></time>
						<?php
						// 评论数徽标（只算真实评论，且为 0 时不输出，所以调用处不需要写 if）。
						mytheme_comment_count_badge();
						?>
					</div>
					<h2 class="card-title text-lg">
						<a class="link link-hover line-clamp-2" href="<?php the_permalink(); ?>"><?php the_title(); ?></a>
					</h2>
					<p class="text-sm text-base-content/70"><?php echo esc_html( wp_trim_words( get_the_excerpt(), 24, '…' ) ); ?></p>
					<a class="link link-primary text-sm" href="<?php the_permalink(); ?>">阅读全文 →</a>
				</div>
			</article>
			<?php
		endwhile;
		?>
	</div>

	<?php
	the_posts_pagination(
		array(
			'prev_text' => '上一页',
			'next_text' => '下一页',
			'mid_size'  => 1,
		)
	);
	?>
<?php elseif ( is_search() ) : ?>
	<p class="py-8 text-center text-base-content/60">
		<?php echo esc_html( '没有找到与「' . get_search_query() . '」相关的内容，试试其他关键词。' ); ?>
	</p>
<?php else : ?>
	<p class="py-8 text-center text-base-content/60">暂无内容。</p>
<?php endif; ?>
