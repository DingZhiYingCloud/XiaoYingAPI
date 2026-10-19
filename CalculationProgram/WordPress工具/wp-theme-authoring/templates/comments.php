<?php
/**
 * 评论区模板（可复制骨架）
 *
 * 职责：输出评论列表（支持嵌套）、评论分页、空态与「发表评论」表单。
 * 来源：本技能包 templates/ 骨架（写法：经典 PHP 主题 + Tailwind 4 + daisyUI 5 预编译）。
 * 落地位置：新主题根目录 comments.php（由 single.php 的 comments_template() 引入）。
 *
 * 复制后必须改的地方：
 * TODO 1. 【重要】评论项渲染回调 mytheme_comment_item() 与评论表单样式都在 inc/comments.php
 *          （还有 mytheme_real_comment_count() / mytheme_comment_count_badge()），**需一并复制该文件**，
 *          否则本模板会因找不到回调与函数而致命报错。
 * TODO 2. mytheme_ 前缀统一替换为你的主题短名，并与 inc/comments.php 中的函数名保持一致。
 * TODO 3. 改动了下面的类名后，必须重新执行 `npm run build:css`，否则嵌套列表排版不生效。
 *
 * 说明：
 * 1. 嵌套评论由 WordPress 输出为 ol.children，这里用任意变体类名排版，因此不需要写任何自定义 CSS；
 * 2. 评论区只在文章详情页调用；页面模板不要调用 comments_template()；
 * 3. 'format' => 'html5' 与 functions.php 里 add_theme_support( 'html5', array( 'comment-list', 'comment-form' ) ) 配套，缺一不可。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

// 需要密码才能阅读的文章不显示评论区。
if ( post_password_required() ) {
	return;
}

$mytheme_real_count = mytheme_real_comment_count();
?>
<section id="comments" class="card mt-6 bg-base-100 shadow-sm">
	<div class="card-body">
		<h2 class="card-title text-lg">
			评论
			<?php if ( $mytheme_real_count > 0 ) : ?>
				<span class="badge badge-sm"><?php echo esc_html( number_format_i18n( $mytheme_real_count ) ); ?></span>
			<?php endif; ?>
		</h2>

		<?php if ( have_comments() ) : ?>
			<?php if ( 0 === $mytheme_real_count ) : ?>
				<?php // 只有引用通告（没有读者评论）时说清楚，避免与下方列表产生歧义。 ?>
				<p class="text-sm text-base-content/70">还没有评论，来说两句吧。以下为本文的引用通告：</p>
			<?php endif; ?>
			<ol class="m-0 list-none p-0 [&_ol.children]:mt-2 [&_ol.children]:list-none [&_ol.children]:border-l [&_ol.children]:border-base-300 [&_ol.children]:pl-4 [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
				<?php
				wp_list_comments(
					array(
						'callback'   => 'mytheme_comment_item',
						'style'      => 'ol',
						'format'     => 'html5',
						'short_ping' => true,
					)
				);
				?>
			</ol>

			<?php
			the_comments_pagination(
				array(
					'prev_text' => '上一页',
					'next_text' => '下一页',
					'mid_size'  => 1,
				)
			);
			?>
		<?php else : ?>
			<p class="text-sm text-base-content/70">还没有评论，来说两句吧。</p>
		<?php endif; ?>

		<?php if ( ! comments_open() ) : ?>
			<p class="mt-2 text-sm text-base-content/70">评论功能已关闭。</p>
		<?php endif; ?>

		<?php // 表单字段与按钮样式由 inc/comments.php 的 comment_form_defaults 过滤器统一调整。 ?>
		<?php comment_form(); ?>
	</div>
</section>
