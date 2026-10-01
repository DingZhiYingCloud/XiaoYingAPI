/* API 文档中心 - AI 回复的 Markdown 渲染（渐进增强）
 *
 * 加载时机：文档页存在「返回 Markdown 正文」的端点时（端点在文档声明里标了 markdown=True，
 * 如 AI 服务的对话接口），模板先引入 vendor/marked.min.js，再引入本脚本。
 *
 * 为什么不用 marked 的默认配置直接渲染：
 *   1) 原始 HTML 一律丢弃（renderer.html 返回空）—— 回复正文来自大模型，可能夹带
 *      <script> / <img onerror> 这类内容，直接塞进 DOM 就等于在访客浏览器里执行；
 *   2) 链接与图片地址做协议白名单（只放行 http/https/mailto/tel 与相对地址）——
 *      marked 本身不拦 `javascript:`；不安全的地址退化成纯文本，不给可点的死链；
 *   3) 外链一律 target="_blank" + rel="noopener noreferrer"。
 *
 * 用法：window.DocsMarkdown.render(markdown文本) → HTML 字符串；渲染器不可用时返回 null，
 * 调用方据此回退为纯文本展示（见 docs.js 的 renderStream / renderResult）。
 */
(function () {
  'use strict';

  var SAFE_SCHEME = /^(https?:|mailto:|tel:)/i;
  var HAS_SCHEME = /^[a-z][a-z0-9+.-]*:/i;

  /* 地址是否放行：无协议的（相对地址 / 锚点）放行；带协议的必须在白名单内，
     javascript: / data: / vbscript: 等一律判为不安全 */
  function safeUrl(url) {
    var value = String(url === undefined || url === null ? '' : url).trim();
    if (!value) return false;
    return HAS_SCHEME.test(value) ? SAFE_SCHEME.test(value) : true;
  }

  /* 转义 HTML 属性值。
     注意：正则字面量里不要直接写引号字符 —— 引号会把 scripts/check_i18n.py 的词法
     状态机带偏（它按字符走一遍来剥注释），其后所有中文注释都会被误报成「未包翻译」。
     故引号走 split / join，不用正则。 */
  function escAttr(text) {
    return String(text === undefined || text === null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .split('"').join('&quot;');
  }

  var configured = false;

  function configure() {
    window.marked.use({
      renderer: {
        // 原始 HTML 一律丢弃
        html: function () { return ''; },
        link: function (token) {
          var text = this.parser.parseInline(token.tokens);
          if (!safeUrl(token.href)) return text;
          var title = token.title ? ' title="' + escAttr(token.title) + '"' : '';
          return '<a href="' + escAttr(token.href) + '"' + title
            + ' target="_blank" rel="noopener noreferrer">' + text + '</a>';
        },
        image: function (token) {
          var alt = escAttr(token.text);
          if (!safeUrl(token.href)) return alt;
          return '<img src="' + escAttr(token.href) + '" alt="' + alt + '" loading="lazy" />';
        }
      }
    });
  }

  window.DocsMarkdown = {
    render: function (text) {
      if (!window.marked) return null;      // 脚本没加载成：由调用方回退纯文本
      if (!configured) {
        configure();
        configured = true;
      }
      try {
        // breaks=true：大模型回复常按单换行断句，按 GFM 换行处理更接近它的原意
        return window.marked.parse(String(text === undefined || text === null ? '' : text),
          { gfm: true, breaks: true });
      } catch (e) {
        return null;
      }
    }
  };
})();
