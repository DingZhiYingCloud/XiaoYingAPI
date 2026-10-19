<?php
/**
 * 主题集中配置层（可复制骨架）
 *
 * 职责：本主题所有「换环境可能要改的值」只在这里定义一次；其它文件一律通过常量引用，不得硬编码。
 * 来源：本技能包 templates/ 骨架（集中配置层写法）。
 * 落地位置：新主题根目录 inc/config.php。
 *
 * 复制后必须改的地方：
 * TODO 1. 把 mytheme / MYTHEME_ 替换为你的主题短名，并在全主题内保持统一。
 * TODO 2. 把各常量换成你自己环境的真实值——本文件全是占位值，直接上线会调用失败。
 * TODO 3. 按项目实际情况增删常量：用不到的整项删掉（连同注释），新参数照同一格式追加。
 *
 * 覆盖方式（推荐）：每个常量都用 defined() 保护，因此可以在 wp-config.php 里提前定义同名常量来覆盖。
 * 把生产密钥放在 wp-config.php，既不进主题目录，也不会在主题升级覆盖时丢失：
 *
 *     define( 'MYTHEME_API_BASE', 'https://api.example.com' );
 *     define( 'MYTHEME_APP_ID', 'YOUR_APP_ID' );
 *     define( 'MYTHEME_APP_SECRET', 'YOUR_APP_SECRET' );
 *
 * 安全红线：APP_SECRET 只在服务端使用，严禁下发前端（不得出现在任何 JS 输出或页面 HTML 中）。
 *
 * @package mytheme
 */

// 防止直接访问该文件。
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 上游 API 服务基址。
 * 注意：结尾不要带斜杠；换环境只改这一处。
 */
if ( ! defined( 'MYTHEME_API_BASE' ) ) {
	define( 'MYTHEME_API_BASE', 'https://api.example.com' );
}

/**
 * 上游 API 应用 ID（公开标识，参与签名）。
 */
if ( ! defined( 'MYTHEME_APP_ID' ) ) {
	define( 'MYTHEME_APP_ID', 'YOUR_APP_ID' );
}

/**
 * 上游 API 应用密钥，用于服务端签名。
 * 注意：只留服务端，严禁下发前端；生产环境建议定义在 wp-config.php。
 */
if ( ! defined( 'MYTHEME_APP_SECRET' ) ) {
	define( 'MYTHEME_APP_SECRET', 'YOUR_APP_SECRET' );
}

/**
 * 服务端缓存时长（秒）。缓存键建议：mytheme_cache_{业务名}。
 * 用途：把上游耗时挡在页面渲染之外，同时减少对上游的调用。
 */
if ( ! defined( 'MYTHEME_CACHE_TTL' ) ) {
	define( 'MYTHEME_CACHE_TTL', 600 );
}

/**
 * 限流窗口（秒）。
 */
if ( ! defined( 'MYTHEME_RATE_WINDOW' ) ) {
	define( 'MYTHEME_RATE_WINDOW', 60 );
}

/**
 * 限流规则：窗口内每 IP、每类接口允许的最大请求次数。
 * 键名与 REST 路由一一对应（示例 write / read，请按项目实际接口改名）。
 * 注意：太严会把真实用户挡在门外，太松等于没有限流；上线后按实际流量回调。
 */
if ( ! defined( 'MYTHEME_RATE_RULES' ) ) {
	define(
		'MYTHEME_RATE_RULES',
		array(
			'write' => 5,
			'read'  => 60,
		)
	);
}

/**
 * 真实访客 IP 的来源请求头（站点位于 CDN / 反向代理之后时必须配置）。
 *
 * 默认空字符串：限流直接使用 REMOTE_ADDR。
 * Cloudflare 场景填 'HTTP_CF_CONNECTING_IP'；Nginx 等通用反代可填 'HTTP_X_FORWARDED_FOR'。
 * 不配置的后果：REMOTE_ADDR 是 CDN 节点 IP，所有访客共用一个限流桶，真实流量一上来就大面积被拦。
 * 安全前提：只有当源站仅接受该代理回源时这个请求头才可信；源站可被直连时它可被伪造（仅影响限流，不是安全边界）。
 */
if ( ! defined( 'MYTHEME_PROXY_IP_HEADER' ) ) {
	define( 'MYTHEME_PROXY_IP_HEADER', '' );
}

/**
 * 普通请求超时（秒），用于短耗时接口。
 */
if ( ! defined( 'MYTHEME_TIMEOUT' ) ) {
	define( 'MYTHEME_TIMEOUT', 20 );
}

/**
 * 长轮询请求超时（秒），仅在存在「服务端挂起等待」的接口时需要。
 * 注意：必须大于上游挂起时长，否则会被误判为失败；无长轮询接口时整项删掉。
 */
if ( ! defined( 'MYTHEME_TIMEOUT_LONG_POLL' ) ) {
	define( 'MYTHEME_TIMEOUT_LONG_POLL', 40 );
}
