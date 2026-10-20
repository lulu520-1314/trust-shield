/* 静态演示版的网络垫片：把 /api/* 换成本地预置数据，页面代码本身不用改。 */
(function () {
  const D = window.__DEMO__ || { samples: {}, reports: {}, answers: {} };
  const json = (obj, status) => new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { 'Content-Type': 'application/json' },
  });

  const realFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const path = url.replace(/^https?:\/\/[^/]+/, '').replace(/^.*\/trust-shield\//, '/');

    if (path.startsWith('/api/samples')) {
      const scene = (path.split('scene=')[1] || 'post').split('&')[0];
      return Promise.resolve(json(D.samples[scene] || []));
    }
    if (path.startsWith('/api/sample/')) {
      const id = path.slice('/api/sample/'.length).split('?')[0];
      const rep = D.reports[id];
      if (!rep) return Promise.resolve(json({ error: '演示数据里没有这个样例' }, 404));
      return Promise.resolve(json(rep));
    }
    if (path.startsWith('/api/ask')) {
      try {
        const body = init && init.body ? JSON.parse(init.body) : {};
        const key = `${body.id}||${body.q}`;
        const ans = D.answers[key];
        if (ans) return Promise.resolve(json({ answer: ans }));
      } catch (_) { /* 忽略 */ }
      return Promise.resolve(json({
        answer: '这是静态演示版，只预置了下方几个常用问题的回答；' +
          '完整问答请本地运行（python -m uvicorn app.server:app）。',
      }));
    }
    if (path.startsWith('/api/analyze') || path.startsWith('/api/extract')) {
      return Promise.resolve(json({
        error: '静态演示版不支持上传新素材。页面上是 4 组预生成结果，' +
          '可以切换左侧示例查看；完整功能请本地运行。',
      }, 400));
    }
    return realFetch(input, init);
  };

  function banner() {
    const card = document.querySelector('.card');
    if (!card || document.querySelector('.demo-banner')) return;
    const el = document.createElement('div');
    el.className = 'demo-banner';
    el.innerHTML = '<b>静态演示 · 只读</b>' +
      '<span>数据是 5 组预生成结果，不能上传新图片。' +
      '点左侧示例切换场景，或直接按「开始核验」重新播放。</span>';
    card.insertBefore(el, card.firstChild ? card.firstChild.nextSibling : null);
  }

  window.addEventListener('DOMContentLoaded', function () {
    document.body.classList.add('demo');
    banner();
    const st = document.getElementById('statusText');
    if (st) st.textContent = '静态演示 · 预生成';

    // 首屏与切换场景时，自动点开第一组样例：评委不用先摸索
    let lastScene = null;
    const pickFirst = () => {
      const tab = document.querySelector('#tabs button.active');
      const scene = tab ? tab.dataset.scene : 'post';
      if (scene === lastScene) return;
      const btn = document.querySelector('#samples button');
      if (!btn) return;
      lastScene = scene;
      setTimeout(() => btn.click(), 150);
    };
    new MutationObserver(pickFirst).observe(document.body, { childList: true, subtree: true });
    setTimeout(pickFirst, 400);
  });
})();
