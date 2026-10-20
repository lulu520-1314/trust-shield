/* 信任守护师 · 前端交互
   纯原生 JS + ECharts，无构建步骤，断网可跑（vendor 本地化）。 */

const S = {
  scene: 'post',
  files: [null, null],
  report: null,
  view: 'fused',
  imgIndex: 0,
  charts: [],
  highlight: null,
  sampleId: null,
};

const $ = (s) => document.querySelector(s);
const docBtn = () => $('#btnDoc');
const DOC_BTN_HTML = (document.querySelector('#btnDoc') || {}).innerHTML || '导入文档';
const docInput = () => $('#docInput');
const $$ = (s) => Array.from(document.querySelectorAll(s));

/* ---------------------------------------------------------------- 初始化 */
async function init() {
  bindTabs();
  bindSlots();
  bindRun();
  bindChat();
  bindToolbar();
  bindDocImport();

  // 深链接：?scene=comments&sample=xxx 便于演示与截图
  const q = new URLSearchParams(location.search);
  if (q.get('scene')) {
    setScene(q.get('scene'));      // setScene 内部会调用 loadSamples
  } else {
    setScene('post');
  }
  if (q.get('sample')) loadSample(q.get('sample'));
}

function bindTabs() {
  $$('#tabs button').forEach((b) => {
    b.onclick = () => setScene(b.dataset.scene);
  });
}

const SCENE_COPY = {
  post: {
    slot: '📷 使用前 / 待检图片',
    hint: '只有一张图也能核验；补上「使用后」，才能算出实测色差与文案宣称是否对得上。',
  },
  comments: {
    slot: '',
    hint: '每行一条，或「时间 TAB 账号 TAB 内容」。带上时间才能分析发布节奏与集中投放。',
  },
  material: {
    slot: '🖼 待检素材图',
    hint: '单图鉴伪：看频域指纹、细节分布与 EXIF，判断是否 AI 生成或重度处理。',
  },
};

const EMPTY_LINE = {
  post: '上传图片与文案，或点左侧的示例样本',
  comments: '粘贴评论区内容，或点左侧的示例样本',
  material: '上传一张待检图片，或点左侧的示例样本',
};

function setScene(scene) {
  S.scene = scene;
  const copy = SCENE_COPY[scene] || SCENE_COPY.post;
  const slotLabel = $('#slotALabel');
  if (slotLabel) slotLabel.textContent = copy.slot;
  const hint = $('#dropHint');
  if (hint) hint.textContent = copy.hint;
  const aTag = $('#slotATag');
  if (aTag) aTag.textContent = scene === 'material' ? '待检素材' : '使用前';
  const empty = $('#emptyLine');
  if (empty) empty.textContent = EMPTY_LINE[scene] || EMPTY_LINE.post;
  const ta = $('#postText');
  if (ta) {
    ta.placeholder = scene === 'material'
      ? '粘贴配文（可留空）· 也可点右上「导入文档」'
      : '粘贴种草文案（标题+正文）· 少于 40 字统计意义不足 · 也可导入文档';
  }
  const tl = $('#textLabel');
  if (tl) {
    tl.classList.remove('hide');
    // 标签保持一行，说明放进输入框占位符，按钮才有位置
    tl.innerHTML = scene === 'material'
      ? '配文 <em class="opt">选填</em>'
      : scene === 'comments'
        ? '评论内容 <em class="req">粘贴或导入</em>'
        : '文案 <em class="req">建议填写</em>';
  }
  renderAskChips();
  $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.scene === scene));
  const isComments = scene === 'comments';
  $('#postText').classList.toggle('hide', isComments);
  $('#commentsText').classList.toggle('hide', !isComments);
  $('#dropZone').classList.toggle('hide', isComments);
  $('#slotB').classList.toggle('hide', scene !== 'post');
  reset();
  loadSamples();
}

function reset() {
  S.report = null;
  S.sampleId = null;
  S.files = [null, null];
  S.highlight = null;
  [0, 1].forEach((i) => {
    const el = $(`#slot${i === 0 ? 'A' : 'B'}`);
    if (!el) return;
    el.querySelector('.ph').classList.remove('hide');
    el.querySelector('.tag').classList.add('hide');
    const img = el.querySelector('img');
    if (img) img.remove();
  });
  // 切换场景要清空输入，否则上一个场景的文案会留在框里
  $('#postText').value = '';
  $('#commentsText').value = '';
  disposeCharts();
  $('#charts').innerHTML = '';
  const staleTabs = $('#toolbar').querySelector('.imgtabs');
  if (staleTabs) staleTabs.remove();
  $('#viewer').classList.add('hide');
  $('#toolbar').classList.add('hide');
  $('#charts').classList.add('hide');
  $('#evidence').innerHTML = '';
  $('#emptyState').classList.remove('hide');
  $('#narrative').textContent = '—';
  $('#hits').innerHTML = '';
  $('#bars').innerHTML = '';
  $('#riskLabel').textContent = '—';
  $('#riskLabel').style.color = '';
  $('#riskSub').textContent = '等待核验';
  drawGauge(0, 'low');
  $('#askInput').disabled = true;
  $('#askBtn').disabled = true;
  setFlow(1);
}

/* ---------------------------------------------------------------- 图片槽位 */
function bindSlots() {
  [0, 1].forEach((i) => {
    const el = $(`#slot${i === 0 ? 'A' : 'B'}`);
    if (!el) return;
    el.onclick = () => {
      const inp = document.createElement('input');
      inp.type = 'file';
      inp.accept = 'image/*';
      inp.onchange = () => inp.files[0] && setFile(i, inp.files[0]);
      inp.click();
    };
    el.ondragover = (e) => { e.preventDefault(); el.classList.add('hover'); };
    el.ondragleave = () => el.classList.remove('hover');
    el.ondrop = (e) => {
      e.preventDefault();
      el.classList.remove('hover');
      const f = e.dataTransfer.files[0];
      if (f && f.type.startsWith('image/')) setFile(i, f);
    };
  });
}

function setFile(i, file) {
  S.files[i] = file;
  const el = $(`#slot${i === 0 ? 'A' : 'B'}`);
  el.querySelector('.ph').classList.add('hide');
  el.querySelector('.tag').classList.remove('hide');
  const old = el.querySelector('img');
  if (old) old.remove();
  const img = document.createElement('img');
  img.src = URL.createObjectURL(file);
  el.prepend(img);
}

/* ---------------------------------------------------------------- 运行 */
function bindRun() {
  $('#runBtn').onclick = run;
}

async function run() {
  // 已加载示例且没有替换素材时，直接走示例接口（走缓存，演示秒出）
  if (S.sampleId && !S.files.some(Boolean) && S.scene !== 'comments') {
    await postAnalyze('/api/sample/' + S.sampleId, null, 'GET');
    return;
  }
  const fd = new FormData();
  fd.append('scene', S.scene);
  if (S.scene === 'comments') {
    fd.append('comments', $('#commentsText').value);
  } else {
    fd.append('text', $('#postText').value);
    S.files.forEach((f) => f && fd.append('files', f));
  }

  if (!hasInput()) {
    alert('先上传图片或粘贴文本');
    return;
  }
  await postAnalyze('/api/analyze', fd);
}

function hasInput() {
  if (S.scene === 'comments') return $('#commentsText').value.trim().length > 5;
  return S.files.some(Boolean) || $('#postText').value.trim().length > 5;
}

async function postAnalyze(url, body, method = 'POST') {
  showLoading(true);
  const t0 = performance.now();
  try {
    const r = await fetch(url, { method, body });
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    await sleep(Math.max(0, 1100 - (performance.now() - t0)));
    render(data);
  } catch (e) {
    alert('分析失败：' + e.message);
  } finally {
    showLoading(false);
  }
}

function showLoading(on) {
  if (on) setFlow(2);
  $('#loading').classList.toggle('on', on);
  if (!on) return;
  const nodes = $$('#steps .n');
  nodes.forEach((n) => { n.className = 'n'; });
  let i = 0;
  S._timer && clearInterval(S._timer);
  S._timer = setInterval(() => {
    nodes.forEach((n, k) => { n.className = 'n' + (k < i ? ' done' : k === i ? ' run' : ''); });
    if (i < nodes.length - 1) i += 1;
  }, 240);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------------------------------------------------------------- 示例 */
async function loadSamples() {
  const box = $('#samples');
  const sceneAtRequest = S.scene;
  box.innerHTML = '';          // 先清空：否则切场景瞬间还能点到上一个场景的示例
  try {
    const r = await fetch('/api/samples?scene=' + S.scene);
    const list = await r.json();
    if (sceneAtRequest !== S.scene) return;   // 场景已经切走，丢弃这次结果
    box.innerHTML = '';
    list.forEach((s) => {
      const b = document.createElement('button');
      b.textContent = s.name;
      b.onclick = () => loadSample(s.id);
      box.appendChild(b);
    });
  } catch (e) { /* 忽略 */ }
}

async function loadSample(id) {
  showLoading(true);
  const t0 = performance.now();
  try {
    const r = await fetch('/api/sample/' + id);
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    await sleep(Math.max(0, 900 - (performance.now() - t0)));
    S.sampleId = id;
    S.files = [null, null];   // 示例的图来自服务端，清掉残留的上传文件
    render(data);
    fillInputs(data);
  } catch (e) {
    alert('示例加载失败：' + e.message);
  } finally {
    showLoading(false);
  }
}

/* 把示例的原始素材回填到左侧，让「输入 → 输出」的对应关系看得见 */
function fillInputs(rep) {
  const inp = rep.inputs || {};
  if (rep.scene === 'comments') {
    $('#commentsText').value = inp.comments || '';
  } else {
    $('#postText').value = inp.text || '';
    (inp.images || []).forEach((url, i) => {
      if (i > 1) return;
      const el = $(`#slot${i === 0 ? 'A' : 'B'}`);
      if (!el) return;
      el.querySelector('.ph').classList.add('hide');
      el.querySelector('.tag').classList.remove('hide');
      const old = el.querySelector('img');
      if (old) old.remove();
      const img = document.createElement('img');
      img.src = './cache/' + url;
      el.prepend(img);
    });
  }
}

/* ---------------------------------------------------------------- 顶栏流程 */
function setFlow(step) {
  document.querySelectorAll('#flow .fs').forEach((el) => {
    const n = Number(el.dataset.step);
    el.classList.toggle('done', n < step);
    el.classList.toggle('on', n === step);
  });
}

/* ---------------------------------------------------------------- 渲染 */
function render(rep) {
  S.report = rep;
  S.highlight = null;
  $('#emptyState').classList.add('hide');
  renderRisk(rep.risk, rep.timing_ms);
  renderBars(rep.dimensions);
  renderNarrative(rep.narrative);
  renderHits(rep.compliance || []);
  renderEvidence(rep.findings || []);
  renderCenter(rep);
  $('#askInput').disabled = false;
  $('#askBtn').disabled = false;
  setFlow(4);
  $('#statusText').textContent = `本地推理 · ${(rep.timing_ms / 1000).toFixed(2)}s`;
}

function renderRisk(risk, ms) {
  const color = { high: '#ff4d6d', medium: '#ffb020', low: '#35d39a' }[risk.level];
  $('#riskLabel').textContent = risk.label;
  $('#riskLabel').style.color = color;
  $('#riskSub').innerHTML = `综合风险 <b style="color:#fff;font-size:15px">${Math.round(risk.score * 100)}</b> / 100<br />
    证据覆盖 ${(risk.coverage * 100).toFixed(0)}% · 耗时 ${(ms / 1000).toFixed(2)}s`;
  drawGauge(risk.score, risk.level);
}

function drawGauge(score, level) {
  const color = { high: '#ff4d6d', medium: '#ffb020', low: '#35d39a' }[level] || '#35d39a';
  const len = Math.PI * 60;
  const on = Math.max(0, Math.min(1, score)) * len;
  $('#gauge').innerHTML = `
    <path d="M10,72 A60,60 0 0 1 130,72" fill="none" stroke="#1c2a45" stroke-width="10" stroke-linecap="round"/>
    <path d="M10,72 A60,60 0 0 1 130,72" fill="none" stroke="${color}" stroke-width="10"
          stroke-linecap="round" stroke-dasharray="${on} ${len + 2}"/>
    <text x="70" y="64" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">${Math.round(score * 100)}</text>
    <text x="70" y="78" text-anchor="middle" fill="#8ea3c4" font-size="9">/ 100</text>`;
}

function renderBars(dims) {
  const names = { pixel: '像素取证', semantic: '文本文体', consistency: '图文一致性',
                  rules: '合规规则', behavior: '评论行为' };
  const legend = `<div class="bar-legend">维度分 0–100，越高越可疑</div>`;
  const rows = dims.map((d) => {
    if (d.available === false) {
      return `<div class="bar-row off">
        <div class="lab"><span>${names[d.key] || d.name}</span><span>未参与</span></div>
        <div class="bar empty"></div>
      </div>`;
    }
    const v = Math.max(0, Math.min(1, d.score || 0));
    const val = Math.round(v * 100);
    const c = v >= 0.75 ? '#ff4d6d' : v >= 0.45 ? '#ffb020' : '#35d39a';
    const tag = v >= 0.75 ? '高' : v >= 0.45 ? '中' : '低';
    const sub = d.summary ? `<div class="bar-sub">${esc(d.summary)}</div>` : '';
    return `<div class="bar-row">
      <div class="lab">
        <span>${names[d.key] || d.name}</span>
        <span><b style="color:#fff">${val}</b><span class="bar-tag" style="color:${c}">${tag}</span></span>
      </div>
      <div class="bar"><i style="width:${val}%;background:linear-gradient(90deg,${c}88,${c})"></i></div>
      ${sub}
    </div>`;
  }).join('');
  $('#bars').innerHTML = legend + rows;
}

function renderNarrative(text) {
  $('#narrative').innerHTML = (text || '—')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}

function renderHits(hits) {
  if (!hits.length) {
    $('#hits').innerHTML = '';   // 合规为 0 时维度行已说明，不再重复
    return;
  }
  $('#hits').innerHTML = hits.map((h) => `
    <div class="hit ${h.severity}">
      <div class="k">${esc(h.name)}</div>
      <div class="v">命中原文「${esc(h.context || h.text)}」</div>
      <div class="v">${esc(h.clause)} — ${esc(h.note || '')}</div>
    </div>`).join('');
}

function renderEvidence(findings) {
  // 合规命中在右栏单独成块展示，这里过滤掉，避免同一条规则出现两次
  const list = findings.filter((f) => f.dim !== 'rules');
  if (!list.length) {
    $('#evidence').innerHTML = '<div style="padding:0 4px;color:#5f7395">未发现异常特征</div>';
    return;
  }
  $('#evidence').innerHTML = list.slice(0, 6).map((f, i) => `
    <div class="ev" data-i="${i}">
      <div class="t"><span class="badge ${f.severity}">${
        { high: '高危', medium: '中危', low: '提示' }[f.severity]}</span>${esc(f.title)}</div>
      <div class="d">${esc(f.detail)}</div>
    </div>`).join('');
  $$('#evidence .ev').forEach((el) => {
    el.onclick = () => {
      S.highlight = Number(el.dataset.i);
      drawBoxes();
    };
  });
}

/* ---------------------------------------------------------------- 中间证据区 */
function renderCenter(rep) {
  const hasImg = rep.images && rep.images.length > 0;
  $('#viewer').classList.toggle('hide', !hasImg);
  $('#toolbar').classList.toggle('hide', !hasImg && rep.scene !== 'material');
  $('#charts').classList.toggle('hide', rep.scene !== 'comments');
  $('#charts').innerHTML = '';

  if (hasImg) {
    S.imgIndex = rep.images.length > 1 ? 1 : 0;
    renderImageTabs(rep);
    showImage(rep);
  }
  if (rep.scene === 'comments') renderCommentCharts(rep);
  else renderSemanticChart(rep);

  // 评论场景：图表是主视觉，放在证据卡之前；图文场景：图表作为补充，放在之后
  const body = $('#centerBody');
  const charts = $('#charts');
  const ev = $('#evidence');
  if (rep.scene === 'comments') body.insertBefore(charts, ev);
  else body.insertBefore(ev, charts);
}

function renderImageTabs(rep) {
  const tb = $('#toolbar');
  const old = tb.querySelector('.imgtabs');
  if (old) old.remove();
  if (rep.images.length < 2) return;
  const box = document.createElement('div');
  box.className = 'imgtabs';
  box.style.cssText = 'display:flex;gap:6px;padding-right:8px;margin-right:2px;border-right:1px solid #223252';
  rep.images.forEach((im, i) => {
    const b = document.createElement('button');
    b.className = 'imgtab' + (i === S.imgIndex ? ' active' : '');
    b.textContent = i === 0 ? '使用前' : '使用后';
    b.onclick = () => {
      S.imgIndex = i;
      renderImageTabs(rep);
      showImage(rep);
    };
    box.appendChild(b);
  });
  tb.insertBefore(box, tb.firstChild);
}

function showImage(rep) {
  const im = rep.images[S.imgIndex];
  if (!im) return;
  const base = $('#baseImg');
  base.src = './cache/' + im.url;
  base.onload = () => {
    $('#boxes').setAttribute('viewBox', `0 0 ${im.shape[0]} ${im.shape[1]}`);
    drawBoxes();
  };
  const heatName = (im.heat && im.heat[S.view]) || null;
  const heat = $('#heatImg');
  if (heatName) {
    heat.src = './cache/' + heatName + '?v=' + Date.now();
    heat.style.display = '';
  } else {
    heat.style.display = 'none';
  }
}

function drawBoxes() {
  const rep = S.report;
  if (!rep || !rep.images) return;
  const im = rep.images[S.imgIndex];
  if (!im) return;
  const regions = im.regions || [];
  const svg = $('#boxes');
  const hl = S.highlight != null ? rep.findings[S.highlight] : null;
  svg.innerHTML = regions.map((r, i) => {
    const [x, y, w, h] = r.bbox;
    return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6"
              opacity="${hl && hl.dim === 'pixel' ? 1 : 0.85}"/>
            <text x="${x + 6}" y="${Math.max(14, y - 6)}">区域 ${i + 1} · 可疑度 ${(r.peak * 100).toFixed(0)}%</text>`;
  }).join('');
}

function bindToolbar() {
  $$('#toolbar .chip[data-view]').forEach((b) => {
    b.onclick = () => {
      S.view = b.dataset.view;
      $$('#toolbar .chip[data-view]').forEach((x) => x.classList.toggle('active', x === b));
      if (S.report) showImage(S.report);
    };
  });
  $('#opacity').oninput = (e) => {
    $('#heatImg').style.opacity = (e.target.value / 100).toFixed(2);
  };
}

/* ---------------------------------------------------------------- 图表 */
function disposeCharts() {
  S.charts.forEach((c) => c && c.dispose());
  S.charts = [];
}

function chartEl(id) {
  const d = document.createElement('div');
  d.className = 'chart';
  d.id = id;
  $('#charts').appendChild(d);
  return echarts.init(d, null, { renderer: 'canvas' });
}

const AXIS = {
  axisLine: { lineStyle: { color: '#2a3b5c' } },
  axisLabel: { color: '#a3b8d6', fontSize: 10 },
  splitLine: { lineStyle: { color: '#1b2740' } },
};

function renderSemanticChart(rep) {
  const sem = rep.dimensions.find((d) => d.key === 'semantic');
  if (!sem || sem.available === false || !sem.features) { disposeCharts(); return; }
  disposeCharts();
  const box = $('#charts');
  box.classList.remove('hide');
  box.innerHTML = '';

  const score = Math.round((sem.score || 0) * 100);
  // 只画贡献前 6 的特征：9 条会撑破版面，而且末尾全是 0，没有信息量
  const ranked = sem.features.slice().sort((a, b) => b.contribution - a.contribution).slice(0, 5);
  const feats = ranked.slice().sort((a, b) => a.contribution - b.contribution);
  const top = ranked[0];
  const total = feats.reduce((s, f) => s + f.contribution, 0) || 1;
  const pct = (v) => Math.round((v / total) * 100);

  // 图表必须说明「这是什么、和结论什么关系」，否则就是装饰
  const cap = document.createElement('div');
  cap.className = 'chart-cap';
  cap.innerHTML = score < 45
    ? `<b>文案特征贡献度</b><span>文体分 ${score}/100；各特征贡献均偏低（最高 ${top.name} ${top.contribution}），未形成模板化证据</span>`
    : `<b>文案特征贡献度</b><span>文体分 ${score}/100；主要推手是 ${top.name}（${top.contribution}，占 ${pct(top.contribution)}%）</span>`;
  box.appendChild(cap);

  const maxV = Math.max(0.08, top.contribution * 1.3);
  const c = chartEl('chartSem');
  c.setOption({
    backgroundColor: 'transparent',
    grid: { left: 92, right: 58, top: 10, bottom: 6 },
    // 数值已经标在柱子右侧，横轴上再刻一遍只会被版面裁掉
    xAxis: {
      type: 'value', max: +maxV.toFixed(3),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false },
      splitLine: { lineStyle: { color: '#1b2740' } },
    },
    yAxis: { type: 'category', data: feats.map((f) => f.name), ...AXIS },
    series: [{
      type: 'bar',
      data: feats.map((f) => +f.contribution.toFixed(3)),
      barWidth: 9,
      itemStyle: { borderRadius: 4, color: '#4da3ff' },
      label: {
        show: true, position: 'right', color: '#a3b8d6', fontSize: 10,
        formatter: (p) => (p.value < 0.005 ? '' : `${p.value} · ${pct(p.value)}%`),
      },
    }],
    tooltip: {
      formatter: (p) => `${p.name}<br/>贡献 ${p.value}，约占文体分 ${pct(p.value)}%`,
    },
  });
  S.charts.push(c);
}

function renderCommentCharts(rep) {
  const b = rep.dimensions.find((d) => d.key === 'behavior');
  if (!b || !b.available) return;
  disposeCharts();
  $('#charts').classList.remove('hide');

  if (b.scatter && b.scatter.length) {
    const c1 = chartEl('chartScatter');
    const groups = {};
    b.scatter.forEach((p) => {
      const k = p.c < 0 ? '正常' : '簇 #' + p.c;
      (groups[k] = groups[k] || []).push([p.x, p.y]);
    });
    c1.setOption({
      backgroundColor: 'transparent',
      title: { text: '评论聚类分布', left: 8, top: 4, textStyle: { color: '#a3b8d6', fontSize: 12 } },
      grid: { left: 40, right: 16, top: 34, bottom: 28 },
      xAxis: { type: 'value', ...AXIS, scale: true },
      yAxis: { type: 'value', ...AXIS, scale: true },
      series: Object.keys(groups).map((k) => ({
        name: k, type: 'scatter', data: groups[k], symbolSize: 9,
        itemStyle: { color: k === '正常' ? '#3a5a86' : '#ff4d6d', opacity: 0.85 },
      })),
      legend: { textStyle: { color: '#a3b8d6', fontSize: 10 }, top: 2, right: 8 },
      tooltip: { trigger: 'item' },
    });
    S.charts.push(c1);
  }

  if (b.timeline && b.timeline.length) {
    const c2 = chartEl('chartTime');
    c2.setOption({
      backgroundColor: 'transparent',
      title: { text: '发布时间分布 · ' + (b.timing?.verdict || ''), left: 8, top: 4,
               textStyle: { color: '#a3b8d6', fontSize: 12 } },
      grid: { left: 46, right: 16, top: 34, bottom: 28 },
      xAxis: { type: 'category', data: b.timeline.map((t) => t.t.slice(5, 16)), ...AXIS,
               axisLabel: { ...AXIS.axisLabel, rotate: 35, interval: Math.ceil(b.timeline.length / 7) } },
      yAxis: { type: 'value', min: -1, max: 1, ...AXIS, axisLabel: { show: false }, splitLine: { show: false } },
      series: [{ type: 'scatter', data: b.timeline.map((t, i) => [i, (i % 3 - 1) * 0.30]),
                 symbolSize: 10, itemStyle: { color: '#ffb020', opacity: .9 } }],
      tooltip: { formatter: (p) => `${b.timeline[p.value[0]].t}<br/>${b.timeline[p.value[0]].usr || ''}` },
    });
    S.charts.push(c2);
  }
}

/* ---------------------------------------------------------------- 对话 */
const ASK_CHIPS = {
  post: ['为什么判这个等级', '改在哪一块', '文本文体怎么算的', '平台该怎么处置'],
  comments: ['这些评论哪里异常', '发布节奏说明什么', '平台该怎么处置'],
  material: ['这张图哪里有问题', '是不是 AI 生成', '平台该怎么处置'],
};

function renderAskChips() {
  const box = $('#askChips');
  if (!box) return;
  box.innerHTML = '';
  (ASK_CHIPS[S.scene] || ASK_CHIPS.post).forEach((q) => {
    const b = document.createElement('button');
    b.className = 'askchip';
    b.textContent = q;
    b.onclick = () => {
      $('#askInput').value = q;
      ask();
    };
    box.appendChild(b);
  });
}

/* ---------------- 文档导入（.txt / .md / .docx） ---------------- */
function activeTextarea() {
  return S.scene === 'comments' ? $('#commentsText') : $('#postText');
}

function flashStatus(text) {
  const t = $('#statusText');
  if (!t) return;
  const old = t.textContent;
  t.textContent = text;
  clearTimeout(flashStatus._t);
  flashStatus._t = setTimeout(() => { t.textContent = old; }, 4000);
}

async function importDoc(file) {
  if (!file) return;
  const okExt = /\.(txt|md|markdown|docx|doc|csv|log)$/i.test(file.name);
  if (!okExt) {
    alert('只支持 .txt / .md / .docx 这类文本文件');
    return;
  }
  const btn = docBtn();
  btn.disabled = true;
  btn.innerHTML = '读取中…';
  try {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/extract', { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || '解析失败');
    activeTextarea().value = d.text;
    flashStatus(`已导入《${d.name}》${d.chars} 字${d.truncated ? '（超长已截断）' : ''}`);
  } catch (e) {
    alert('导入失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = DOC_BTN_HTML;
  }
}

function bindDocImport() {
  const btn = docBtn();
  const input = docInput();
  if (!btn || !input) return;
  btn.onclick = () => input.click();
  input.onchange = () => {
    if (input.files && input.files[0]) importDoc(input.files[0]);
    input.value = '';
  };

  // 拖进文本框也能导入
  ['#postText', '#commentsText'].forEach((sel) => {
    const ta = $(sel);
    if (!ta) return;
    ta.addEventListener('dragover', (e) => { e.preventDefault(); ta.classList.add('drop-hover'); });
    ta.addEventListener('dragleave', () => ta.classList.remove('drop-hover'));
    ta.addEventListener('drop', (e) => {
      e.preventDefault();
      ta.classList.remove('drop-hover');
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) importDoc(f);
    });
  });
}

function bindChat() {
  $('#askBtn').onclick = ask;
  $('#askInput').onkeydown = (e) => { if (e.key === 'Enter') ask(); };
}

async function ask() {
  const q = $('#askInput').value.trim();
  if (!q || !S.report) return;
  $('#askInput').value = '';
  addMsg('user', q);
  try {
    const r = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: S.report.id, q }),
    });
    const d = await r.json();
    addMsg('bot', d.answer || '（未获取到回答）');
  } catch (e) {
    addMsg('bot', '接口异常：' + e.message);
  }
}

function addMsg(role, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  d.textContent = text;
  d.style.whiteSpace = 'pre-wrap';
  $('#msgs').appendChild(d);
  $('#msgs').scrollTop = 1e9;
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

init();
