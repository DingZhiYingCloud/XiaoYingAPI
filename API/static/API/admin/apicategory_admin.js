/* ============================================================
   API服务分类（ApiCategory）列表页折叠交互
   通过 ApiCategoryAdmin.Media 注入，仅作用于分类列表页。

   实现原理：列表行按树形顺序排列（父行之后紧跟其所有子孙行），
   每行内嵌 .apicat-tree.depth-N 标识层级。JS 遍历所有行，
   为「存在子孙」的节点添加折叠按钮：点击后隐藏其全部子孙行，
   再次点击恢复显示。

   不修改 admin 模板，完全基于 DOM 类名驱动，兼容各版本 simpleui。
   ============================================================ */
(function () {
    'use strict';

    // 立即执行：changelist 表格存在时初始化
    function init() {
        var table = document.querySelector('#result_list');
        if (!table) return;

        var rows = Array.prototype.slice.call(table.querySelectorAll('tbody tr'));
        if (rows.length < 2) return;

        // 读取一行深度
        function rowDepth(row) {
            var el = row.querySelector('.apicat-tree');
            if (!el) return null;
            var m = /depth-(\d+)/.exec(el.className);
            return m ? parseInt(m[1], 10) : null;
        }

        // 为每行计算「是否有子孙」并插入折叠按钮
        rows.forEach(function (row, i) {
            var depth = rowDepth(row);
            if (depth === null) return;

            // 检查后续行中是否存在更深的层级
            var hasChildren = false;
            for (var j = i + 1; j < rows.length; j++) {
                var nd = rowDepth(rows[j]);
                if (nd === null) continue;
                if (nd <= depth) break; // 遇到同级或上级，说明没有子孙
                hasChildren = true;
                break;
            }
            if (!hasChildren) return;

            var tree = row.querySelector('.apicat-tree');
            if (!tree) return;

            // 折叠按钮插入名称最前
            var btn = document.createElement('span');
            btn.className = 'apicat-toggle';
            btn.title = '折叠 / 展开子分类';
            btn.textContent = '▼';
            btn.setAttribute('role', 'button');
            btn.setAttribute('aria-expanded', 'true');
            tree.insertBefore(btn, tree.firstChild);

            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                toggle(row, depth, btn);
            });
        });

        function toggle(parentRow, parentDepth, btn) {
            var hidden = btn.classList.toggle('collapsed');
            btn.textContent = hidden ? '▶' : '▼';
            btn.setAttribute('aria-expanded', String(!hidden));
            var j = rows.indexOf(parentRow) + 1;
            for (; j < rows.length; j++) {
                var nd = rowDepth(rows[j]);
                if (nd === null) continue;
                if (nd <= parentDepth) break; // 到达父级边界
                rows[j].classList.toggle('apicat-hidden', hidden);
            }
        }
    }

    // 兼容：Django admin 可能在 DOM ready 前注入，双保险
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
