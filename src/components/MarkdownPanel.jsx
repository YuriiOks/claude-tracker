// Markdown viewer with a Code / HTML toggle.
//
// "Code" mode: raw .md text in a terminal-style block.
// "HTML" mode: parsed markdown rendered as HTML, with:
//   • Borderless frontmatter card with per-key icons & accent stripes (A1)
//   • Heading hierarchy: bars, prefix glyphs, hover-anchor (A2)
//   • Code-block chrome: language label + copy button (A3)
//   • GFM alerts ([!NOTE], [!WARNING], …) (B1)
//   • In-repo links route inside the SPA (B4)
//   • Pattern recognition: agent / skill / rule frontmatter shapes (C1)
//
// Source can be passed in (`source` prop) or fetched from the backend
// (`repoId` + `relPath` props → /api/files/:repo/:path).
import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { marked } from 'marked';
import hljs from 'highlight.js/lib/core';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import python from 'highlight.js/lib/languages/python';
import bash from 'highlight.js/lib/languages/bash';
import yaml from 'highlight.js/lib/languages/yaml';
import json from 'highlight.js/lib/languages/json';
import css from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';
import markdown from 'highlight.js/lib/languages/markdown';
import sql from 'highlight.js/lib/languages/sql';
import diff from 'highlight.js/lib/languages/diff';
import dockerfile from 'highlight.js/lib/languages/dockerfile';
import Icon from '../icons';
import { useFile } from '../api';
import { useRoute } from '../useRoute';

// ──────────────────────── highlight.js setup ────────────────────────
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('jsx', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('ts', typescript);
hljs.registerLanguage('tsx', typescript);
hljs.registerLanguage('python', python);
hljs.registerLanguage('py', python);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('sh', bash);
hljs.registerLanguage('shell', bash);
hljs.registerLanguage('zsh', bash);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('yml', yaml);
hljs.registerLanguage('json', json);
hljs.registerLanguage('css', css);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('md', markdown);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('diff', diff);
hljs.registerLanguage('dockerfile', dockerfile);
hljs.registerLanguage('docker', dockerfile);

marked.setOptions({ gfm: true, breaks: false, headerIds: false, mangle: false });
// Note: we deliberately do NOT register markedHighlight here. The custom
// renderer.code below is the sole highlighter — registering both makes the
// code get highlighted twice and the second pass treats the first pass's
// HTML as plain text → visible <span class="hljs-keyword"> escapes.

// ──────────────────────── marked extensions (A2/A3/B1) ────────────────────────

// Stable kebab-case slug for heading anchors (A2)
function slugify(text) {
  return String(text)
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 60);
}

// Alert kinds (B1) — mapped to icon + accent class
const ALERT_KINDS = {
  NOTE:      { icon: 'info',          accent: 'note',      label: 'Note' },
  TIP:       { icon: 'sparkles',      accent: 'tip',       label: 'Tip' },
  IMPORTANT: { icon: 'star',          accent: 'important', label: 'Important' },
  WARNING:   { icon: 'alertTriangle', accent: 'warning',   label: 'Warning' },
  CAUTION:   { icon: 'shieldX',       accent: 'caution',   label: 'Caution' },
};

// Custom marked renderer that:
//   • Wraps headings with anchor IDs + a hover ¶ link (A2)
//   • Wraps fenced code in a chrome div with language pill + copy (A3)
//   • Detects [!NOTE]/[!TIP]/etc. blockquotes and renders as callouts (B1)
//   • Marks in-repo links with a data-attr the click handler can intercept (B4)
function buildRenderer({ collectHeadings }) {
  const renderer = new marked.Renderer();

  renderer.heading = function ({ tokens, depth }) {
    const text = this.parser.parseInline(tokens);
    const plain = tokens.map(t => t.text || '').join('');
    const id = slugify(plain);
    if (collectHeadings) collectHeadings.push({ id, text: plain, level: depth });
    return `<h${depth} id="${id}" class="md-h md-h${depth}"><a href="#${id}" class="md-anchor" aria-label="anchor" tabindex="-1">¶</a><span class="md-h-text">${text}</span></h${depth}>\n`;
  };

  renderer.code = function ({ text, lang }) {
    // text is the raw code (markedHighlight is intentionally NOT registered).
    const langLabel = (lang || '').trim();
    let highlighted;
    try {
      const language = langLabel && hljs.getLanguage(langLabel) ? langLabel : 'plaintext';
      highlighted = hljs.highlight(text, { language, ignoreIllegals: true }).value;
    } catch {
      highlighted = text.replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
    }
    return `<div class="md-code-block">
<div class="md-code-bar">
  <span class="md-code-lang">${langLabel || 'text'}</span>
  <button class="md-code-copy" type="button" data-clipboard="${encodeURIComponent(text)}" title="Copy code" aria-label="Copy code"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>
</div>
<pre><code class="hljs language-${langLabel || 'plaintext'}">${highlighted}</code></pre>
</div>\n`;
  };

  renderer.blockquote = function ({ tokens }) {
    const inner = this.parser.parse(tokens);
    // Detect leading [!KIND] inside the first paragraph
    const m = inner.match(/^<p>\s*\[!([A-Z]+)\]\s*(.*)/s);
    if (m && ALERT_KINDS[m[1]]) {
      const kind = ALERT_KINDS[m[1]];
      // Reconstruct the body with the marker stripped from the first paragraph
      const rest = m[2];
      const bodyHtml = `<p>${rest}` + inner.slice(m[0].length);
      return `<div class="md-alert md-alert-${kind.accent}">
<div class="md-alert-head"><span class="md-alert-icon" aria-hidden="true"></span><span class="md-alert-label">${kind.label}</span></div>
<div class="md-alert-body">${bodyHtml}</div>
</div>\n`;
    }
    return `<blockquote>${inner}</blockquote>\n`;
  };

  renderer.link = function ({ href, title, tokens }) {
    const text = this.parser.parseInline(tokens);
    const titleAttr = title ? ` title="${title}"` : '';
    // External link → arrow icon (B4)
    if (/^https?:\/\//i.test(href)) {
      return `<a href="${href}"${titleAttr} class="md-link md-link-external" target="_blank" rel="noopener">${text}<span class="md-link-arrow" aria-hidden="true">↗</span></a>`;
    }
    // In-repo .md / .html link → handled by click delegate (B4)
    if (/\.(md|html?)(#.*)?$/i.test(href) && !href.startsWith('#')) {
      return `<a href="${href}"${titleAttr} class="md-link md-link-inrepo" data-inrepo="${href}">${text}</a>`;
    }
    return `<a href="${href}"${titleAttr} class="md-link">${text}</a>`;
  };

  return renderer;
}

// ──────────────────────── frontmatter helpers ────────────────────────

function fillTemplatePlaceholders(html) {
  if (!html || !html.includes('{{')) return html;
  const today = new Date().toISOString().slice(0, 10);
  const defaults = {
    DATE: today, TITLE: 'Sample title',
    SUBTITLE: 'One-sentence framing of the doc.',
    EYEBROW: 'Preview · sample data', TOPIC: 'sample topic',
    SOURCE: 'codebase + chat', FILENAME: 'lib/example.ts',
  };
  return html.replace(/\{\{\s*([^{}]+?)\s*\}\}/g, (_, body) => {
    const eg = body.match(/—\s*e\.g\.,?\s*"?([^"]+?)"?\s*$/);
    if (eg) return eg[1].trim();
    const key = body.split('—')[0].trim().toUpperCase();
    if (defaults[key]) return defaults[key];
    return '[' + body.split('—')[0].trim() + ']';
  });
}

function splitFrontmatter(content) {
  if (!content || !content.startsWith('---')) return { fm: null, body: content };
  const m = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return { fm: null, body: content };
  return { fm: parseSimpleYaml(m[1]), body: m[2] };
}

function parseSimpleYaml(text) {
  const out = {};
  const lines = text.split(/\r?\n/);
  let currentKey = null;
  for (const raw of lines) {
    const indented = /^\s+-\s+(.*)$/.exec(raw);
    if (indented && currentKey) {
      if (!Array.isArray(out[currentKey])) out[currentKey] = [];
      out[currentKey].push(indented[1].trim());
      continue;
    }
    const kv = /^([A-Za-z_][\w-]*)\s*:\s*(.*)$/.exec(raw);
    if (kv) {
      currentKey = kv[1];
      const v = kv[2].trim();
      out[currentKey] = v;
    }
  }
  return out;
}

// ──────────────────────── code-view highlighter ────────────────────────

function highlightMarkdown(text) {
  const lines = text.split('\n');
  let inFrontmatter = false;
  let inFence = false;
  return lines.map((line, idx) => {
    if (line.trim() === '---' && (idx === 0 || inFrontmatter)) {
      inFrontmatter = !inFrontmatter;
      return <div key={idx}><span className="cmt">{line || ' '}</span></div>;
    }
    const fence = line.match(/^(\s*)(```)(.*)$/);
    if (fence) {
      inFence = !inFence;
      return <div key={idx}>{fence[1]}<span className="cmt">{fence[2]}</span>{fence[3] && <span className="vr">{fence[3]}</span>}</div>;
    }
    if (inFence) return <div key={idx} className="md-fenced-line">{line || ' '}</div>;
    if (inFrontmatter) {
      const yaml = line.match(/^(\s*)([A-Za-z_][\w-]*)(:\s*)(.*)$/);
      if (yaml) {
        return <div key={idx}>{yaml[1]}<span className="kw">{yaml[2]}</span><span>{yaml[3]}</span><span className="str">{yaml[4]}</span></div>;
      }
      return <div key={idx}><span className="str">{line || ' '}</span></div>;
    }
    const heading = line.match(/^(\s*)(#{1,6}\s.*)$/);
    if (heading) {
      return <div key={idx}>{heading[1]}<span className="cmt" style={{ fontStyle: 'normal', fontWeight: 700 }}>{heading[2]}</span></div>;
    }
    const bullet = line.match(/^(\s*)([-*+]|\d+\.)(\s+)(.*)$/);
    if (bullet) {
      return <div key={idx}>{bullet[1]}<span className="fn">{bullet[2]}</span>{bullet[3]}{renderInline(bullet[4])}</div>;
    }
    if (line.trimStart().startsWith('>')) return <div key={idx}><span className="vr">{line}</span></div>;
    return <div key={idx}>{renderInline(line || ' ')}</div>;
  });
}

function renderInline(line) {
  const parts = [];
  let i = 0;
  const re = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\([^)\n]+\))/g;
  let m, key = 0;
  while ((m = re.exec(line)) !== null) {
    if (m.index > i) parts.push(line.slice(i, m.index));
    const tok = m[0];
    if (tok.startsWith('`')) parts.push(<span key={'k' + key++} className="fn">{tok}</span>);
    else if (tok.startsWith('**')) parts.push(<span key={'k' + key++} style={{ fontWeight: 700, color: 'var(--txt-bright)' }}>{tok}</span>);
    else if (tok.startsWith('*')) parts.push(<span key={'k' + key++} style={{ fontStyle: 'italic', color: 'var(--gold)' }}>{tok}</span>);
    else if (tok.startsWith('[')) parts.push(<span key={'k' + key++} className="vr">{tok}</span>);
    i = re.lastIndex;
  }
  if (i < line.length) parts.push(line.slice(i));
  return parts.length ? parts : line;
}

// ──────────────────────── frontmatter table (A1) ────────────────────────

const FM_KEY_META = {
  name:        { icon: 'bot',      stripe: 'cyan',   label: 'name' },
  description: { icon: 'file',     stripe: 'muted',  label: 'description' },
  role:        { icon: 'sparkles', stripe: 'green',  label: 'role' },
  tools:       { icon: 'layers',   stripe: 'cyan',   label: 'tools' },
  model:       { icon: 'cpu',      stripe: 'purple', label: 'model' },
  color:       { icon: 'eye',      stripe: 'gold',   label: 'color' },
  origin:      { icon: 'folder',   stripe: 'muted',  label: 'origin' },
  repo:        { icon: 'folder',   stripe: 'muted',  label: 'repo' },
  agent:       { icon: 'bot',      stripe: 'cyan',   label: 'agent' },
  skill:       { icon: 'sparkles', stripe: 'purple', label: 'skill' },
  globs:       { icon: 'zap',      stripe: 'gold',   label: 'globs' },
};

function FrontmatterCard({ data }) {
  const entries = Object.entries(data);
  return (
    <div className="md-fm">
      {entries.map(([k, v]) => {
        const meta = FM_KEY_META[k] || { icon: 'hash', stripe: 'muted', label: k };
        return (
          <div key={k} className={`md-fm-row md-fm-stripe-${meta.stripe}`}>
            <div className="md-fm-key">
              <span className="md-fm-icon"><Icon name={meta.icon} size={12} /></span>
              <span className="md-fm-key-label">{meta.label}</span>
            </div>
            <div className="md-fm-val">
              {Array.isArray(v) ? (
                <div className="md-fm-chips">
                  {v.map((it, i) => <span key={i} className="md-fm-chip">{String(it)}</span>)}
                </div>
              ) : k === 'color' ? (
                <span className="md-fm-color">
                  <span className="md-fm-color-swatch" style={{ background: String(v) }} />
                  <code>{String(v)}</code>
                </span>
              ) : k === 'model' ? (
                <span className="md-fm-pill">{String(v)}</span>
              ) : k === 'description' ? (
                <span className="md-fm-desc">{String(v)}</span>
              ) : (
                <span>{String(v)}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ──────────────────────── TOC (B2) ────────────────────────

function TableOfContents({ headings, scrollContainer }) {
  const [activeId, setActiveId] = useState(headings[0]?.id || '');
  // Persist collapsed state per-tab so it stays sane across navigations
  const [collapsed, setCollapsed] = useState(() => {
    try { return sessionStorage.getItem('ct:toc-collapsed') === '1'; } catch { return false; }
  });
  useEffect(() => {
    try { sessionStorage.setItem('ct:toc-collapsed', collapsed ? '1' : '0'); } catch { /* ignore */ }
  }, [collapsed]);
  useEffect(() => {
    if (!scrollContainer || headings.length === 0 || collapsed) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActiveId(visible.target.id);
      },
      { root: scrollContainer, rootMargin: '0px 0px -70% 0px', threshold: 0 }
    );
    headings.forEach(h => {
      const el = scrollContainer.querySelector('#' + CSS.escape(h.id));
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [headings, scrollContainer, collapsed]);
  if (headings.length < 4) return null;
  const min = Math.min(...headings.map(h => h.level));
  return (
    <nav className={'md-toc' + (collapsed ? ' collapsed' : '')} aria-label="Table of contents">
      <div className="md-toc-head">
        {!collapsed && <span className="md-toc-title">On this page</span>}
        <button
          className="md-toc-toggle"
          onClick={() => setCollapsed(c => !c)}
          title={collapsed ? 'Show table of contents' : 'Hide table of contents'}
          aria-label={collapsed ? 'Show table of contents' : 'Hide table of contents'}
        >
          <Icon name={collapsed ? 'list' : 'x'} size={11} />
        </button>
      </div>
      {!collapsed && (
        <div className="md-toc-body">
          <ul>
            {headings.map(h => (
              <li
                key={h.id}
                className={`md-toc-l${h.level - min} ${activeId === h.id ? 'active' : ''}`}
              >
                <a href={'#' + h.id}>{h.text}</a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </nav>
  );
}

// ──────────────────────── component ────────────────────────

const MarkdownPanel = ({
  source,
  repoId,
  relPath,
  filePath,
  defaultMode = 'html',
  emptyMessage = 'No content',
  hideSourceToggle = false,
}) => {
  const [mode, setMode] = useState(hideSourceToggle ? 'html' : defaultMode);
  const [, setRoute] = useRoute();
  const bodyRef = useRef(null);

  const { data: fetched, loading, error } = useFile(
    source == null ? repoId : null,
    source == null ? relPath : null,
  );
  const content = source != null ? source : (fetched?.content || '');
  const headerPath = filePath || fetched?.path || relPath || '';

  const isHtml = /\.html?$/i.test(headerPath || '') || /^<!doctype html|^<html\b/i.test((content || '').trimStart());
  const { fm, body } = useMemo(() => splitFrontmatter(content), [content]);

  // Parse markdown body, collecting headings on the side for TOC
  const { html, headings } = useMemo(() => {
    if (mode !== 'html' || !content || isHtml) return { html: '', headings: [] };
    const collected = [];
    const renderer = buildRenderer({ collectHeadings: collected });
    try {
      const out = marked.parse(body, { renderer });
      return { html: out, headings: collected };
    } catch (e) {
      return { html: `<pre>${String(e)}</pre>`, headings: [] };
    }
  }, [body, mode, isHtml, content]);

  // Click delegate: in-repo links route inside the SPA (B4)
  // Copy buttons on code blocks (A3) — use the same delegate.
  const handleBodyClick = useCallback((e) => {
    const copyBtn = e.target.closest('.md-code-copy');
    if (copyBtn) {
      e.preventDefault();
      const raw = decodeURIComponent(copyBtn.dataset.clipboard || '');
      navigator.clipboard?.writeText(raw).then(() => {
        copyBtn.classList.add('md-code-copied');
        setTimeout(() => copyBtn.classList.remove('md-code-copied'), 1500);
      }).catch(() => {});
      return;
    }
    const link = e.target.closest('a.md-link-inrepo');
    if (link && repoId) {
      const href = link.dataset.inrepo || link.getAttribute('href') || '';
      const route = inRepoLinkToRoute(href, repoId);
      if (route) {
        e.preventDefault();
        setRoute(route);
      }
    }
  }, [repoId, setRoute]);

  return (
    <div className="md-panel">
      <div className="md-panel-head">
        <Icon name="file" size={12} />
        <span className="mono md-panel-path">{headerPath}</span>
        {!hideSourceToggle && (
          <div className="md-panel-toggle">
            <button
              className={'md-toggle-btn' + (mode === 'code' ? ' active' : '')}
              onClick={() => setMode('code')}
              title={isHtml ? 'Show raw HTML source' : 'Show raw markdown source'}
            >
              <Icon name="terminal" size={11} />{isHtml ? 'Source' : 'Code'}
            </button>
            <button
              className={'md-toggle-btn' + (mode === 'html' ? ' active' : '')}
              onClick={() => setMode('html')}
              title={isHtml ? 'Render in sandboxed iframe' : 'Render markdown as HTML'}
            >
              <Icon name="eye" size={11} />{isHtml ? 'Preview' : 'HTML'}
            </button>
          </div>
        )}
        {isHtml && content && (
          <button
            className="md-toggle-btn md-open-tab"
            title="Open at full width in a new tab"
            onClick={() => {
              const blob = new Blob([fillTemplatePlaceholders(content)], { type: 'text/html' });
              const url = URL.createObjectURL(blob);
              window.open(url, '_blank', 'noopener');
              setTimeout(() => URL.revokeObjectURL(url), 60_000);
            }}
          >
            <Icon name="link" size={11} />Open
          </button>
        )}
      </div>

      <div className="md-panel-body" ref={bodyRef}>
        {loading && <div className="empty">Loading…</div>}
        {!loading && error && <div className="empty">Could not load file</div>}
        {!loading && !error && !content && <div className="empty">{emptyMessage}</div>}
        {!loading && !error && content && (
          mode === 'code'
            ? (isHtml
                ? <pre className="code md-panel-code md-panel-raw">{content}</pre>
                : <div className="code md-panel-code">{highlightMarkdown(content)}</div>)
            : (isHtml
                ? <iframe
                    title={headerPath || 'embedded html'}
                    className="md-panel-iframe md-panel-iframe-tall"
                    srcDoc={fillTemplatePlaceholders(content)}
                    sandbox="allow-same-origin allow-scripts"
                  />
                : (
                  <div className="md-panel-html-wrap">
                    <div className="md-panel-html" onClick={handleBodyClick}>
                      {fm && Object.keys(fm).length > 0 && <FrontmatterCard data={fm} />}
                      <div dangerouslySetInnerHTML={{ __html: html }} />
                    </div>
                    <TableOfContents headings={headings} scrollContainer={bodyRef.current} />
                  </div>
                )
              )
        )}
      </div>
    </div>
  );
};

// Map an in-repo .md link → route inside the SPA (B4)
//   .claude/agents/foo.md             → /repos/<id>/agents/foo
//   .claude/skills/foo/SKILL.md       → /repos/<id>/skills/foo
//   .claude/commands/foo.md           → /repos/<id>/commands/foo
//   .claude/rules/foo.md              → /repos/<id>/rules/foo
function inRepoLinkToRoute(href, repoId) {
  const cleaned = href.replace(/^\.\//, '').replace(/^\//, '');
  let m;
  if ((m = cleaned.match(/^\.claude\/agents\/([^/]+)\.md$/i)))
    return { page: 'agent', repoId, name: m[1], kind: 'agent' };
  if ((m = cleaned.match(/^\.claude\/skills\/([^/]+)\/SKILL\.md$/i)))
    return { page: 'agent', repoId, name: m[1], kind: 'skill' };
  if ((m = cleaned.match(/^\.claude\/commands\/([^/]+)\.md$/i)))
    return { page: 'agent', repoId, name: m[1], kind: 'command' };
  if ((m = cleaned.match(/^\.claude\/rules\/([^/]+)\.md$/i)))
    return { page: 'agent', repoId, name: m[1], kind: 'rule' };
  return null;
}

export default MarkdownPanel;
