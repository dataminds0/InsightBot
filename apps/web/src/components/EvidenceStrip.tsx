import { BookOpen, Calendar, Clock, ExternalLink, GitBranch, Hash, ShieldCheck, Timer } from "lucide-react";

interface EvidenceStripProps {
  sourceId: string;
  originalUrl?: string;
  publishedAt?: string | null;
  publicationDateUnknownReason?: string | null;
  fetchedAt: string;
  version: number;
  contentHash?: string;
  readingTimeMinutes?: number;
  wordCount?: number;
  fetchDurationSeconds?: number | null;
  className?: string;
}

export function EvidenceStrip({
  sourceId,
  originalUrl,
  publishedAt,
  publicationDateUnknownReason,
  fetchedAt,
  version,
  contentHash,
  readingTimeMinutes,
  wordCount,
  fetchDurationSeconds,
  className = "",
}: EvidenceStripProps) {
  const formatDate = (isoString?: string | null) => {
    if (!isoString) return null;
    try {
      const dt = new Date(isoString);
      return new Intl.DateTimeFormat("ar-EG", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(dt);
    } catch {
      return isoString;
    }
  };

  const formattedPublished = formatDate(publishedAt);
  const formattedFetched = formatDate(fetchedAt);

  return (
    <div
      className={`bg-canvas border border-border rounded-lg p-3 text-xs text-muted flex flex-wrap items-center gap-y-2 gap-x-4 ${className}`}
    >
      {/* Source */}
      <div className="flex items-center space-x-1.5 space-x-reverse">
        <ShieldCheck className="h-4 w-4 text-brand" />
        <span className="font-semibold text-text">المصدر:</span>
        <span className="bg-brand-light text-brand px-2 py-0.5 rounded font-mono">
          {sourceId}
        </span>
      </div>

      {/* Publication Date (Distinct from Fetch Date to prevent Defect A13) */}
      <div className="flex items-center space-x-1.5 space-x-reverse">
        <Calendar className="h-4 w-4 text-slate-500" />
        <span className="font-semibold text-text">تاريخ النشر:</span>
        {formattedPublished ? (
          <span className="text-text">{formattedPublished}</span>
        ) : (
          <span
            className="text-warning bg-amber-50 px-2 py-0.5 rounded border border-amber-200"
            title={publicationDateUnknownReason || "غير متوفر في بيانات التغذية والصفحة"}
          >
            غير محدد
          </span>
        )}
      </div>

      {/* Fetch Date */}
      <div className="flex items-center space-x-1.5 space-x-reverse">
        <Clock className="h-4 w-4 text-slate-500" />
        <span className="font-semibold text-text">تاريخ الجلب:</span>
        <span className="text-text">{formattedFetched}</span>
      </div>

      {/* Estimated Reading Time (Word-count based, resolving Defect A14) */}
      {readingTimeMinutes !== undefined && (
        <div className="flex items-center space-x-1.5 space-x-reverse">
          <BookOpen className="h-4 w-4 text-brand" />
          <span className="font-semibold text-text">وقت القراءة:</span>
          <span className="text-text font-medium">
            {readingTimeMinutes} {readingTimeMinutes === 1 ? "دقيقة" : "دقائق"}
            {wordCount ? ` (${wordCount} كلمة)` : ""}
          </span>
        </div>
      )}

      {/* Fetch Latency (Separate technical metric, NEVER confused with reading time) */}
      {fetchDurationSeconds !== undefined && fetchDurationSeconds !== null && (
        <div className="flex items-center space-x-1.5 space-x-reverse">
          <Timer className="h-3.5 w-3.5 text-slate-400" />
          <span className="text-muted">استجابة الجلب:</span>
          <span className="text-slate-600 font-mono">{fetchDurationSeconds} ث</span>
        </div>
      )}

      {/* Version */}
      <div className="flex items-center space-x-1.5 space-x-reverse">
        <GitBranch className="h-4 w-4 text-brand" />
        <span className="font-semibold text-text">النسخة:</span>
        <span className="bg-slate-200 text-slate-700 px-1.5 py-0.2 rounded font-mono font-medium">
          v{version}
        </span>
      </div>

      {/* Content Hash */}
      {contentHash && (
        <div className="flex items-center space-x-1.5 space-x-reverse font-mono text-[11px]" title={`SHA-256: ${contentHash}`}>
          <Hash className="h-3.5 w-3.5 text-slate-400" />
          <span className="text-slate-600">{contentHash.slice(0, 10)}...</span>
        </div>
      )}

      {/* Original Publisher Link */}
      {originalUrl && (
        <div className="flex items-center space-x-1 space-x-reverse mr-auto">
          <a
            href={originalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-1 space-x-reverse text-brand hover:underline font-medium"
          >
            <span>رابط الناشر</span>
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
      )}
    </div>
  );
}
