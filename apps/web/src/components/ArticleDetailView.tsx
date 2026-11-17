import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api, ApiClientError } from "../lib/api";
import type { ArticleDetail, ArticleVersionItem, DuplicateRelationshipItem } from "../types/api";
import { EvidenceStrip } from "./EvidenceStrip";
import {
  AlertCircle,
  ArrowRight,
  Bookmark,
  BookmarkCheck,
  Check,
  Clock,
  Copy,
  ExternalLink,
  FileText,
  GitBranch,
  History,
  Layers,
  RefreshCw,
  Save,
  ShieldAlert,
  Trash2,
  Type,
} from "lucide-react";

interface ArticleDetailViewProps {
  articleId: string;
  onBack: () => void;
}

type ReaderFontSize = "compact" | "normal" | "large";

export function ArticleDetailView({ articleId, onBack }: ArticleDetailViewProps) {
  const { user } = useAuth();
  const isAnalystOrAdmin = user?.role === "Admin" || user?.role === "Analyst";

  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [versions, setVersions] = useState<ArticleVersionItem[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<ArticleVersionItem | null>(null);
  const [fontSize, setFontSize] = useState<ReaderFontSize>("normal");
  const [copied, setCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Duplicates & Syndication states
  const [duplicates, setDuplicates] = useState<DuplicateRelationshipItem[]>([]);
  const [isCheckingDuplicates, setIsCheckingDuplicates] = useState(false);

  // Workspace states
  const [isBookmarked, setIsBookmarked] = useState(false);
  const [isTogglingBookmark, setIsTogglingBookmark] = useState(false);
  const [noteContent, setNoteContent] = useState("");
  const [noteSavedAt, setNoteSavedAt] = useState<string | null>(null);
  const [isSavingNote, setIsSavingNote] = useState(false);
  const [noteFeedback, setNoteFeedback] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadData() {
      setIsLoading(true);
      setError(null);
      try {
        const detail = await api.getArticle(articleId, controller.signal);
        setArticle(detail);

        try {
          const vList = await api.getArticleVersions(articleId, controller.signal);
          setVersions(vList);
        } catch {
          // Version list optional fallback
        }

        try {
          const dupList = await api.getArticleDuplicates(articleId, controller.signal);
          setDuplicates(dupList);
        } catch {
          // Duplicates list optional fallback
        }

        // Load bookmark status and analyst note if authorized
        if (isAnalystOrAdmin) {
          try {
            const bmStatus = await api.getBookmarkStatus(articleId, controller.signal);
            setIsBookmarked(bmStatus.is_bookmarked);
          } catch {
            // Non-blocking
          }

          try {
            const note = await api.getArticleNote(articleId, controller.signal);
            setNoteContent(note.content);
            setNoteSavedAt(note.updated_at);
          } catch {
            // Note might not exist yet
          }
        }
      } catch (err) {
        if (err instanceof ApiClientError) {
          setError(err.message);
        } else if ((err as Error).name !== "AbortError") {
          setError("فشل تحميل بيانات المقال. يرجى التحقق من اتصال الخادم.");
        }
      } finally {
        setIsLoading(false);
      }
    }

    loadData();
    return () => controller.abort();
  }, [articleId, isAnalystOrAdmin]);

  const handleToggleBookmark = async () => {
    if (isTogglingBookmark) return;
    setIsTogglingBookmark(true);
    try {
      if (isBookmarked) {
        await api.deleteBookmark(articleId);
        setIsBookmarked(false);
      } else {
        await api.createBookmark({ article_id: articleId });
        setIsBookmarked(true);
      }
    } catch {
      // Failed to toggle
    } finally {
      setIsTogglingBookmark(false);
    }
  };

  const handleSaveNote = async () => {
    if (!noteContent.trim()) return;
    setIsSavingNote(true);
    setNoteFeedback(null);
    try {
      const note = await api.upsertArticleNote(articleId, noteContent);
      setNoteSavedAt(note.updated_at);
      setNoteFeedback("تم حفظ الملاحظة في مساحتك الخاصة.");
      setTimeout(() => setNoteFeedback(null), 3000);
    } catch {
      setNoteFeedback("فشل حفظ الملاحظة.");
    } finally {
      setIsSavingNote(false);
    }
  };

  const handleDeleteNote = async () => {
    try {
      await api.deleteArticleNote(articleId);
      setNoteContent("");
      setNoteSavedAt(null);
      setNoteFeedback("تم حذف الملاحظة.");
      setTimeout(() => setNoteFeedback(null), 3000);
    } catch {
      setNoteFeedback("فشل حذف الملاحظة.");
    }
  };

  const handleRunDeduplication = async () => {
    if (isCheckingDuplicates) return;
    setIsCheckingDuplicates(true);
    try {
      const res = await api.runArticleDeduplication(articleId);
      setDuplicates(res);
    } catch {
      // Failed to run deduplication
    } finally {
      setIsCheckingDuplicates(false);
    }
  };

  const handleCopyLink = () => {
    if (typeof window === "undefined") return;
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6">
        <div className="animate-pulse space-y-6">
          <div className="h-6 w-24 bg-slate-200 rounded"></div>
          <div className="h-10 bg-slate-200 rounded w-3/4"></div>
          <div className="h-14 bg-slate-200 rounded"></div>
          <div className="space-y-3">
            <div className="h-4 bg-slate-200 rounded"></div>
            <div className="h-4 bg-slate-200 rounded"></div>
            <div className="h-4 bg-slate-200 rounded w-5/6"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="max-w-4xl mx-auto py-12 px-4 sm:px-6" dir="rtl">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <AlertCircle className="h-10 w-10 text-negative mx-auto mb-3" />
          <h3 className="text-lg font-bold text-negative mb-2">خطأ في استرجاع المقال</h3>
          <p className="text-sm text-muted mb-4">{error || "لم يتم العثور على المقال المطلوب."}</p>
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center space-x-2 space-x-reverse px-4 py-2 bg-white border border-border rounded-lg text-sm font-medium text-text hover:bg-slate-50"
          >
            <ArrowRight className="h-4 w-4" />
            <span>العودة لقائمة المقالات</span>
          </button>
        </div>
      </div>
    );
  }

  const isRtl = article.language.toLowerCase() === "ar";
  const displayedTitle = selectedVersion ? selectedVersion.title : article.title;
  const displayedBody = selectedVersion ? selectedVersion.body_text : article.body_text;
  const displayedVersionNum = selectedVersion ? selectedVersion.version : article.current_version;

  // Font size class mapping for calm reader experience
  const getFontSizeClass = () => {
    switch (fontSize) {
      case "compact":
        return "text-base leading-relaxed";
      case "large":
        return "text-xl leading-[2.1]";
      case "normal":
      default:
        return "text-lg leading-reader";
    }
  };

  return (
    <article className="max-w-4xl mx-auto py-8 px-4 sm:px-6" dir="rtl">
      {/* Top Bar: Back & Reader Controls */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center space-x-2 space-x-reverse text-sm font-medium text-muted hover:text-brand transition-colors focus:ring-2 focus:ring-focus rounded p-1"
        >
          <ArrowRight className="h-4 w-4" />
          <span>العودة لنتائج البحث (مع الاحتفاظ بالمرشحات)</span>
        </button>

        <div className="flex items-center space-x-3 space-x-reverse text-xs">
          {/* Font Size Adjuster */}
          <div className="flex items-center bg-canvas border border-border rounded-lg p-1 space-x-1 space-x-reverse">
            <Type className="h-3.5 w-3.5 text-muted ml-1" />
            <button
              type="button"
              onClick={() => setFontSize("compact")}
              className={`px-2 py-0.5 rounded font-mono ${
                fontSize === "compact" ? "bg-white font-bold text-brand shadow-xs" : "text-muted"
              }`}
              title="خط مدمج (16px)"
            >
              صغير
            </button>
            <button
              type="button"
              onClick={() => setFontSize("normal")}
              className={`px-2 py-0.5 rounded font-mono ${
                fontSize === "normal" ? "bg-white font-bold text-brand shadow-xs" : "text-muted"
              }`}
              title="خط عادي (18px)"
            >
              عادي
            </button>
            <button
              type="button"
              onClick={() => setFontSize("large")}
              className={`px-2 py-0.5 rounded font-mono ${
                fontSize === "large" ? "bg-white font-bold text-brand shadow-xs" : "text-muted"
              }`}
              title="خط كبير (20px)"
            >
              كبير
            </button>
          </div>

          {/* Copy Link Button */}
          <button
            type="button"
            onClick={handleCopyLink}
            className="inline-flex items-center space-x-1.5 space-x-reverse px-3 py-1.5 bg-canvas hover:bg-slate-200 border border-border rounded-lg font-medium text-text transition-colors"
            title="نسخ الرابط المباشر للمقال"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-positive" />
                <span className="text-positive font-bold">تم نسخ الرابط!</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5 text-muted" />
                <span>نسخ الرابط</span>
              </>
            )}
          </button>

          {/* Bookmark Button for Analysts & Admins */}
          {isAnalystOrAdmin && (
            <button
              type="button"
              onClick={handleToggleBookmark}
              disabled={isTogglingBookmark}
              className={`inline-flex items-center space-x-1.5 space-x-reverse px-3 py-1.5 border rounded-lg font-medium transition-colors ${
                isBookmarked
                  ? "bg-brand text-white border-brand"
                  : "bg-canvas hover:bg-slate-200 border-border text-text"
              }`}
              title={isBookmarked ? "إزالة من الإشارات المرجعية" : "إضافة إلى الإشارات المرجعية"}
            >
              {isBookmarked ? (
                <>
                  <BookmarkCheck className="h-3.5 w-3.5" />
                  <span>محفوظ في الإشارات</span>
                </>
              ) : (
                <>
                  <Bookmark className="h-3.5 w-3.5 text-muted" />
                  <span>إشارة مرجعية</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Main Headline with bdi isolation */}
      <h1
        className={`text-2xl sm:text-3xl font-extrabold text-text tracking-tight mb-4 leading-tight ${
          isRtl ? "text-right" : "text-left"
        }`}
        dir={isRtl ? "rtl" : "ltr"}
      >
        <bdi>{displayedTitle}</bdi>
      </h1>

      {/* Evidence Strip (Distinct publish/fetch dates, word count reading time) */}
      <EvidenceStrip
        sourceId={article.source_id}
        originalUrl={article.original_url}
        publishedAt={article.published_at}
        publicationDateUnknownReason={article.publication_date_unknown_reason}
        fetchedAt={article.fetched_at}
        version={displayedVersionNum}
        contentHash={selectedVersion ? selectedVersion.content_hash : article.content_hash}
        readingTimeMinutes={article.reading_time_minutes}
        wordCount={article.word_count}
        className="mb-6"
      />

      {/* Publisher Display Policy & Legal Attribution Banner */}
      <div className="mb-6 bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs text-muted flex items-start space-x-2 space-x-reverse">
        <ShieldAlert className="h-4 w-4 text-slate-500 mt-0.5 flex-shrink-0" />
        <div className="leading-relaxed">
          <span>
            جميع حقوق النشر محفوظة للمصدر الأصلي <strong>({article.source_id})</strong>. النص منشور
            ومحفوظ محلياً لأغراض التحليل والرصد الصحفي وفق السياسة المعتمدة للمصدر.
          </span>
          {article.original_url && (
            <a
              href={article.original_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-1 space-x-reverse mr-2 text-brand font-medium hover:underline"
            >
              <span>مراجعة المادة على موقع الناشر الأصلي</span>
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>

      {/* Historical Version Notice Banner */}
      {selectedVersion && (
        <div className="mb-6 bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center space-x-2 space-x-reverse text-warning text-sm">
            <History className="h-5 w-5 flex-shrink-0" />
            <span>
              أنت تعرض حالياً لقطة تاريخية قديمة <strong>(النسخة {selectedVersion.version})</strong> محفوظة في سجل المراجعات غير القابل للتعديل.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setSelectedVersion(null)}
            className="text-xs font-semibold bg-white border border-amber-300 px-3 py-1.5 rounded hover:bg-amber-100 text-amber-900 transition-colors"
          >
            عرض النسخة الأحدث (v{article.current_version})
          </button>
        </div>
      )}

      {/* Article Body - Calm Reader View with adjustable size and bidi isolation */}
      <div
        className={`bg-surface border border-border rounded-xl p-6 sm:p-10 shadow-sm text-text space-y-5 ${getFontSizeClass()} ${
          isRtl ? "text-right" : "text-left font-sans"
        }`}
        dir={isRtl ? "rtl" : "ltr"}
      >
        {displayedBody.split("\n\n").map((para, idx) => {
          const trimmed = para.trim();
          if (!trimmed) return null;
          return (
            <p key={idx} dir="auto" className="leading-inherit">
              {trimmed}
            </p>
          );
        })}
      </div>

      {/* Private Analyst Notes Section (مساحة الملاحظات التحليلية الخاصة) */}
      {isAnalystOrAdmin && (
        <section className="mt-8 bg-surface border border-border rounded-xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-3 border-b border-border pb-3">
            <div className="flex items-center space-x-2 space-x-reverse">
              <FileText className="h-5 w-5 text-brand" />
              <h2 className="text-base font-bold text-text">ملاحظاتك التحليلية الخاصة</h2>
            </div>
            {noteSavedAt && (
              <span className="text-xs text-muted">
                آخر حفظ: {new Date(noteSavedAt).toLocaleTimeString("ar-EG")}
              </span>
            )}
          </div>

          <p className="text-xs text-muted mb-3">
            هذه الملاحظات خاصة بك وحدك ومحفوظة في مساحة عملك، لا يمكن لأي مستخدم آخر في النظام الاطلاع عليها.
          </p>

          <textarea
            rows={4}
            value={noteContent}
            onChange={(e) => setNoteContent(e.target.value)}
            placeholder="اكتب ملاحظاتك التحليلية، استنتاجاتك الميدانية، أو ملخص التقييم هنا..."
            className="w-full p-3 bg-canvas border border-border rounded-lg text-sm text-text focus:ring-2 focus:ring-focus outline-none leading-relaxed"
          />

          {noteFeedback && (
            <div className="mt-2 text-xs text-positive font-medium">
              {noteFeedback}
            </div>
          )}

          <div className="mt-3 flex items-center justify-between">
            <button
              type="button"
              onClick={handleSaveNote}
              disabled={isSavingNote || !noteContent.trim()}
              className="inline-flex items-center space-x-1.5 space-x-reverse px-4 py-2 bg-brand hover:bg-brand-hover disabled:opacity-50 text-white rounded-lg text-xs font-semibold transition-colors"
            >
              <Save className="h-3.5 w-3.5" />
              <span>{isSavingNote ? "جاري الحفظ..." : "حفظ الملاحظة"}</span>
            </button>

            {noteSavedAt && (
              <button
                type="button"
                onClick={handleDeleteNote}
                className="inline-flex items-center space-x-1 space-x-reverse text-xs text-negative hover:underline"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>حذف الملاحظة</span>
              </button>
            )}
          </div>
        </section>
      )}

      {/* Duplicates & Wire Syndication Section (التغطيات المكررة وإعادة النشر) */}
      <section className="mt-8 bg-surface border border-border rounded-xl p-6 shadow-xs">
        <div className="flex items-center justify-between mb-4 border-b border-border pb-3">
          <div className="flex items-center space-x-2 space-x-reverse">
            <Layers className="h-5 w-5 text-brand" />
            <h2 className="text-base font-bold text-text">
              التغطيات المكررة وإعادة النشر ({duplicates.length})
            </h2>
          </div>
          {isAnalystOrAdmin && (
            <button
              type="button"
              onClick={handleRunDeduplication}
              disabled={isCheckingDuplicates}
              className="inline-flex items-center space-x-1.5 space-x-reverse px-3 py-1.5 bg-canvas border border-border hover:bg-slate-100 disabled:opacity-50 text-text rounded-lg text-xs font-medium transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isCheckingDuplicates ? "animate-spin" : ""}`} />
              <span>{isCheckingDuplicates ? "جاري الفحص..." : "فحص التكرار الآن"}</span>
            </button>
          )}
        </div>

        {duplicates.length === 0 ? (
          <p className="text-xs text-muted">
            لا توجد تغطيات مكررة أو إعادة نشر متطابقة تم رصدها لهذا المقال حتى الآن.
          </p>
        ) : (
          <div className="space-y-3">
            {duplicates.map((dup) => (
              <div
                key={dup.relationship_id}
                className="p-3.5 rounded-lg border border-border bg-canvas flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2 space-x-reverse">
                    <span
                      className={`px-2 py-0.5 rounded font-medium text-[11px] ${
                        dup.duplicate_type === "syndication"
                          ? "bg-purple-100 text-purple-800"
                          : dup.duplicate_type === "exact_hash"
                          ? "bg-blue-100 text-blue-800"
                          : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {dup.duplicate_type === "syndication"
                        ? "سلك وكالات (Syndication)"
                        : dup.duplicate_type === "exact_hash"
                        ? "تطابق تام (Exact Hash)"
                        : "شبه مكرر (Near Duplicate)"}
                    </span>
                    {dup.evidence.shared_wire_agency && (
                      <span className="font-semibold text-text">
                        وكالة: {dup.evidence.shared_wire_agency}
                      </span>
                    )}
                    <span className="text-muted">
                      نسبة التطابق: {(dup.similarity_score * 100).toFixed(0)}%
                    </span>
                  </div>

                  {dup.related_article && (
                    <div className="text-text font-medium text-sm pt-1">
                      <bdi>{dup.related_article.title}</bdi>
                    </div>
                  )}

                  <p className="text-[11px] text-muted">
                    {dup.evidence.reason || "تم كشف التطابق وفق خوارزمية المقارنة النصية وشينغلينغ."}
                  </p>
                </div>

                {dup.related_article && (
                  <div className="flex-shrink-0 text-left sm:text-right">
                    <span className="text-xs text-muted block font-mono">
                      {dup.related_article.source_id}
                    </span>
                    {dup.related_article.published_at && (
                      <span className="text-[11px] text-muted block">
                        {new Date(dup.related_article.published_at).toLocaleString("ar-EG")}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Versions & Revisions History Drawer */}
      {versions.length > 0 && (
        <section className="mt-12 bg-surface border border-border rounded-xl p-6 shadow-sm">
          <div className="flex items-center space-x-2 space-x-reverse mb-4 border-b border-border pb-3">
            <GitBranch className="h-5 w-5 text-brand" />
            <h2 className="text-lg font-bold text-text">سجل المراجعات والنسخ المؤرشفة ({versions.length})</h2>
          </div>

          <div className="space-y-3">
            {versions.map((v) => {
              const isCurrent = v.version === article.current_version;
              const isSelected = selectedVersion ? selectedVersion.version === v.version : isCurrent;

              return (
                <div
                  key={v.version}
                  onClick={() => (isCurrent ? setSelectedVersion(null) : setSelectedVersion(v))}
                  className={`p-3.5 rounded-lg border text-sm transition-all cursor-pointer flex items-center justify-between ${
                    isSelected
                      ? "border-brand bg-brand-light/40"
                      : "border-border hover:border-slate-300 bg-canvas"
                  }`}
                >
                  <div className="flex items-center space-x-3 space-x-reverse">
                    <span className="font-mono font-bold bg-white border border-border px-2 py-0.5 rounded text-xs">
                      v{v.version}
                    </span>
                    <span className="text-text font-medium"><bdi>{v.title}</bdi></span>
                    <span className="text-xs text-muted font-mono">({v.operation})</span>
                  </div>

                  <div className="flex items-center space-x-3 space-x-reverse text-xs text-muted">
                    <span className="flex items-center space-x-1 space-x-reverse">
                      <Clock className="h-3.5 w-3.5" />
                      <span>{new Date(v.created_at).toLocaleDateString("ar-EG")}</span>
                    </span>
                    {isCurrent ? (
                      <span className="bg-positive/10 text-positive px-2 py-0.5 rounded font-medium text-[11px]">
                        النسخة الحالية
                      </span>
                    ) : (
                      <span className="text-brand hover:underline flex items-center space-x-1 space-x-reverse text-[11px]">
                        <FileText className="h-3.5 w-3.5" />
                        <span>معاينة النسخة</span>
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </article>
  );
}
