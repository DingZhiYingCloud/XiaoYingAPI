/* 反馈附件图片灯箱：点击缩略图在当前页看大图（不再新开窗口）
 *
 * 与 feedback/_attachments.html（缩略图按钮）、feedback/_lightbox.html（<dialog> 外壳）配套。
 * 用事件委托：同页出现的多个附件网格（提交附件、各条回复的附件）共用一个监听器。
 * 关闭方式：Esc（<dialog> 原生）、「关闭」按钮（<form method="dialog">）、点击背景。
 */
(function () {
  'use strict';

  function pick() {
    var box = document.getElementById('fb-lightbox');
    var img = document.getElementById('fb-lightbox-img');
    return box && img ? { box: box, img: img } : null;
  }

  // 点背景关闭：daisyUI 的 .modal 把内容包在 .modal-box 里，落在 <dialog> 自身上的点击即背景
  var found = pick();
  if (found) {
    found.box.addEventListener('click', function (event) {
      if (event.target === found.box) found.box.close();
    });
  }

  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-fb-lightbox]');
    if (!trigger) return;
    var elements = pick();
    if (!elements) return;                       // 页面没有灯箱（未引入片段）时不做任何事
    event.preventDefault();
    elements.img.src = trigger.getAttribute('data-fb-lightbox');
    elements.img.alt = trigger.getAttribute('data-fb-alt') || '';
    if (typeof elements.box.showModal === 'function') {
      elements.box.showModal();
    }
  });
})();
