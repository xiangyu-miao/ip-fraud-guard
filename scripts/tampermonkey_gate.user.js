// ==UserScript==
// @name         IPGuard 访问门控
// @namespace    ipguard.local
// @version      0.1.0
// @description  本机外网 IP 欺诈分超过阈值时，拦截敏感网站访问（需本机运行 IPGuard 且开启门控服务）
// @match        https://claude.ai/*
// @match        https://*.claude.ai/*
// @match        https://chatgpt.com/*
// @match        https://*.openai.com/*
// @connect      127.0.0.1
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// ==/UserScript==
//
// Usage:
// 1. Install in Tampermonkey and add/remove @match domains as needed.
// 2. GATE_PORT must match gate_server.port in the IPGuard config.json.
// 3. This is a SOFT gate: the browser request has already been sent; the
//    script only blocks page rendering. Request-level hard blocking needs a
//    local proxy filter (see the project README).
// 4. When the gate service is down, requests are allowed by default
//    (FAIL_OPEN); set it to false for fail-closed behavior.

(function () {
  'use strict';

  const GATE_PORT = 17654;   // keep in sync with config.json
  const TOKEN = '';          // fill in if gate_server.token is configured
  const FAIL_OPEN = true;    // service unavailable: true=allow, false=block

  if (sessionStorage.getItem('ipguard-bypass') === '1') return;

  let url = `http://127.0.0.1:${GATE_PORT}/status`;
  if (TOKEN) url += `?token=${encodeURIComponent(TOKEN)}`;

  GM_xmlhttpRequest({
    method: 'GET',
    url: url,
    timeout: 4000,
    onload(res) {
      let st = null;
      try { st = JSON.parse(res.responseText); } catch (e) { /* ignore */ }
      if (st && st.ok && st.allowed === false && sessionStorage.getItem('ipguard-bypass') !== '1') {
        try { window.stop(); } catch (e) { /* ignore */ }
        renderWarning(st);
      }
    },
    onerror() { if (!FAIL_OPEN) renderWarning(null); }
  });

  function renderWarning(st) {
    const score = st && st.score != null ? st.score : '未知';
    const ip = (st && st.ip) || '未知';
    const threshold = (st && st.threshold) || 20;
    const risk = (st && st.risk_label) || '';
    document.documentElement.innerHTML =
      '<!DOCTYPE html><html><head><meta charset="utf-8"><title>⛔ IPGuard 已拦截</title><style>' +
      'body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;' +
      'background:#141419;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#E8E8EC}' +
      '.card{max-width:420px;padding:32px;border-radius:16px;background:#1C1C24;' +
      'border:1px solid #FF5B5B;text-align:center}' +
      'h1{font-size:20px;margin:0 0 12px}.row{font-size:14px;color:#9A9AA5;margin:6px 0}' +
      'b{color:#FF6B6B;font-weight:700}' +
      '.btn{display:inline-block;margin:18px 8px 0;padding:9px 18px;border-radius:8px;' +
      'font-size:14px;cursor:pointer;border:none}' +
      '.btn.danger{background:#FF5B5B;color:#fff}.btn.plain{background:rgba(255,255,255,.12);color:#E8E8EC}' +
      '</style></head><body><div class="card">' +
      '<h1>⛔ IPGuard 已拦截本页面</h1>' +
      '<div class="row">当前 IP：<b>' + ip + '</b></div>' +
      '<div class="row">欺诈分：<b>' + score + '</b>（阈值 ' + threshold + (risk ? '，' + risk : '') + '）</div>' +
      '<div class="row">该 IP 风险过高，请切换代理节点后再访问敏感网站</div>' +
      '<button class="btn danger" id="ipguard-refresh">刷新状态</button>' +
      '<button class="btn plain" id="ipguard-bypass">我已知晓风险，仍然继续</button>' +
      '</div></body></html>';
    document.getElementById('ipguard-bypass').addEventListener('click', function () {
      sessionStorage.setItem('ipguard-bypass', '1');
      location.reload();
    });
    document.getElementById('ipguard-refresh').addEventListener('click', function () {
      location.reload();
    });
  }
})();
