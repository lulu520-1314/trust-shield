/**
 * UI 自动巡检：用 CDP 驱动无头 Chrome，模拟真实点击，收集 JS 异常与状态异常。
 * 用法：node scripts/audit_ui.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE = 'http://127.0.0.1:8899';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const errors = [];
const logs = [];
const checks = [];

function check(name, ok, detail = '') {
  checks.push({ name, ok, detail });
  console.log(`${ok ? '  ok ' : ' FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id);
        this.pending.delete(m.id);
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
        return;
      }
      if (m.method === 'Runtime.exceptionThrown') {
        const d = m.params.exceptionDetails;
        errors.push(`[异常] ${d.text} ${d.exception?.description || ''}`);
      }
      if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
        logs.push('[console.error] ' + m.params.args.map((a) => a.value ?? a.description ?? '').join(' '));
      }
      if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') {
        logs.push('[log] ' + m.params.entry.text + ' ' + (m.params.entry.url || ''));
      }
    };
  }

  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: `(async () => { ${expr} })()`,
      awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) {
      errors.push(`[eval] ${r.exceptionDetails.text} ${r.exceptionDetails.exception?.description || ''}`);
      return null;
    }
    return r.result?.value;
  }

  async waitFor(expr, timeout = 15000, label = '') {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const v = await this.eval(`return !!(${expr});`);
      if (v) return true;
      await sleep(300);
    }
    if (label) check(label, false, '等待超时');
    return false;
  }
}

async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch('http://127.0.0.1:9333/json')).json();
      const page = list.find((t) => t.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch { /* 等启动 */ }
    await sleep(250);
  }
  throw new Error('Chrome 未就绪');
}

async function main() {
  const udd = mkdtempSync(join(tmpdir(), 'audit-'));
  const proc = spawn(CHROME, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--mute-audio',
    '--remote-debugging-port=9333', `--user-data-dir=${udd}`,
    '--window-size=1600,950', 'about:blank',
  ], { stdio: 'ignore' });

  const ws = new WebSocket(await connect());
  await new Promise((r) => (ws.onopen = r));
  const cdp = new CDP(ws);

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');

  await cdp.send('Page.navigate', { url: BASE + '/?scene=post&sample=post_001' });
  await sleep(5000);
  await cdp.eval(`window.__alerts = []; window.alert = (m) => window.__alerts.push(String(m)); return 1;`);
  await cdp.waitFor(`document.querySelector('#riskLabel').textContent.trim() !== '—'`);

  // ---------- 场景 1：图文
  const s1 = await cdp.eval(`return {
    risk: document.querySelector('#riskLabel').textContent.trim(),
    evCards: document.querySelectorAll('#evidence .ev').length,
    boxes: document.querySelectorAll('#boxes rect').length,
    heat: document.querySelector('#heatImg').getAttribute('src'),
    imgTabs: document.querySelectorAll('#toolbar .imgtab').length,
  };`);
  check('图文场景出结果', s1 && s1.risk.includes('高风险'), s1?.risk);
  check('证据卡有内容', s1 && s1.evCards > 0, `${s1?.evCards} 张`);
  check('区域框已绘制', s1 && s1.boxes > 0, `${s1?.boxes} 个`);
  check('图片切换按钮 = 2', s1 && s1.imgTabs === 2, `${s1?.imgTabs}`);

  // 热图视角切换
  await cdp.eval(`document.querySelector('#toolbar .chip[data-view="ela"]').click(); return 1;`);
  await sleep(500);
  const s2 = await cdp.eval(`return {src: document.querySelector('#heatImg').getAttribute('src'),
    active: document.querySelector('#toolbar .chip[data-view].active')?.dataset.view};`);
  check('切换 ELA 视角生效', !!s2 && s2.active === 'ela' && /_ela\.png/.test(s2.src || ''), JSON.stringify(s2));

  // 切到「使用前」：热图必须换成另一张
  await cdp.eval(`document.querySelectorAll('#toolbar .imgtab')[0]?.click(); return 1;`);
  await sleep(900);
  const s3 = await cdp.eval(`return {heat: document.querySelector('#heatImg').getAttribute('src'),
    tabs: document.querySelectorAll('#toolbar .imgtab').length,
    boxes: document.querySelectorAll('#boxes rect').length};`);
  check('切换图片后热图跟着换', !!s3 && s3.heat !== s2.src, s3?.heat);
  check('切换图片后按钮不重复', s3 && s3.tabs === 2, `${s3?.tabs}`);

  // 证据联动
  await cdp.eval(`document.querySelector('#evidence .ev')?.click(); return 1;`);
  await sleep(300);

  // 对话
  await cdp.eval(`
    document.querySelector('#askInput').value = '凭什么判高风险';
    document.querySelector('#askBtn').click(); return 1;`);
  await cdp.waitFor(`document.querySelectorAll('#msgs .msg').length >= 3`, 8000, '对话有回答');
  const s4 = await cdp.eval(`return document.querySelectorAll('#msgs .msg').length;`);
  check('对话返回内容', s4 >= 3, `${s4} 条消息`);

  // ---------- 场景 2：评论
  await cdp.eval(`document.querySelector('#tabs button[data-scene="comments"]').click(); return 1;`);
  await cdp.waitFor(`document.querySelectorAll('#samples button').length > 0`, 8000, '评论示例已加载');
  const cleared = await cdp.eval(`return document.querySelector('#postText').value.length + document.querySelector('#commentsText').value.length;`);
  check('切场景后输入框已清空', cleared === 0, `${cleared} 字`);

  await cdp.eval(`document.querySelectorAll('#samples button')[0].click(); return 1;`);
  await cdp.waitFor(`document.querySelector('#riskLabel').textContent.trim() !== '—'`, 15000, '评论场景出结果');
  const s5 = await cdp.eval(`return {
    risk: document.querySelector('#riskLabel').textContent.trim(),
    chartHidden: document.querySelector('#charts').classList.contains('hide'),
    canvas: document.querySelectorAll('#charts canvas').length,
    viewerHidden: document.querySelector('#viewer').classList.contains('hide'),
    textarea: document.querySelector('#commentsText').value.length,
  };`);
  check('评论场景显示图表', s5 && !s5.chartHidden && s5.canvas >= 2, `canvas=${s5?.canvas}`);
  check('评论场景隐藏图片区', s5 && s5.viewerHidden === true);
  check('示例回填了评论内容', s5 && s5.textarea > 50, `${s5?.textarea} 字`);

  // ---------- 场景 3：素材
  await cdp.eval(`document.querySelector('#tabs button[data-scene="material"]').click(); return 1;`);
  await cdp.waitFor(`document.querySelectorAll('#samples button').length > 0`, 8000, '素材示例已加载');
  await cdp.eval(`document.querySelectorAll('#samples button')[0].click(); return 1;`);
  await cdp.waitFor(`document.querySelector('#riskLabel').textContent.trim() !== '—'`, 15000, '素材场景出结果');
  const s6 = await cdp.eval(`return {
    risk: document.querySelector('#riskLabel').textContent.trim(),
    viewerHidden: document.querySelector('#viewer').classList.contains('hide'),
    evCards: document.querySelectorAll('#evidence .ev').length,
    staleCanvas: document.querySelectorAll('#charts canvas').length,
  };`);
  check('素材场景图片可见', s6 && s6.viewerHidden === false);
  // 素材场景只会有一个「文体特征」图；大于 1 说明上一场景的图表没清掉
  check('素材场景不残留上个场景的图表', s6 && s6.staleCanvas <= 1, `canvas=${s6?.staleCanvas}`);

  // ---------- 空输入
  await cdp.eval(`document.querySelector('#tabs button[data-scene="post"]').click(); return 1;`);
  await sleep(800);
  await cdp.eval(`document.querySelector('#runBtn').click(); return 1;`);
  await sleep(1200);
  const s7 = await cdp.eval(`return window.__alerts.slice(-1);`);
  check('空输入时有提示', Array.isArray(s7) && s7.length > 0, JSON.stringify(s7));

  // ---------- 文档导入（拖一个 .txt 到文案框）
  await cdp.eval(`
    const dt = new DataTransfer();
    dt.items.add(new File(['这是通过拖拽导入的测试文案，用来验证导入链路。'], 't.txt', { type: 'text/plain' }));
    const ta = document.querySelector('#postText');
    ta.value = '';
    ta.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
    return 1;`);
  const okDoc = await cdp.waitFor(`document.querySelector('#postText').value.length > 5`, 8000);
  const s8 = await cdp.eval(`return {
    len: document.querySelector('#postText').value.length,
    status: document.querySelector('#statusText').textContent.trim(),
    btn: !!document.querySelector('#btnDoc'),
  };`);
  check('拖入 .txt 能填进文案框', okDoc && s8.len > 5, JSON.stringify(s8));
  check('导入后有状态提示', /导入/.test(s8.status || ''), s8.status);

  // ---------- 报告
  console.log('\n===== JS 异常 =====');
  console.log(errors.length ? errors.map((e) => '  ' + e).join('\n') : '  无');
  console.log('\n===== console.error / 资源错误 =====');
  console.log(logs.length ? logs.slice(0, 20).map((e) => '  ' + e).join('\n') : '  无');

  const failed = checks.filter((c) => !c.ok);
  console.log(`\n巡检 ${checks.length} 项，失败 ${failed.length} 项`);

  ws.close();
  proc.kill();
  process.exit(failed.length || errors.length ? 1 : 0);
}

main().catch((e) => {
  console.error('巡检脚本异常：', e);
  process.exit(2);
});
