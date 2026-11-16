import type { ArticleListItem } from "../types/api";
import { BookOpen, Calendar, ChevronLeft, Globe, Shield } from "lucide-react";

interface ArticleCardProps {
  article: ArticleListItem;
  onSelect: (articleId: string) => void;
}

export function ArticleCard({ article, onSelect }: ArticleCardProps) {
  const formatDate = (isoString?: string | null) => {
    if (!isoString) return null;
    try {
      const dt = new Date(isoString);
      return new Intl.DateTimeFormat("ar-EG", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(dt);
    } catch {
      return isoString;
    }
  };

  const getLanguageLabel = (lang: string) => {
    switch (lang.toLowerCase()) {
      case "ar":
        return "العربية";
      case "en":
        return "English";
      case "ru":
        return "Русский";
      default:
        return lang.toUpperCase();
    }
  };

  const isRtl = article.language.toLowerCase() === "ar";
  const readingTime = article.reading_time_minutes || 1;
  const wordCount = article.word_count || 0;

  return (
    <article
      onClick={() => onSelect(article.article_id)}
      className="bg-surface border border-border rounded-xl p-5 shadow-sm hover:shadow-md hover:border-brand transition-all cursor-pointer group flex flex-col justify-between"
    >
      <div>
        {/* Top Meta Bar */}
        <div className="flex items-center justify-between text-xs text-muted mb-3">
          <div className="flex items-center space-x-2 space-x-reverse">
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-brand-light text-brand">
              <Shield className="h-3 w-3 ml-1" />
              {article.source_id}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-slate-100 text-slate-700">
              <Globe className="h-3 w-3 ml-1 text-slate-400" />
              {getLanguageLabel(article.language)}
            </span>
          </div>

          <div className="flex items-center space-x-2 space-x-reverse">
            {article.current_version > 1 && (
              <span className="bg-amber-100 text-amber-800 text-[11px] font-semibold px-1.5 py-0.5 rounded">
                محدث (v{article.current_version})
              </span>
            )}
            <span className="text-slate-400 font-mono text-[11px]">v{article.current_version}</span>
          </div>
        </div>

        {/* Title with bdi isolation */}
        <h3
          className={`text-lg font-bold text-text group-hover:text-brand transition-colors line-clamp-2 mb-2 ${
            isRtl ? "text-right" : "text-left"
          }`}
          dir={isRtl ? "rtl" : "ltr"}
        >
          <bdi>{article.title}</bdi>
        </h3>

        {/* Reading Time & NLP State (Defect A14 & Unknown Sentiment disambiguation) */}
        <div className="flex flex-wrap items-center gap-2 mt-2 text-xs text-muted">
          <span className="inline-flex items-center space-x-1 space-x-reverse bg-slate-50 border border-slate-200 px-2 py-0.5 rounded text-[11px]">
            <BookOpen className="h-3 w-3 text-slate-500" />
            <span>
              {readingTime} {readingTime === 1 ? "دقيقة قراءة" : "دقائق قراءة"}
              {wordCount > 0 ? ` (${wordCount} كلمة)` : ""}
            </span>
          </span>

          <span
            className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-600 border border-slate-200"
            title="حالة تحليل المشاعر والموضوعات غير منفذة بعد (ليست محايداً ولا صفراً)"
          >
            التحليل: بانتظار المعالجة
          </span>
        </div>
      </div>

      {/* Footer Meta */}
      <div className="flex items-center justify-between pt-3 mt-4 border-t border-slate-100 text-xs text-muted">
        <div className="flex items-center space-x-1.5 space-x-reverse">
          <Calendar className="h-3.5 w-3.5 text-slate-400" />
          {article.published_at ? (
            <span>{formatDate(article.published_at)}</span>
          ) : (
            <span
              className="text-warning bg-amber-50 px-1.5 py-0.2 rounded border border-amber-200"
              title={article.publication_date_unknown_reason || "تاريخ النشر غير محدد في المصدر الأصلي"}
            >
              تاريخ النشر غير محدد
            </span>
          )}
        </div>

        <div className="flex items-center space-x-1 space-x-reverse text-brand font-medium group-hover:translate-x-[-2px] transition-transform">
          <span>قراءة التفاصيل</span>
          <ChevronLeft className="h-4 w-4" />
        </div>
      </div>
    </article>
  );
}
