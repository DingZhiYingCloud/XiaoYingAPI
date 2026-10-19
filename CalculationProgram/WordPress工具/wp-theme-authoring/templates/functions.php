<?php
/**
 * 主题入口文件（可复制骨架）
 *
 * 职责：定义主题目录 / URL 常量 → 加载 inc/ 下的配置与业务文件 → 声明主题支持的特性 → 注册前台静态资源。
 * 来源：本技能包 templates/ 骨架（写法：经典 PHP 主题，非 FSE / 非区块主题）。
 * 落地位置：新主题根目录 functions.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme / MYTHEME_ / mytheme- 替换为你的主题短名（例：acme → acme / ACME_ / acme-），
 *          并在全主题内保持统一——函数名、常量名、资源 handle、wp_localize_script 的对象名要一起改。
 * TODO 2. 按项目实际存在的文件增删下面的 require_once 列表：写进来的文件必须真实存在，否则直接致命报错。
 * TODO 3. assets/js/main.js 换成你的脚本文件名；不需要前端脚本时，删掉整段脚本注册（含 wp_localize_script）。
 * TODO 4. 不打算关闭 WindPress 前台运行时编译时，删掉文件末尾的函数与 add_filter 两处。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 主题根目录绝对路径（带结尾斜杠）。
 * 用途：拼本地文件路径（例如判断样式产物是否存在）。
 */
define( 'MYTHEME_THEME_DIR', trailingslashit( get_template_directory() ) );

/**
 * 主题根目录 URL（带结尾斜杠）。
 * 用途：wp_enqueue_style() / wp_enqueue_script() 里拼资源地址；模板中不要手写相对路径。
 */
define( 'MYTHEME_THEME_URI', trailingslashit( get_template_directory_uri() ) );

// 集中配置层必须最先加载：后面的业务文件都依赖其中的常量。
require_once MYTHEME_THEME_DIR . 'inc/config.php';

// TODO: 按实际存在的文件续写，加载顺序固定为 config → class → 数据层 → rest-api → seo → comments。
// 下面几行是参考实现的文件名，改名后按需启用；文件不存在时不要 require，会致命报错。
// require_once MYTHEME_THEME_DIR . 'inc/class-api-client.php';
// require_once MYTHEME_THEME_DIR . 'inc/rest-api.php';
// require_once MYTHEME_THEME_DIR . 'inc/seo.php';
// require_once MYTHEME_THEME_DIR . 'inc/comments.php';

/**
 * 主题初始化：声明主题支持的特性（四组固定声明，缺一项对应能力就失效），并注册导航菜单位置。
 */
function mytheme_after_setup_theme() {
	// 1. 让 WordPress 自动生成并输出页面 <title>：模板里不要再手写 <title>。
	add_theme_support( 'title-tag' );

	// 2. 在 <head> 输出 RSS feed 链接（rel="alternate" type="application/rss+xml"），便于阅读器自动发现。
	add_theme_support( 'automatic-feed-links' );

	// 3. 开启后台编辑页的「特色图片」元框，并启用 has_post_thumbnail() / the_post_thumbnail()。
	add_theme_support( 'post-thumbnails' );

	// 4. 让 WordPress 输出 HTML5 语义标记（评论列表、评论表单、搜索表单、图集、图注），并省略 style/script 的 type 属性。
	add_theme_support(
		'html5',
		array(
			'comment-list',
			'comment-form',
			'search-form',
			'gallery',
			'caption',
			'style',
			'script',
		)
	);

	// 5. 注册导航菜单位置：header.php 用 wp_nav_menu( array( 'theme_location' => 'primary' ) ) 输出主导航。
	//    未注册该位置时 wp_nav_menu() 必然回退到 wp_page_menu()（导航外观与后台菜单管理都会失效），
	//    所以这里注册的 id 必须与模板里使用的 theme_location 一致。
	register_nav_menus(
		array(
			'primary' => '主导航',
		)
	);
}
add_action( 'after_setup_theme', 'mytheme_after_setup_theme' );

/**
 * 注册前台样式与脚本。
 *
 * 用 filemtime() 取文件修改时间当版本号：文件一改 URL 就变，不会被浏览器或 CDN 的旧缓存卡住。
 */
function mytheme_enqueue_assets() {
	// 预编译样式产物（由 `npm run build:css` 生成）：先于自定义样式加载，保证首屏即带完整样式。
	$tailwind_relative_path = 'assets/css/tailwind.css';
	$tailwind_absolute_path = MYTHEME_THEME_DIR . $tailwind_relative_path;

	// 产物不存在时不注册，避免产生 404 请求（此时前台会缺 Tailwind 样式，先跑一次 build:css）。
	if ( file_exists( $tailwind_absolute_path ) ) {
		wp_enqueue_style(
			'mytheme-tailwind',
			MYTHEME_THEME_URI . $tailwind_relative_path,
			array(),
			(string) filemtime( $tailwind_absolute_path )
		);
	}

	// 自定义补充样式（手写、不需要构建）：只放工具类无法表达的规则（正文排版、分页外观等）。
	$style_relative_path = 'assets/css/theme.css';
	$style_absolute_path = MYTHEME_THEME_DIR . $style_relative_path;

	// 文件不存在时不注册，避免产生 404 请求。
	if ( file_exists( $style_absolute_path ) ) {
		wp_enqueue_style(
			'mytheme-theme',
			MYTHEME_THEME_URI . $style_relative_path,
			array(),
			(string) filemtime( $style_absolute_path )
		);
	}

	// 前端脚本：不存在时不注册，避免产生 404 请求。
	$script_relative_path = 'assets/js/main.js'; // TODO: 换成你的脚本文件名。
	$script_absolute_path = MYTHEME_THEME_DIR . $script_relative_path;

	if ( file_exists( $script_absolute_path ) ) {
		wp_enqueue_script(
			'mytheme-script',
			MYTHEME_THEME_URI . $script_relative_path,
			array(),
			(string) filemtime( $script_absolute_path ),
			true
		);

		// 只向前端下发确实需要的值（这里仅 REST 基址）；app_secret 之类的敏感配置绝不下发。
		wp_localize_script(
			'mytheme-script',
			'MyTheme',
			array(
				'restUrl' => rest_url( 'mytheme/v1' ),
			)
		);
	}

	// 启用嵌套评论时，必须加载 comment-reply 脚本，「回复」链接才能把表单移到对应楼层。
	if ( is_singular() && comments_open() && get_option( 'thread_comments' ) ) {
		wp_enqueue_script( 'comment-reply' );
	}
}
add_action( 'wp_enqueue_scripts', 'mytheme_enqueue_assets' );

/**
 * 关闭 WindPress 的前台运行时编译（可选代码块，不需要就整块删掉）。
 *
 * 保留时机：站点装了 WindPress，且主题已用 Tailwind CLI 产出 assets/css/tailwind.css。
 * 删除时机：站点没装 WindPress（过滤器虽无副作用但也没意义），或本站就打算用 WindPress 运行时编译。
 * 兜底逻辑：仅当预编译产物存在时才拦截；产物缺失时不拦截，继续由 WindPress 兜底，不会出现「完全无样式」。
 * 影响范围：只影响前台，WindPress 后台与编辑器功能不受影响。
 */
function mytheme_disable_windpress_runtime() {
	return file_exists( MYTHEME_THEME_DIR . 'assets/css/tailwind.css' );
}
add_filter( 'f!windpress/core/runtime:is_prevent_load', 'mytheme_disable_windpress_runtime' );
