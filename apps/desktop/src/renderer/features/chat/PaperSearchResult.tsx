/**
 * Paper search result card rendered inline in chat.
 *
 * Detects paper_search tool output and renders formatted cards with
 * title, authors, year, abstract, citation count, source badge,
 * and a one-click PDF download button.
 */
import { useState, useCallback } from 'react';
import {
  Download,
  FileText,
  Calendar,
  Users,
  Quote,
  ExternalLink,
  Loader2,
  CheckCircle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

/* ─── Types ─────────────────────────────────────────────────── */

export interface PaperItem {
  id: string;
  title: string;
  abstract: string;
  authors: string[];
  year: number | null;
  venue?: string;
  doi?: string;
  arxiv_id?: string;
  citation_count?: number | null;
  reference_count?: number | null;
  is_open_access?: boolean;
  open_access_pdf_url?: string;
  source?: string;
  source_url?: string;
}

export interface PaperSearchPayload {
  query?: string;
  source?: string;
  total?: number;
  count?: number;
  items?: PaperItem[];
  error?: string;
}

/* ─── Helpers ────────────────────────────────────────────────── */

const SOURCE_LABELS: Record<string, string> = {
  semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv',
  core: 'CORE',
  hybrid: 'Multi-source',
};

function fmtAuthors(authors: string[], max = 4): string {
  if (!authors.length) return '未知';
  const shown = authors.slice(0, max);
  const suffix = authors.length > max ? ` et al. (${authors.length})` : '';
  return shown.join(', ') + suffix;
}

function fmtCitations(n: number | null | undefined): string {
  if (n == null) return '-';
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

/** Try to parse a tool result text as a paper_search JSON payload. */
export function tryParsePaperSearchResult(text: string): PaperSearchPayload | null {
  try {
    const obj = JSON.parse(text);
    if (obj && typeof obj === 'object' && Array.isArray(obj.items)) {
      return obj as PaperSearchPayload;
    }
    return null;
  } catch {
    return null;
  }
}

/* ─── Single Paper Card ──────────────────────────────────────── */

function PaperCard({
  paper,
  onDownload,
  isDownloading,
}: {
  paper: PaperItem;
  onDownload: (paper: PaperItem) => void;
  isDownloading: boolean;
}) {
  const [showAbstract, setShowAbstract] = useState(false);
  const hasAbstract = paper.abstract?.trim().length > 10;
  const sourceLabel = SOURCE_LABELS[paper.source ?? ''] || paper.source || '未知';
  const hasPdf = !!(paper.open_access_pdf_url || paper.is_open_access);

  return (
    <div
      className="my-2 rounded-xl border overflow-hidden"
      style={{
        borderColor: 'var(--border)',
        background: 'var(--card-bg, var(--bg-secondary))',
      }}
    >
      {/* ── Header ────────────────────────────────────────── */}
      <div className="px-4 pt-3 pb-1">
        <div className="flex items-start justify-between gap-3">
          <h4
            className="text-sm font-semibold leading-snug flex-1"
            style={{ color: 'var(--text-primary)' }}
          >
            <FileText
              size={14}
              className="inline mr-1.5 shrink-0"
              style={{ color: 'var(--text-muted)' }}
            />
            {paper.title || '无标题'}
          </h4>
          {paper.year && (
            <span
              className="text-xs shrink-0 px-1.5 py-0.5 rounded font-mono"
              style={{
                background: 'var(--tag-bg, var(--bg-tertiary))',
                color: 'var(--tag-text, var(--text-muted))',
              }}
            >
              {paper.year}
            </span>
          )}
        </div>

        {/* Authors + citation count */}
        <div
          className="flex items-center gap-3 mt-1 flex-wrap text-xs"
          style={{ color: 'var(--text-muted)' }}
        >
          <span className="inline-flex items-center gap-1">
            <Users size={11} />
            {fmtAuthors(paper.authors)}
          </span>
          {paper.citation_count != null && (
            <span className="inline-flex items-center gap-1">
              <Quote size={11} />
              {fmtCitations(paper.citation_count)} cites
            </span>
          )}
          {paper.venue && (
            <span className="inline-flex items-center gap-1">
              <Calendar size={11} />
              {paper.venue}
            </span>
          )}
        </div>
      </div>

      {/* ── Abstract (collapsible) ────────────────────────── */}
      {hasAbstract && (
        <div className="px-4 pb-1">
          <button
            onClick={() => setShowAbstract((v) => !v)}
            className="inline-flex items-center gap-1 text-xs mt-1 hover:underline"
            style={{ color: 'var(--text-muted)' }}
          >
            {showAbstract ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {showAbstract ? 'Hide abstract' : 'Show abstract'}
          </button>
          {showAbstract && (
            <p
              className="text-xs mt-1 leading-relaxed whitespace-pre-wrap"
              style={{ color: 'var(--text-secondary)' }}
            >
              {paper.abstract}
            </p>
          )}
        </div>
      )}

      {/* ── Footer: actions ───────────────────────────────── */}
      <div
        className="flex items-center gap-2 px-4 py-2"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {/* Source badge */}
        <span
          className="text-[10px] px-1.5 py-0.5 rounded-full"
          style={{
            background: 'var(--tag-bg, var(--bg-tertiary))',
            color: 'var(--tag-text, var(--text-faint))',
          }}
        >
          {sourceLabel}
        </span>

        {paper.source_url && (
          <a
            href={paper.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[10px] hover:underline"
            style={{ color: 'var(--text-muted)' }}
          >
            <ExternalLink size={10} />
            Source
          </a>
        )}

        <div className="flex-1" />

        {/* Download PDF button */}
        {hasPdf && (
          <button
            onClick={() => onDownload(paper)}
            disabled={isDownloading}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all"
            style={{
              background: isDownloading ? 'var(--bg-tertiary)' : 'var(--accent, #3b82f6)',
              color: isDownloading ? 'var(--text-muted)' : '#fff',
              cursor: isDownloading ? 'not-allowed' : 'pointer',
            }}
          >
            {isDownloading ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Download size={12} />
            )}
            {isDownloading ? '下载中…' : '下载 PDF'}
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── Results Container ──────────────────────────────────────── */

export default function PaperSearchResult({
  data,
  onDownloadPaper,
  downloadingId,
}: {
  data: PaperSearchPayload;
  onDownloadPaper: (paper: PaperItem) => void;
  downloadingId: string | null;
}) {
  const items = data.items ?? [];

  if (data.error) {
    return (
      <div
        className="my-2 p-3 rounded-lg text-xs"
        style={{
          background: 'var(--danger-bg)',
          color: 'var(--danger)',
          border: '1px solid var(--danger)',
        }}
      >
        Paper search failed: {data.error}
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="my-2 text-xs" style={{ color: 'var(--text-muted)' }}>
        No papers found{data.query ? ` for "${data.query}"` : ''}.
      </div>
    );
  }

  return (
    <div className="my-1">
      {/* Search meta */}
      <div
        className="flex items-center gap-2 mb-2 text-[11px]"
        style={{ color: 'var(--text-muted)' }}
      >
        <span>{data.query ? `Results for "${data.query}"` : '搜索结果'}</span>
        {data.total != null && (
          <span style={{ color: 'var(--text-faint)' }}>
            · {data.total} found · showing {items.length}
          </span>
        )}
        {data.source && (
          <span
            className="px-1 py-0.5 rounded text-[10px]"
            style={{
              background: 'var(--tag-bg, var(--bg-tertiary))',
              color: 'var(--tag-text, var(--text-faint))',
            }}
          >
            via {SOURCE_LABELS[data.source] || data.source}
          </span>
        )}
      </div>

      {/* Paper cards */}
      {items.map((paper, idx) => (
        <PaperCard
          key={paper.id || idx}
          paper={paper}
          onDownload={onDownloadPaper}
          isDownloading={downloadingId === paper.id}
        />
      ))}
    </div>
  );
}
