/**
 * 静态演示版自检：三个场景都能加载预生成报告，且没有 JS 异常。
 * 用法：node scripts/audit_demo.mjs
 */
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = process.argv[2] || 'http://127.0.0.1:8899/demo/';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const errors = [];
let failed = 0;

class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map();
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id);
        this.pending.delete(m.id);
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
        return;
      }
      if (m.method === 'Runtime.exceptionThrown') {
        errors.push(m.params.exceptionDetails.text + ' ' + (m.params.exceptionDetails.exception?.description || ''));
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
      expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true,
    });
    return r.exceptionDetails ? null : r.result?.value;
  }
}

const check = (name, ok, detail = '') => {
  console.log(`${ok ? '  ok ' : ' FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failed += 1;
};

async function main() {
  const udd = mkdtempSync(join(tmpdir(), 'demo-'));
  const proc = spawn(CHROME, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--mute-audio',
    '--remote-debugging-port=9337', `--user-data-dir=${udd}`,
    '--window-size=1600,950', 'about:blank',
  ], { stdio: 'ignore' });

  let wsUrl;
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch('http://127.0.0.1:9337/json')).json();
      const p = list.find((t) => t.type === 'page');
      if (p) { wsUrl = p.webSocketDebuggerUrl; break; }
    } catch { /* 等待 */ }
    await sleep(250);
  }
  const ws = new WebSocket(wsUrl);
  await new Promise((r) => (ws.onopen = r));
  const cdp = new CDP(ws);

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.navigate', { url: URL });
  await sleep(4000);

  // 首屏自动加载
  let ok = false;
  for (let i = 0; i < 40; i++) {
    const label = await cdp.eval(`return document.querySelector('#riskLabel').textContent.trim();`);
    if (label && label !== '—') { ok = true; break; }
    await sleep(300);
  }
  check('首屏自动加载出结果', ok);

  const s1 = await cdp.eval(`return {
    banner: !!document.querySelector('.demo-banner'),
    imgs: document.querySelectorAll('#viewer img').length,
    loaded: [...document.querySelectorAll('#viewer img')].every(i => i.complete && i.naturalWidth > 0),
    risk: document.querySelector('#riskLabel').textContent.trim(),
    ev: document.querySelectorAll('#evidence .ev').length,
  };`);
  check('演示横幅存在', s1 && s1.banner);
  check('证据图加载成功', s1 && s1.imgs > 0 && s1.loaded, `imgs=${s1?.imgs}`);
  check('风险等级已出', s1 && s1.risk !== '—', s1?.risk);

  for (const [scene, name] of [['comments', '评论区'], ['material', '素材']]) {
    await cdp.eval(`document.querySelector('#tabs button[data-scene="${scene}"]').click(); return 1;`);
    await sleep(2200);
    const s = await cdp.eval(`return {
      risk: document.querySelector('#riskLabel').textContent.trim(),
      ev: document.querySelectorAll('#evidence .ev').length,
      charts: document.querySelectorAll('#charts canvas').length,
    };`);
    check(`${name}场景能加载`, s && s.risk !== '—', `${s?.risk} / 证据 ${s?.ev}`);
  }

  // 问答
  await cdp.eval(`document.querySelector('#tabs button[data-scene="post"]').click(); return 1;`);
  await sleep(2500);
  const q = await cdp.eval(`
    const chip = document.querySelector('#askChips button');
    if (!chip) return null;
    chip.click();
    await new Promise(r => setTimeout(r, 1500));
    const msgs = [...document.querySelectorAll('#msgs .msg')].map(e => e.textContent);
    return msgs[msgs.length - 1] || '';
  `);
  check('预置问答能回答', !!(q && q.length > 10 && !/只预置了下方几个常用问题/.test(q)), (q || '').slice(0, 40));

  console.log(errors.length ? `\nJS 异常:\n  ${errors.join('\n  ')}` : '\nJS 异常: 无');
  ws.close(); proc.kill();
  process.exit(failed || errors.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
