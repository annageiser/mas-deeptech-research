// Minimal, dependency-free markdown renderer for the generated reports.
// Handles: # / ## / ### headings, **bold**, *italic*, [text](url), `code`,
// "- " bullets, "---" rules, blank-line paragraphs. The reports only use these.

import React from "react";

function inline(text: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let rest = text;
  let k = 0;
  const pattern = /(\*\*([^*]+)\*\*)|(\*([^*]+)\*)|(`([^`]+)`)|(\[([^\]]+)\]\(([^)]+)\))/;
  while (rest.length) {
    const m = rest.match(pattern);
    if (!m || m.index === undefined) {
      out.push(rest);
      break;
    }
    if (m.index > 0) out.push(rest.slice(0, m.index));
    if (m[1]) out.push(<strong key={`${keyBase}-${k++}`}>{m[2]}</strong>);
    else if (m[3]) out.push(<em key={`${keyBase}-${k++}`}>{m[4]}</em>);
    else if (m[5]) out.push(<code key={`${keyBase}-${k++}`}>{m[6]}</code>);
    else if (m[7]) out.push(<a key={`${keyBase}-${k++}`} href={m[9]} target="_blank" rel="noreferrer">{m[8]}</a>);
    rest = rest.slice(m.index + m[0].length);
  }
  return out;
}

export default function Markdown({ source }: { source: string }) {
  const lines = source.replace(/<!--[\s\S]*?-->/g, "").split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) {
      blocks.push(<p key={`p${blocks.length}`}>{inline(para.join(" "), `p${blocks.length}`)}</p>);
      para = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push(
        <ul key={`u${blocks.length}`}>
          {list.map((li, i) => (
            <li key={i}>{inline(li, `u${blocks.length}-${i}`)}</li>
          ))}
        </ul>
      );
      list = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^###\s+/.test(line)) { flushPara(); flushList(); blocks.push(<h3 key={blocks.length}>{inline(line.replace(/^###\s+/, ""), `h${blocks.length}`)}</h3>); }
    else if (/^##\s+/.test(line)) { flushPara(); flushList(); blocks.push(<h2 key={blocks.length}>{inline(line.replace(/^##\s+/, ""), `h${blocks.length}`)}</h2>); }
    else if (/^#\s+/.test(line)) { flushPara(); flushList(); blocks.push(<h1 key={blocks.length}>{inline(line.replace(/^#\s+/, ""), `h${blocks.length}`)}</h1>); }
    else if (/^---+$/.test(line)) { flushPara(); flushList(); blocks.push(<hr key={blocks.length} />); }
    else if (/^[-*]\s+/.test(line)) { flushPara(); list.push(line.replace(/^[-*]\s+/, "")); }
    else if (line.trim() === "") { flushPara(); flushList(); }
    else para.push(line);
  }
  flushPara();
  flushList();
  return <div className="md">{blocks}</div>;
}
