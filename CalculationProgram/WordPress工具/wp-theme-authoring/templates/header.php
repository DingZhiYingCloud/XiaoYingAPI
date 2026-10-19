<?php
/**
 * 页头模板（可复制骨架）
 *
 * 职责：输出完整 HTML 文档头与页头导航栏，并在文件末尾打开页面主内容区 <main>。
 * 来源：参考主题的 header.php（经典 PHP 主题，非 FSE / 非区块主题）。
 * 落地位置：新主题根目录 header.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme / MYTHEME_ 替换为你的主题短名，并与 functions.php 里的常量名保持一致。
 * TODO 2. assets/img/brand-icon.svg 是占位品牌图标，换成你自己的图标文件（尺寸保持 28×28 左右）。
 * TODO 3. 品牌副标题（bloginfo( 'description' )）不需要时，删掉 navbar-center 整块。
 * TODO 4. 导航用的是 'primary' 菜单位置：需先在 functions.php 的 after_setup_theme 里
 *          register_nav_menus( array( 'primary' => '主导航' ) )，再到后台「外观 → 菜单」建菜单并指定到该位置。
 *
 * 两条约定（最容易写错）：
 * 1. <main> 的开标签停在本文件末尾，由 footer.php 闭合：各页面模板只负责填充 <main> 内部，
 *    不要自己再开 <main>，也不要在 get_footer() 之后再写内容。
 * 2. 本文件**不要输出 h1**：h1 落在各页面模板里（single / page / archive / search / 404 …），
 *    全站每页有且只有一个 h1；页头的品牌区与导航都只用 <a> / <span>。
 *
 * 依赖：MYTHEME_THEME_URI 常量（在 functions.php 中定义）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
?>
<!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
	<meta charset="<?php bloginfo( 'charset' ); ?>">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<?php // <title> / favicon / RSS / SEO 插件标签全部交给 wp_head() 统一输出，这里不要手写，否则会重复。 ?>
	<?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>
<?php // 最外层 flex 列容器 + 底部 <main class="flex-1">：内容不足一屏时页脚依然贴在视口底部。 ?>
<div class="min-h-screen flex flex-col">
	<header class="navbar bg-base-200 px-4">
		<?php // 品牌区：图标 + 站点名，链接回首页。图标尺寸用 HTML 属性控制，间距复用 .btn 自带的图标 / 文字间距。 ?>
		<div class="navbar-start">
			<a href="<?php echo esc_url( home_url( '/' ) ); ?>" class="btn btn-ghost text-base font-bold">
				<img src="<?php echo esc_url( MYTHEME_THEME_URI . 'assets/img/brand-icon.svg' ); ?>" width="28" height="28" alt="">
				<?php bloginfo( 'name' ); ?>
			</a>
		</div>
		<?php if ( get_bloginfo( 'description' ) ) : ?>
			<?php // 品牌副标题：窄屏隐藏，避免与导航抢占空间；站点没填副标题时整块不输出。 ?>
			<div class="navbar-center hidden lg:flex">
				<span class="text-sm text-base-content/60"><?php bloginfo( 'description' ); ?></span>
			</div>
		<?php endif; ?>
		<?php
		// 主导航：优先输出后台指定到 primary 的菜单；没建菜单时回退列出页面链接。
		// 外层 <nav> 由本文件输出，所以 wp_nav_menu() 用 container => false，只吐 <ul>。
		?>
		<nav class="navbar-end" aria-label="主导航">
			<?php
			if ( has_nav_menu( 'primary' ) ) {
				wp_nav_menu(
					array(
						'theme_location' => 'primary',
						'container'      => false,
						'menu_class'     => 'menu menu-horizontal gap-1 px-1',
						'depth'          => 2,
					)
				);
			} else {
				// 回退：后台还没建菜单时列出所有页面。wp_page_menu() 的实际结构是
				// <div class="menu …"><ul>…页面链接…</ul></div>——menu_class 落在容器 div 而不是 <ul> 上，
				// 因此这里只保证「有可点的页面入口」，不保证完整的 daisyUI menu 外观；
				// 需要标准外观就按 TODO 4 注册菜单位置并到后台建菜单。
				// 不想要这个回退时，把本行整段删掉即可（导航区会留空，页面不报错）。
				wp_page_menu( array( 'menu_class' => 'menu menu-horizontal gap-1 px-1' ) );
			}
			?>
		</nav>
	</header>
	<main class="flex-1">
