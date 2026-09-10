/* 全站主题切换（daisyUI data-theme）
 * - THEMES 与 daisyUI 35 个内置主题一一对应（input.css 已 themes: all）
 * - 面板结构由本文件生成：标题 → 搜索框 → 可滚动菜单列表；
 *   行布局固定「色卡(自动) + 名称(自适应截断) + 勾选(固定)」，避免被挤压/截断。
 * - 点击任意 data-theme-set 元素即切换并持久化；<head> 内联脚本防闪烁。
 */
(function () {
  'use strict';

  var KEY = 'xyapi_theme';
  var DEFAULT_THEME = 'light';

  // [主题标识, 展示名]（daisyUI 全部 35 个内置主题）
  var THEMES = [
    ['light', gettext('明亮')], ['dark', gettext('暗黑')], ['cupcake', gettext('纸杯蛋糕')],
    ['bumblebee', gettext('大黄蜂')], ['emerald', gettext('翡翠')], ['corporate', gettext('商务')],
    ['synthwave', gettext('合成波')], ['retro', gettext('复古')], ['cyberpunk', gettext('赛博朋克')],
    ['valentine', gettext('情人节')], ['halloween', gettext('万圣夜')], ['garden', gettext('花园')],
    ['forest', gettext('森林')], ['aqua', gettext('水蓝')], ['lofi', gettext('低保真')],
    ['pastel', gettext('粉彩')], ['fantasy', gettext('幻想')], ['wireframe', gettext('线框')],
    ['black', gettext('纯黑')], ['luxury', gettext('奢华')], ['dracula', gettext('德古拉')],
    ['cmyk', 'CMYK'], ['autumn', gettext('秋日')], ['business', gettext('商务夜')],
    ['acid', gettext('酸性')], ['lemonade', gettext('柠檬水')], ['night', gettext('深夜')],
    ['coffee', gettext('咖啡')], ['winter', gettext('冬日')], ['dim', gettext('微光')],
    ['nord', gettext('北极')], ['sunset', gettext('日落')], ['caramellatte', gettext('焦糖拿铁')],
    ['abyss', gettext('深渊')], ['silk', gettext('丝绸')],
  ];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function currentTheme() {
    var cur = document.documentElement.getAttribute('data-theme');
    if (cur) return cur;
    try { return localStorage.getItem(KEY) || DEFAULT_THEME; } catch (e) { return DEFAULT_THEME; }
  }

  function applyTheme(name, persist) {
    if (!name) return;
    document.documentElement.setAttribute('data-theme', name);
    if (persist !== false) {
      try { localStorage.setItem(KEY, name); } catch (e) { /* 忽略 */ }
    }
    markActive();
    updateCurrentText();
  }

  /* 当前主题名（供高亮与标题） */
  function themeLabel(key) {
    var hit = DEFAULT_THEME;
    THEMES.forEach(function (pair) { if (pair[0] === key) hit = pair[1]; });
    return hit;
  }

  function markActive() {
    var cur = currentTheme();
    document.querySelectorAll('[data-theme-set]').forEach(function (btn) {
      var on = btn.dataset.themeSet === cur;
      btn.classList.toggle('text-primary', on);
      btn.classList.toggle('font-semibold', on);
      var check = btn.querySelector('[data-theme-check]');
      if (check) check.classList.toggle('hidden', !on);
    });
  }

  function updateCurrentText() {
    var label = themeLabel(currentTheme());
    document.querySelectorAll('[data-theme-current]').forEach(function (e) {
      e.textContent = label;
    });
  }

  /* 行内实时色卡：在 data-theme 作用域内取该主题的 CSS 变量 */
  function previewDots(theme) {
    var box = el('span', 'inline-flex shrink-0 items-center gap-0.5 pr-1');
    box.setAttribute('data-theme', theme);
    [['--color-primary', 'h-3 w-3 rounded-full'],
     ['--color-secondary', 'h-3 w-3 rounded-full'],
     ['--color-accent', 'h-3 w-3 rounded-full']].forEach(function (c) {
      var dot = el('span', c[1]);
      dot.style.background = 'var(' + c[0] + ')';
      dot.style.boxShadow = '0 0 0 1px rgb(0 0 0 / 0.08)';
      box.appendChild(dot);
    });
    return box;
  }

  /* 为每个 data-theme-menu 面板生成：标题 → 搜索框 → 主题列表 */
  function renderMenus() {
    document.querySelectorAll('[data-theme-menu]').forEach(function (panel) {
      panel.innerHTML = '';

      // 标题行：左「选择主题」，右当前主题名
      var head = el('div', 'flex items-center justify-between px-2 pb-1.5 pt-0.5');
      head.appendChild(el('span', 'text-xs font-semibold', gettext('选择主题')));
      var cur = el('span', 'badge badge-ghost badge-xs max-w-24 truncate');
      cur.dataset.themeCurrent = '';
      cur.textContent = themeLabel(currentTheme());
      head.appendChild(cur);
      panel.appendChild(head);

      // 搜索框
      var input = el('input', 'input input-sm w-full');
      input.type = 'text';
      input.placeholder = gettext('搜索主题…');
      panel.appendChild(input);

      // 列表
      var ul = el('ul',
        'menu mt-1.5 w-full min-h-0 flex-1 flex-nowrap gap-0.5 overflow-y-auto p-0 text-sm ' +
        '[scrollbar-width:none] [&::-webkit-scrollbar]:hidden');
      THEMES.forEach(function (pair) {
        var li = document.createElement('li');
        li.dataset.themeItem = pair[0];

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className =
          'flex h-8 w-full items-center gap-1.5 rounded-lg px-2 text-left hover:bg-base-200/60';
        btn.dataset.themeSet = pair[0];

        btn.appendChild(previewDots(pair[0]));
        var name = el('span', 'min-w-0 flex-1 truncate', pair[1]);
        name.title = pair[1];
        btn.appendChild(name);

        var check = el('i', 'hidden h-4 w-4 shrink-0 text-primary');
        check.dataset.themeCheck = '';
        check.setAttribute('data-lucide', 'check');
        btn.appendChild(check);

        li.appendChild(btn);
        ul.appendChild(li);
      });
      panel.appendChild(ul);

      // 过滤
      input.addEventListener('input', function () {
        var q = input.value.trim().toLowerCase();
        ul.querySelectorAll('[data-theme-item]').forEach(function (li) {
          li.classList.toggle('hidden', q !== '' && li.textContent.toLowerCase().indexOf(q) === -1);
        });
      });
    });
    if (window.lucide && lucide.createIcons) lucide.createIcons();
  }

  // 点击切换
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-theme-set]');
    if (!btn) return;
    applyTheme(btn.dataset.themeSet);
  });

  renderMenus();
  markActive();
  updateCurrentText();
  document.addEventListener('DOMContentLoaded', function () {
    renderMenus();
    markActive();
    updateCurrentText();
  });
})();
