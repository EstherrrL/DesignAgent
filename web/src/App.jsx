import React, { useState, useEffect, useRef } from 'react';

// 注入一次旋转动画的 CSS（避免引入额外样式文件）
const SPINNER_STYLE_ID = 'multiagent-spinner-style';
function ensureSpinnerStyle() {
  if (document.getElementById(SPINNER_STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = SPINNER_STYLE_ID;
  style.innerHTML = `
    @keyframes ma-spin { to { transform: rotate(360deg); } }
    .ma-spinner {
      display: inline-block;
      width: 20px;
      height: 20px;
      border: 3px solid #d0d7de;
      border-top-color: #2563eb;
      border-radius: 50%;
      animation: ma-spin 0.8s linear infinite;
      vertical-align: middle;
      margin-right: 10px;
    }
    @keyframes ma-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    .ma-pulse-dot { animation: ma-pulse 1.4s ease-in-out infinite; }
  `;
  document.head.appendChild(style);
}

function LoadingPanel({ seconds }) {
  ensureSpinnerStyle();
  const stage = seconds < 15
    ? '正在拆解需求（Planner）…'
    : seconds < 40
    ? '正在设计与生成代码（Designer / Coder）…'
    : seconds < 70
    ? '正在审查代码（Reviewer）…'
    : '正在汇总与测试（Assembler / Tester）…';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '16px 20px',
        background: '#f0f4ff',
        border: '1px solid #c7d7fe',
        borderRadius: 8,
      }}
    >
      <span className="ma-spinner" />
      <div>
        <div style={{ fontWeight: 600 }}>
          正在生成中，请稍候
          <span className="ma-pulse-dot">…</span>
        </div>
        <div style={{ fontSize: 13, color: '#555', marginTop: 4 }}>
          {stage}（已耗时 {seconds}s，真实调用大模型，通常需要 30–100 秒）
        </div>
      </div>
    </div>
  );
}

function FileList({ files }) {
  if (!files) return null;
  return (
    <div>
      <h4>生成文件</h4>
      <ul>
        {Object.entries(files).map(([name, content]) => (
          <li key={name} style={{ marginBottom: 8 }}>
            <strong>{name}</strong>
            <div>
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(content)}`}
                download={name}
              >
                下载
              </a>
            </div>
            <pre style={{ background: '#f6f8fa', padding: 8, whiteSpace: 'pre-wrap' }}>{content}</pre>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function App() {
  const [input, setInput] = useState('生成一个加法函数的 Python 文件');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => {
    if (loading) {
      setElapsed(0);
      timerRef.current = setInterval(() => {
        setElapsed(prev => prev + 1);
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [loading]);

  const handleSubmit = async (e) => {
    e && e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input })
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || '后端返回错误');
      setResult(data.result);
    } catch (err) {
      setResult({ error: err.message });
    }
    setLoading(false);
  };

  return (
    <div style={{ maxWidth: 900, margin: '24px auto', fontFamily: 'Inter, Roboto, sans-serif' }}>
      <h1>多Agent 代码生成（Demo）</h1>

      <form onSubmit={handleSubmit} style={{ marginBottom: 20 }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          rows={4}
          style={{ width: '100%', fontSize: 15 }}
        />
        <div style={{ marginTop: 8 }}>
          <button type="submit" disabled={loading} style={{ fontSize: 15 }}>
            {loading ? `处理中... (${elapsed}s)` : '提交'}
          </button>
          <button type="button" disabled={loading} onClick={() => { setInput('生成一个加法函数的 Python 文件'); }} style={{ marginLeft: 8 }}>
            示例填充
          </button>
        </div>
      </form>

      <div>
        <h2>结果</h2>
        {loading && <LoadingPanel seconds={elapsed} />}
        {!loading && !result && <div style={{ color: '#666' }}>尚未生成结果</div>}
        {!loading && result && result.error && (
          <div style={{ background: '#fff5f5', border: '1px solid #ffc9c9', borderRadius: 8, padding: 16 }}>
            <div style={{ color: '#c92a2a', fontWeight: 600 }}>错误: {result.error}</div>
            {/(Connection|connect|timeout|Timeout)/i.test(result.error) && (
              <div style={{ marginTop: 8, fontSize: 13, color: '#555' }}>
                这通常是与大模型服务的网络连接偶发抖动导致，后端已自动重试一次仍失败。请点击下方按钮重新提交。
              </div>
            )}
            <button type="button" onClick={handleSubmit} style={{ marginTop: 10, fontSize: 14 }}>
              重试
            </button>
          </div>
        )}

        {!loading && result && !result.error && (
          <div>
            {result.design_doc && (
              <section style={{ marginBottom: 12 }}>
                <h3>设计文档</h3>
                <pre style={{ background: '#f6f8fa', padding: 12, whiteSpace: 'pre-wrap' }}>{result.design_doc}</pre>
              </section>
            )}

            <FileList files={result.files} />

            {result.review && (
              <section>
                <h3>审查</h3>
                <div>评分: {result.review.score ?? 'N/A'}</div>
                <div>评论: {result.review.comments ?? ''}</div>
              </section>
            )}

            {result.test_result && (
              <section style={{ marginTop: 12 }}>
                <h3>测试结果</h3>
                <div>是否通过: {String(result.test_result.passed)}</div>
                {result.test_result.output && (
                  <pre style={{ background: '#f6f8fa', padding: 8, whiteSpace: 'pre-wrap' }}>{result.test_result.output}</pre>
                )}
                {Array.isArray(result.test_result.errors) && result.test_result.errors.length > 0 && (
                  <div style={{ color: 'red' }}>
                    {result.test_result.errors.map((e, i) => <div key={i}>{e}</div>)}
                  </div>
                )}
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
