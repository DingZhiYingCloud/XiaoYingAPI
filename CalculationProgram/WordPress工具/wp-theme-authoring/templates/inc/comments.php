<?php
/**
 * 评论区逻辑（可复制骨架）
 *
 * 职责：集中评论区的四件事——真实评论数统计与徽标、彩色首字占位头像、单条评论渲染回调、评论表单样式。
 * 来源：本技能包 templates/ 骨架（写法：经典 PHP 主题 + Tailwind 4 + daisyUI 5 预编译）。
 * 落地位置：新主题根目录 inc/comments.php，并在 functions.php 的 require_once 列表里启用本文件
 *          （文件不存在时不要 require，否则直接致命报错）。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme / mytheme- 前缀替换为你的主题短名（例：acme → acme_ / acme-），
 *          并同步修改调用方的函数名：comments.php（mytheme_real_comment_count）、
 *          single.php 与 template-parts/post-list.php（mytheme_comment_count_badge），
 *          以及 comments.php 里 wp_list_comments() 的 'callback' => 'mytheme_comment_item'，四处必须一致。
 * TODO 2. mytheme-comment-text 是给评论正文预留的钩子类名（本文件不写任何自定义 CSS），
 *          需要给它加排版规则时写在 assets/css/theme.css，改完重新执行 npm run build:css。
 * TODO 3. 表单与回复入口的中文文案（「发表评论」「回复」「邮箱不会公开显示……」）按站点语言自行替换。
 *
 * 说明：
 * 1. 头像不使用 Gravatar 外链（国内访问不稳定），改为按昵称哈希取固定配色 + 首字的占位头像，同一昵称始终同色；
 * 2. 评论区只在文章详情页输出（由 single.php 调用 comments_template()），页面模板不要调用；
 * 3. 样式全部使用 daisyUI / Tailwind 类名，新增或修改类名后需执行 `npm run build:css`。
 *
 * 依赖：无第三方依赖，仅用 WordPress 自带函数与 PHP 的 mbstring 扩展（mb_substr / mb_strtoupper）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 按昵称取占位头像的配色类（同一昵称结果固定）。
 *
 * @param string $name 评论者昵称。
 * @return string daisyUI 背景与前景色类名。
 */
function mytheme_avatar_color_class( $name ) {
	$mytheme_palette = array(
		'bg-primary text-primary-content',
		'bg-secondary text-secondary-content',
		'bg-accent text-accent-content',
		'bg-info text-info-content',
		'bg-success text-success-content',
		'bg-neutral text-neutral-content',
	);

	$mytheme_index = abs( crc32( (string) $name ) ) % count( $mytheme_palette );

	return $mytheme_palette[ $mytheme_index ];
}

/**
 * 取昵称首字：中文取第一个字，英文取首字母并大写。
 *
 * @param string $name 评论者昵称。
 * @return string 单个字符。
 */
function mytheme_avatar_initial( $name ) {
	$mytheme_name = trim( wp_strip_all_tags( (string) $name ) );

	if ( '' === $mytheme_name ) {
		return '?';
	}

	return mb_strtoupper( mb_substr( $mytheme_name, 0, 1 ) );
}

/**
 * 取「真实评论」数量：排除 pingback / trackback 引用通告。
 *
 * 说明：get_comments_number() 会把引用通告也算作评论，导致评论数偏大（文章互相内链会
 * 产生自引用 pingback），因此前台展示统一用本函数。
 *
 * @param int|null $post_id 文章 ID，默认当前文章。
 * @return int 已批准的真实评论数。
 */
function mytheme_real_comment_count( $post_id = null ) {
	$mytheme_post_id = $post_id ? (int) $post_id : (int) get_the_ID();

	if ( $mytheme_post_id < 1 ) {
		return 0;
	}

	return (int) get_comments(
		array(
			'post_id' => $mytheme_post_id,
			'type'    => 'comment',
			'status'  => 'approve',
			'count'   => true,
		)
	);
}

/**
 * 输出评论数徽标（仅在真实评论数大于 0 时输出，避免出现「0 评论」与引用通告带来的虚高）。
 *
 * 数量为 0 时函数直接返回、不输出任何内容，因此调用处不需要写 if。
 *
 * @param int|null $post_id            文章 ID，默认当前文章。
 * @param bool     $link_to_comments   是否渲染为跳到评论区的链接（详情页用）。
 */
function mytheme_comment_count_badge( $post_id = null, $link_to_comments = false ) {
	$mytheme_count = mytheme_real_comment_count( $post_id );

	if ( $mytheme_count < 1 ) {
		return;
	}

	$mytheme_label = esc_html( number_format_i18n( $mytheme_count ) );
	$mytheme_icon  = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5" aria-hidden="true"><path fill-rule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.84 8.84 0 0 1-2.347-.306c-.584.296-1.925.864-4.181 1.234-.2.032-.352-.176-.273-.362.354-.836.674-1.95.77-2.966C2.564 13.698 2 11.937 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7Z" clip-rule="evenodd" /></svg>';

	if ( $link_to_comments ) {
		echo '<a class="badge badge-sm badge-ghost gap-1" href="#comments" aria-label="查看评论">' . $mytheme_icon . ' ' . $mytheme_label . '</a>'; // phpcs:ignore WordPress.Security.EscapeOutput -- 图标为本函数内固定字符串，文字已转义。
		return;
	}

	echo '<span class="badge badge-sm badge-ghost gap-1">' . $mytheme_icon . ' ' . $mytheme_label . '</span>'; // phpcs:ignore WordPress.Security.EscapeOutput -- 同上。
}

/**
 * 单条评论的渲染回调（由 wp_list_comments() 调用）。
 *
 * 注意：结束标签 </li> 由 Walker_Comment 自动补全，本回调不要输出。
 *
 * @param WP_Comment $comment 评论对象。
 * @param array      $args    wp_list_comments() 参数。
 * @param int        $depth   当前嵌套层级。
 */
function mytheme_comment_item( $comment, $args, $depth ) {
	// 引用通告（pingback / trackback）不是读者评论：用紧凑行展示「引用通告 + 来源标题」，
	// 不显示头像与「回复」入口，也不参与评论数统计。
	if ( in_array( (string) $comment->comment_type, array( 'pingback', 'trackback' ), true ) ) {
		?>
		<li id="comment-<?php comment_ID(); ?>" <?php comment_class( 'mt-3' ); ?>>
			<div class="flex flex-wrap items-center gap-2 text-sm text-base-content/70">
				<span class="badge badge-xs badge-ghost">引用通告</span>
				<a class="link link-hover" href="<?php echo esc_url( get_comment_author_url( $comment ) ); ?>" rel="nofollow noopener" target="_blank"><?php echo esc_html( get_comment_author( $comment ) ); ?></a>
				<time class="text-xs text-base-content/50" datetime="<?php echo esc_attr( get_comment_time( 'c' ) ); ?>"><?php echo esc_html( get_comment_date( 'Y-m-d', $comment ) ); ?></time>
			</div>
		</li>
		<?php
		return;
	}

	$mytheme_author = get_comment_author( $comment );
	?>
	<li id="comment-<?php comment_ID(); ?>" <?php comment_class( 'mt-4' ); ?>>
		<div class="flex items-start gap-3">
			<div class="avatar avatar-placeholder" aria-hidden="true">
				<div class="w-10 rounded-full <?php echo esc_attr( mytheme_avatar_color_class( $mytheme_author ) ); ?>">
					<span class="text-base"><?php echo esc_html( mytheme_avatar_initial( $mytheme_author ) ); ?></span>
				</div>
			</div>
			<div class="min-w-0 flex-1">
				<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
					<span class="font-semibold"><?php echo esc_html( $mytheme_author ); ?></span>
					<time class="text-base-content/60" datetime="<?php echo esc_attr( get_comment_time( 'c' ) ); ?>"><?php echo esc_html( get_comment_date( 'Y-m-d H:i' ) ); ?></time>
					<?php if ( '0' === (string) $comment->comment_approved ) : ?>
						<span class="badge badge-warning badge-sm">待审核</span>
					<?php endif; ?>
				</div>
				<div class="mytheme-comment-text mt-1 text-sm">
					<?php comment_text(); ?>
				</div>
				<?php
				comment_reply_link(
					array_merge(
						(array) $args,
						array(
							'depth'      => $depth,
							'max_depth'  => isset( $args['max_depth'] ) ? $args['max_depth'] : 5,
							'reply_text' => '回复',
							'before'     => '<div class="mt-1 text-sm">',
							'after'      => '</div>',
						)
					)
				);
				?>
			</div>
		</div>
	<?php
}

/**
 * 评论表单的字段与按钮样式（daisyUI）。
 *
 * 表单控件 id / name（author、email、url、comment）由 WordPress 读取，不要改。
 *
 * @param array $defaults comment_form() 的默认参数。
 * @return array 调整后的参数。
 */
function mytheme_comment_form_defaults( $defaults ) {
	$defaults['title_reply']        = '发表评论';
	$defaults['title_reply_before'] = '<h3 id="reply-title" class="mt-6 text-lg font-semibold">';
	$defaults['title_reply_after']  = '</h3>';

	$defaults['comment_notes_before'] = '<p class="label">邮箱不会公开显示，带 * 的为必填项。</p>';

	$defaults['class_form']   = 'mt-3 space-y-3';
	$defaults['class_submit'] = 'btn btn-primary btn-sm';

	$defaults['comment_field'] = '<label class="label" for="comment">评论内容 *</label>'
		. '<textarea id="comment" name="comment" class="textarea w-full" rows="4" required aria-required="true"></textarea>';

	// 已登录或曾留言过的访客，回填其昵称/邮箱/网址。
	$mytheme_commenter = wp_get_current_commenter();

	$defaults['fields'] = array(
		'author' => '<label class="label" for="author">昵称 *</label>'
			. '<input id="author" name="author" type="text" class="input w-full" value="' . esc_attr( $mytheme_commenter['comment_author'] ) . '" required aria-required="true" />',
		'email'  => '<label class="label" for="email">邮箱 *</label>'
			. '<input id="email" name="email" type="email" class="input w-full" value="' . esc_attr( $mytheme_commenter['comment_author_email'] ) . '" required aria-required="true" />',
		'url'    => '<label class="label" for="url">网站</label>'
			. '<input id="url" name="url" type="url" class="input w-full" value="' . esc_attr( $mytheme_commenter['comment_author_url'] ) . '" />',
	);

	return $defaults;
}
add_filter( 'comment_form_defaults', 'mytheme_comment_form_defaults' );
