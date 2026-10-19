<?php
/**
 * 页脚模板（可复制骨架）
 *
 * 职责：闭合 header.php 打开的 <main> 与最外层容器，输出品牌区、友情链接栏与版权行，最后加载 wp_footer()。
 * 来源：参考主题的 footer.php（经典 PHP 主题）。
 * 落地位置：新主题根目录 footer.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把全文的 mytheme / MYTHEME_ 替换为你的主题短名，与 header.php / functions.php 保持一致。
 * TODO 2. 【重要】接入友情链接取数：把 $mytheme_friend_links 换成你自己的服务端取数函数返回值
 *          （例如 mytheme_get_friend_links()），取数规则见下方注释。没接入前保持空数组即可正常运行。
 * TODO 3. assets/img/brand-icon.svg 是占位图标，换成你自己的。
 * TODO 4. 品牌区的副标题（bloginfo( 'description' )）按需替换成站点的一句话简介，不需要就删掉那一行。
 *
 * 为什么「友情链接为空时整栏不输出」：上游接口不可用、或后台一条友链都没启用时，
 * 若照常输出标题 + 空容器，页面上会平白多出一块无内容的「友情链接」区块（用户与蜘蛛都会看到一个空栏目）。
 * 因此这里用 ! empty() 把标题与列表**一起**跳过，页脚其余内容（品牌区、版权行）不受影响。
 *
 * 友情链接取数规则（务必遵守，否则会拖慢每次页面渲染）：
 * 1. 必须由**服务端**取数后直出 HTML，蜘蛛才能抓到链接——禁止改成前端 JS 异步请求；
 * 2. 取数函数要自带 transient 缓存，把上游耗时与调用配额挡在页面渲染之外；
 * 3. 上游失败 / 无数据时必须返回空数组、绝不抛错，这样页脚其余部分照常渲染。
 *
 * 依赖：MYTHEME_THEME_URI 常量（在 functions.php 中定义）；友情链接取数函数（可选，见 TODO 2）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/*
 * 友情链接数据（可选区块）：
 * 本骨架默认给空数组 —— 友链栏目整栏不输出，页面不受影响。复制后按 TODO 2 换成你的取数函数调用即可：
 *
 *     $mytheme_friend_links = mytheme_get_friend_links();
 *
 * 每项约定包含 name / url / logo 三个键（logo 可为空字符串）。函数还没准备好时不要调用，会致命报错。
 */
$mytheme_friend_links = array();
?>
	</main>
	<footer class="footer sm:footer-horizontal items-center bg-base-200 px-4 py-6 text-sm">
		<aside>
			<?php // 品牌区：图标 + 站点名 + 一句话简介。图标尺寸用 HTML 属性控制，间距复用 flex/items-center/gap-2。 ?>
			<div class="flex items-center gap-2">
				<img src="<?php echo esc_url( MYTHEME_THEME_URI . 'assets/img/brand-icon.svg' ); ?>" width="32" height="32" alt="">
				<div>
					<p class="font-semibold"><?php bloginfo( 'name' ); ?></p>
					<p class="text-base-content/70"><?php bloginfo( 'description' ); ?></p>
				</div>
			</div>
		</aside>
		<?php
		// 无友链时连标题一起省略，避免出现空栏目（原因见文件头注释）。
		if ( ! empty( $mytheme_friend_links ) ) :
			?>
			<nav aria-label="友情链接">
				<h2 class="footer-title">友情链接</h2>
				<div class="flex flex-wrap gap-x-6 gap-y-3">
					<?php foreach ( $mytheme_friend_links as $mytheme_friend_link ) : ?>
						<a href="<?php echo esc_url( $mytheme_friend_link['url'] ); ?>" target="_blank" rel="noopener nofollow" class="link link-hover flex items-center gap-2">
							<?php
							// logo 可为空；onerror 用于图标地址失效时移除该图片元素，避免留下破图。
							if ( '' !== $mytheme_friend_link['logo'] ) :
								?>
								<img src="<?php echo esc_url( $mytheme_friend_link['logo'] ); ?>" alt="<?php echo esc_attr( $mytheme_friend_link['name'] ); ?>" width="20" height="20" loading="lazy" class="h-5 w-5 object-contain" onerror="this.remove()">
								<?php
							endif;
							?>
							<?php echo esc_html( $mytheme_friend_link['name'] ); ?>
						</a>
					<?php endforeach; ?>
				</div>
			</nav>
			<?php
		endif;
		?>
		<aside>
			<?php // 版权年用 date_i18n() 取站点时区，而不是 PHP 的 date()（后者跟随服务器时区）。 ?>
			<p class="text-base-content/70">© <?php echo esc_html( date_i18n( 'Y' ) ); ?> <?php bloginfo( 'name' ); ?></p>
		</aside>
	</footer>
</div>
<?php wp_footer(); ?>
</body>
</html>
