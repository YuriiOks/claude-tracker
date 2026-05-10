import { useRef, useState, useEffect } from 'react';

export const eventToLine = (e) => {
  const time = new Date(Date.now() + e.t * 1000).toTimeString().slice(0, 8);
  let body;
  switch (e.kind) {
    case 'agent_start':
      body = <><span className="k-agent">▸ agent</span> <span className="k-target">{e.agent}</span> <span className="k-arrow">→</span> {e.msg}</>;
      break;
    case 'tool':
      body = <><span className="k-tool">⌘ {e.tool}</span> <span className="k-target">{e.target}</span></>;
      break;
    case 'delegate':
      body = <><span className="k-agent">{e.from}</span> <span className="k-arrow">↳ delegates →</span> <span className="k-agent-to">{e.to}</span> <span className="k-target">· {e.msg}</span></>;
      break;
    case 'skill':
      body = <><span className="k-skill">✦ skill</span> <span className="k-target">{e.skill}</span> <span className="k-arrow">·</span> {e.msg}</>;
      break;
    case 'command':
      body = <><span className="k-cmd">$ {e.cmd}</span> <span className="k-target">{e.msg}</span></>;
      break;
    case 'permission':
      body = e.granted
        ? <><span className="k-perm-ok">✓ allow</span> <span className="k-target">{e.action}</span></>
        : <><span className="k-perm-no">✗ deny</span> <span className="k-target">{e.action}</span></>;
      break;
    default:
      body = <span className="k-target">{JSON.stringify(e)}</span>;
  }
  return { time, repo: e.repo, body };
};

const LiveTerminal = ({ events, height = 360, showCursor = true, paused = false, hideHeader = false }) => {
  const bodyRef = useRef(null);
  const [frozen, setFrozen] = useState(events);
  useEffect(() => {
    if (!paused) setFrozen(events);
  }, [events, paused]);
  const list = paused ? frozen : events;
  useEffect(() => {
    if (bodyRef.current && !paused) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [list, paused]);

  return (
    <div className={'term' + (paused ? ' is-paused' : '') + (hideHeader ? ' no-header' : '')} style={{ height }}>
      {!hideHeader && (
        <div className="term-header">
          <div className="term-dots"><span className="r"/><span className="y"/><span className="g"/></div>
          <span className="term-title-1">claude-code</span>
          <span className="term-title-sep">—</span>
          <span className="term-title-2">live activity feed</span>
          <span className="term-counter">{paused ? '⏸ paused' : `● tracking ${list.length} events`}</span>
        </div>
      )}
      <div className="term-body" ref={bodyRef}>
        {list.map((e, i) => {
          const line = eventToLine(e);
          const key = (e.id != null) ? e.id : `${e.kind}-${e.t}-${e.repo || ''}-${e.agent || e.tool || e.skill || e.cmd || e.action || i}`;
          return (
            <div key={key} className="term-line">
              <span className="term-time">{line.time}</span>
              <span className="term-repo">{line.repo}</span>
              <span className="term-msg">
                {line.body}
                {showCursor && !paused && i === list.length - 1 && <span className="term-cursor"></span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default LiveTerminal;
