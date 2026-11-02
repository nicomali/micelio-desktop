import React from 'react';
import { AlertTriangle, CheckCircle2, Info, Lightbulb, ShieldAlert } from 'lucide-react';

interface Props {
  content: string;
}

const ALERT_STYLES: Record<
  string,
  { border: string; bg: string; titleColor: string; label: string; icon: React.ReactNode }
> = {
  NOTE: {
    border: 'border-blue-500/30',
    bg: 'bg-blue-500/[0.05]',
    titleColor: 'text-blue-400',
    label: 'Nota',
    icon: <Info className="w-3.5 h-3.5 text-blue-400" />,
  },
  TIP: {
    border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/[0.05]',
    titleColor: 'text-emerald-400',
    label: 'Tip',
    icon: <Lightbulb className="w-3.5 h-3.5 text-emerald-400" />,
  },
  IMPORTANT: {
    border: 'border-[#EC0000]/40',
    bg: 'bg-[#EC0000]/[0.05]',
    titleColor: 'text-[#FF4D4D]',
    label: 'Importante',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-[#FF4D4D]" />,
  },
  WARNING: {
    border: 'border-amber-500/30',
    bg: 'bg-amber-500/[0.05]',
    titleColor: 'text-amber-400',
    label: 'Advertencia',
    icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />,
  },
  CAUTION: {
    border: 'border-red-500/40',
    bg: 'bg-red-500/[0.06]',
    titleColor: 'text-red-400',
    label: 'Precaución',
    icon: <ShieldAlert className="w-3.5 h-3.5 text-red-400" />,
  },
};

export const RichMarkdown: React.FC<Props> = ({ content }) => {
  if (!content) return null;

  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-3 text-[13.5px] leading-[1.65] text-zinc-200">
      {parts.map((part, idx) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const firstNewline = part.indexOf('\n');
          const lang = firstNewline > 3 ? part.slice(3, firstNewline).trim() : '';
          const body = firstNewline > -1 ? part.slice(firstNewline + 1, -3) : part.slice(3, -3);

          if (lang === 'mermaid') {
            return (
              <div
                key={idx}
                className="rounded-xl border border-white/[0.07] bg-[#0D0D10] p-4 my-3 shadow-inner"
              >
                <div className="flex items-center justify-between text-[11px] font-mono text-zinc-500 mb-2 pb-2 border-b border-white/[0.05]">
                  <span className="text-zinc-300 font-medium">Diagrama de Arquitectura (Mermaid)</span>
                  <span>Flow / Sequence</span>
                </div>
                <pre className="text-xs font-mono text-zinc-300 overflow-x-auto whitespace-pre leading-relaxed">
                  {body.trim()}
                </pre>
              </div>
            );
          }

          return (
            <div
              key={idx}
              className="rounded-xl border border-white/[0.07] bg-[#0C0C0E] overflow-hidden my-3"
            >
              {lang && (
                <div className="px-3.5 py-1.5 bg-white/[0.02] border-b border-white/[0.05] text-[11px] font-mono text-zinc-400 flex items-center justify-between">
                  <span>{lang}</span>
                </div>
              )}
              <pre className="p-3.5 text-[12px] font-mono text-zinc-200 overflow-x-auto leading-relaxed">
                <code>{body.trim()}</code>
              </pre>
            </div>
          );
        }

        const lines = part.split('\n');
        const elements: React.ReactNode[] = [];
        let i = 0;

        while (i < lines.length) {
          const line = lines[i];
          const alertMatch = line.match(/^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)/i);
          if (alertMatch) {
            const kind = alertMatch[1].toUpperCase();
            const firstLineText = alertMatch[2];
            const alertLines: string[] = firstLineText ? [firstLineText] : [];
            i++;
            while (i < lines.length && lines[i].startsWith('>')) {
              alertLines.push(lines[i].replace(/^>\s?/, ''));
              i++;
            }
            const style = ALERT_STYLES[kind] || ALERT_STYLES.NOTE;
            elements.push(
              <div
                key={`alert-${idx}-${i}`}
                className={`rounded-xl border ${style.border} ${style.bg} px-4 py-3 my-2.5`}
              >
                <div className={`flex items-center gap-2 font-medium text-xs mb-1 ${style.titleColor}`}>
                  {style.icon}
                  <span>{style.label}</span>
                </div>
                <div className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed">
                  {alertLines.join('\n')}
                </div>
              </div>
            );
            continue;
          }

          if (line.startsWith('# ')) {
            elements.push(
              <h1
                key={`h1-${idx}-${i}`}
                className="text-base font-semibold text-white tracking-tight mt-5 mb-2 pb-1.5 border-b border-white/[0.07]"
              >
                {line.slice(2)}
              </h1>
            );
          } else if (line.startsWith('## ')) {
            elements.push(
              <h2
                key={`h2-${idx}-${i}`}
                className="text-sm font-semibold text-zinc-100 tracking-tight mt-4 mb-1.5"
              >
                {line.slice(3)}
              </h2>
            );
          } else if (line.startsWith('### ')) {
            elements.push(
              <h3 key={`h3-${idx}-${i}`} className="text-[13px] font-semibold text-zinc-200 mt-3 mb-1">
                {line.slice(4)}
              </h3>
            );
          } else if (line.match(/^\s*-\s+\[(x| )\]\s+/i)) {
            const checked = line.toLowerCase().includes('[x]');
            const label = line.replace(/^\s*-\s+\[(x| )\]\s+/i, '');
            elements.push(
              <div key={`chk-${idx}-${i}`} className="flex items-start gap-2.5 text-[13px] py-0.5">
                <span
                  className={`mt-1 w-3.5 h-3.5 rounded flex items-center justify-center border text-[10px] ${
                    checked
                      ? 'bg-[#EC0000] border-[#EC0000] text-white'
                      : 'border-zinc-600 bg-zinc-900'
                  }`}
                >
                  {checked ? '✓' : ''}
                </span>
                <span className={checked ? 'line-through text-zinc-500' : 'text-zinc-200'}>
                  {renderInlineFormatting(label)}
                </span>
              </div>
            );
          } else if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
            elements.push(
              <div key={`li-${idx}-${i}`} className="flex items-start gap-2.5 pl-1 text-[13.5px]">
                <span className="text-zinc-500 select-none">•</span>
                <span className="flex-1 text-zinc-200">
                  {renderInlineFormatting(line.trim().slice(2))}
                </span>
              </div>
            );
          } else if (line.trim() === '---') {
            elements.push(<hr key={`hr-${idx}-${i}`} className="border-white/[0.06] my-4" />);
          } else if (line.trim() !== '') {
            elements.push(
              <p key={`p-${idx}-${i}`} className="text-zinc-200">
                {renderInlineFormatting(line)}
              </p>
            );
          }
          i++;
        }

        return <React.Fragment key={idx}>{elements}</React.Fragment>;
      })}
    </div>
  );
};

function renderInlineFormatting(text: string): React.ReactNode {
  // Match bold (**...**), inline code (`...`), or markdown links ([...](...)) cleanly
  const regex = /(\*\*[^*]+?\*\*|`[^`]+?`|\[[^\]]+?\]\([^)]+?\))/g;
  const parts = text.split(regex);

  return parts.map((tok, i) => {
    if (!tok) return null;
    if (tok.startsWith('**') && tok.endsWith('**') && tok.length > 4) {
      return (
        <strong key={i} className="font-semibold text-white">
          {renderInlineFormatting(tok.slice(2, -2))}
        </strong>
      );
    }
    if (tok.startsWith('`') && tok.endsWith('`') && tok.length > 2) {
      return (
        <code
          key={i}
          className="px-1.5 py-0.5 rounded-md bg-white/[0.06] border border-white/[0.08] text-zinc-200 font-mono text-[12px]"
        >
          {tok.slice(1, -1)}
        </code>
      );
    }
    const linkMatch = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      return (
        <a
          key={i}
          href={linkMatch[2]}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded bg-[#EC0000]/10 text-[#FF5555] hover:bg-[#EC0000]/20 font-mono text-[12px] transition"
        >
          {linkMatch[1]}
        </a>
      );
    }
    return tok;
  });
}
