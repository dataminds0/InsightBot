import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api, ApiClientError } from "../lib/api";
import type { StoryAuditItem, StoryDetail, StoryItem } from "../types/api";
import {
  AlertCircle,
  ChevronLeft,
  Clock,
  ExternalLink,
  Flame,
  GitMerge,
  GitPullRequest,
  Globe,
  History,
  Layers,
  MapPin,
  Newspaper,
  RefreshCw,
  Scale,
  X,
} from "lucide-react";

interface StoriesViewProps {
  onSelectArticle: (articleId: string) => void;
  onOpenComparison?: (storyId: string) => void;
}

type StoryStatusFilter = "all" | "emerging" | "peak" | "declining" | "closed";

export function StoriesView({ onSelectArticle, onOpenComparison }: StoriesViewProps) {
  const { user } = useAuth();
  const isAnalystOrAdmin = user?.role === "Admin" || user?.role === "Analyst";

  const [stories, setStories] = useState<StoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StoryStatusFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selected story for detail modal
  const [selectedStory, setSelectedStory] = useState<StoryDetail | null>(null);
  const [storyAudits, setStoryAudits] = useState<StoryAuditItem[]>([]);

  // Split & Merge modal states
  const [isMerging, setIsMerging] = useState(false);
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [mergeReason, setMergeReason] = useState("");
  const [isSubmittingMerge, setIsSubmittingMerge] = useState(false);

  const [isSplitting, setIsSplitting] = useState(false);
  const [splitSelectedArticles, setSplitSelectedArticles] = useState<string[]>([]);
  const [splitNewTitle, setSplitNewTitle] = useState("");
  const [splitReason, setSplitReason] = useState("");
  const [isSubmittingSplit, setIsSubmittingSplit] = useState(false);

  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const loadStories = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.listStories({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 50,
      });
      setStories(res.items);
      setTotal(res.total);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تحميل قائمة القصص الإخبارية.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStories();
  }, [statusFilter]);

  const handleOpenDetail = async (storyId: string) => {
    try {
      const detail = await api.getStory(storyId);
      setSelectedStory(detail);
      const audits = await api.getStoryHistory(storyId);
      setStoryAudits(audits);
    } catch {
      //
    }
  };

  const handleExecuteMerge = async () => {
    if (!selectedStory || !mergeTargetId.trim() || !mergeReason.trim()) return;
    setIsSubmittingMerge(true);
    setActionFeedback(null);
    try {
      await api.mergeStories(mergeTargetId.trim(), selectedStory.story_id, mergeReason.trim());
      setActionFeedback("تم دمج القصة بنجاح وحفظ سجل التدقيق.");
      setIsMerging(false);
      setSelectedStory(null);
      loadStories();
    } catch (err) {
      setActionFeedback(err instanceof Error ? err.message : "فشل الدمج.");
    } finally {
      setIsSubmittingMerge(false);
    }
  };

  const handleExecuteSplit = async () => {
    if (
      !selectedStory ||
      splitSelectedArticles.length === 0 ||
      !splitNewTitle.trim() ||
      !splitReason.trim()
    )
      return;
    setIsSubmittingSplit(true);
    setActionFeedback(null);
    try {
      await api.splitStory(
        selectedStory.story_id,
        splitSelectedArticles,
        splitNewTitle.trim(),
        splitReason.trim()
      );
      setActionFeedback("تم انشطار القصة وتأسيس عنقود حدث جديد مع سجل تدقيق.");
      setIsSplitting(false);
      setSelectedStory(null);
      loadStories();
    } catch (err) {
      setActionFeedback(err instanceof Error ? err.message : "فشل الانشطار.");
    } finally {
      setIsSubmittingSplit(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "emerging":
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 flex items-center space-x-1 space-x-reverse">
            <Flame className="h-3 w-3" />
            <span>تشكّل / عاجل</span>
          </span>
        );
      case "peak":
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 flex items-center space-x-1 space-x-reverse">
            <Flame className="h-3 w-3" />
            <span>ذروة التغطية</span>
          </span>
        );
      case "declining":
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
            تراجع واستقرار
          </span>
        );
      case "closed":
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
            مغلقة / مؤرشفة
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface border border-border p-5 rounded-xl shadow-xs">
        <div>
          <h1 className="text-xl font-bold text-text flex items-center space-x-2 space-x-reverse">
            <Layers className="h-6 w-6 text-brand" />
            <span>عناقيد القصص والأحداث {total > 0 ? `(${total})` : ""}</span>
          </h1>
          <p className="text-xs text-muted mt-1">
            تجميع ديناميكي لتغطيات الأحداث الواقعية عبر المصادر، مع دورة حياة الحدث (تشكّل، ذروة، تراجع) وحراسة ضد التمدد الزاحف.
          </p>
        </div>

        {/* Status filter tabs */}
        <div className="flex items-center space-x-1 space-x-reverse bg-canvas p-1 rounded-lg border border-border text-xs">
          {(
            [
              { id: "all", label: "الكل" },
              { id: "emerging", label: "تشكّل" },
              { id: "peak", label: "ذروة" },
              { id: "declining", label: "تراجع" },
              { id: "closed", label: "مغلقة" },
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setStatusFilter(t.id)}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                statusFilter === t.id
                  ? "bg-brand text-white shadow-xs"
                  : "text-muted hover:text-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {actionFeedback && (
        <div className="p-3 bg-positive/10 border border-positive/30 rounded-lg text-xs text-positive font-medium">
          {actionFeedback}
        </div>
      )}

      {error && (
        <div className="p-4 bg-negative/10 border border-negative/30 rounded-lg text-xs text-negative flex items-center space-x-2 space-x-reverse">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Stories Grid */}
      {isLoading ? (
        <div className="text-center py-16 text-muted text-sm flex flex-col items-center space-y-2">
          <RefreshCw className="h-6 w-6 animate-spin text-brand" />
          <span>جاري تجميع وتحميل عناقيد القصص...</span>
        </div>
      ) : stories.length === 0 ? (
        <div className="text-center py-16 bg-surface border border-border rounded-xl p-8 space-y-3">
          <Layers className="h-10 w-10 text-muted mx-auto" />
          <h2 className="text-sm font-semibold text-text">لا توجد قصص إخبارية مطابقة</h2>
          <p className="text-xs text-muted max-w-sm mx-auto">
            لم يتم العثور على عناقيد أحداث في هذه الحالة. يمكنك استيراد أو فحص المقالات لتشكيل القصص آلياً.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {stories.map((story) => (
            <div
              key={story.story_id}
              className="bg-surface border border-border hover:border-brand/40 rounded-xl p-5 shadow-xs transition-all flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  {getStatusBadge(story.status)}
                  <span className="text-[11px] text-muted font-mono">v{story.version}</span>
                </div>

                <h2 className="text-sm font-bold text-text leading-snug hover:text-brand transition-colors">
                  <bdi>{story.title}</bdi>
                </h2>

                {story.summary && (
                  <p className="text-xs text-muted line-clamp-2 leading-relaxed">
                    {story.summary}
                  </p>
                )}

                {/* Badges / Entities */}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {story.primary_location && (
                    <span className="inline-flex items-center space-x-1 space-x-reverse text-[11px] bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                      <MapPin className="h-3 w-3 text-brand" />
                      <span>{story.primary_location}</span>
                    </span>
                  )}
                  {story.sources.slice(0, 3).map((src) => (
                    <span
                      key={src}
                      className="inline-flex items-center space-x-1 space-x-reverse text-[11px] bg-canvas border border-border text-muted px-2 py-0.5 rounded font-mono"
                    >
                      <Globe className="h-2.5 w-2.5" />
                      <span>{src}</span>
                    </span>
                  ))}
                  {story.sources.length > 3 && (
                    <span className="text-[10px] text-muted self-center">
                      +{story.sources.length - 3} مصادر
                    </span>
                  )}
                </div>

                {story.keywords.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {story.keywords.slice(0, 4).map((kw) => (
                      <span
                        key={kw}
                        className="text-[10px] bg-brand-light/30 text-brand px-1.5 py-0.5 rounded"
                      >
                        #{kw}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="pt-4 mt-4 border-t border-border flex items-center justify-between text-xs text-muted">
                <div className="flex items-center space-x-3 space-x-reverse">
                  <span className="flex items-center space-x-1 space-x-reverse">
                    <Newspaper className="h-3.5 w-3.5" />
                    <span>{story.article_count} مقالات</span>
                  </span>
                  <span className="flex items-center space-x-1 space-x-reverse">
                    <Clock className="h-3.5 w-3.5" />
                    <span>{new Date(story.updated_at).toLocaleDateString("ar-EG")}</span>
                  </span>
                </div>

                <div className="flex items-center space-x-2 space-x-reverse">
                  {onOpenComparison && (
                    <button
                      type="button"
                      onClick={() => onOpenComparison(story.story_id)}
                      className="inline-flex items-center space-x-1 space-x-reverse text-xs bg-brand-light text-brand px-2.5 py-1 rounded-md hover:bg-brand-light/80 font-medium transition-colors"
                      title="مقارنة زوايا التغطية بين المصادر"
                    >
                      <Scale className="h-3 w-3 ml-1" />
                      <span>مقارنة التغطية</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleOpenDetail(story.story_id)}
                    className="inline-flex items-center space-x-1 space-x-reverse font-medium text-brand hover:underline"
                  >
                    <span>التفاصيل</span>
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Story Detail & Timeline Modal */}
      {selectedStory && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl shadow-xl max-w-3xl w-full max-h-[85vh] overflow-y-auto p-6 space-y-6">
            <div className="flex items-start justify-between border-b border-border pb-4">
              <div className="space-y-1.5">
                <div className="flex items-center space-x-2 space-x-reverse">
                  {getStatusBadge(selectedStory.status)}
                  <span className="text-xs text-muted font-mono">
                    المعرف: {selectedStory.story_id.slice(0, 8)}... (النسخة v{selectedStory.version})
                  </span>
                </div>
                <h2 className="text-base font-bold text-text leading-snug">
                  <bdi>{selectedStory.title}</bdi>
                </h2>
              </div>
              <div className="flex items-center space-x-2 space-x-reverse">
                {onOpenComparison && (
                  <button
                    type="button"
                    onClick={() => {
                      onOpenComparison(selectedStory.story_id);
                      setSelectedStory(null);
                    }}
                    className="inline-flex items-center space-x-1 space-x-reverse px-3 py-1.5 bg-brand text-white hover:bg-brand-hover rounded-lg text-xs font-semibold shadow-xs transition-colors"
                  >
                    <Scale className="h-3.5 w-3.5 ml-1" />
                    <span>مقارنة التغطية</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setSelectedStory(null)}
                  className="p-1 rounded-lg hover:bg-canvas text-muted hover:text-text"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* Analyst Controls: Merge & Split Buttons */}
            {isAnalystOrAdmin && (
              <div className="p-3 bg-canvas border border-border rounded-lg flex items-center justify-between text-xs">
                <span className="font-semibold text-text">عمليات التدقيق والتحرير:</span>
                <div className="flex items-center space-x-2 space-x-reverse">
                  <button
                    type="button"
                    onClick={() => {
                      setIsMerging(true);
                      setIsSplitting(false);
                    }}
                    className="inline-flex items-center space-x-1 space-x-reverse px-2.5 py-1.5 bg-surface border border-border hover:bg-slate-100 rounded text-text font-medium"
                  >
                    <GitMerge className="h-3.5 w-3.5 text-brand" />
                    <span>دمج مع قصة أخرى</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsSplitting(true);
                      setIsMerging(false);
                    }}
                    className="inline-flex items-center space-x-1 space-x-reverse px-2.5 py-1.5 bg-surface border border-border hover:bg-slate-100 rounded text-text font-medium"
                  >
                    <GitPullRequest className="h-3.5 w-3.5 text-warning" />
                    <span>انشطار مقالات</span>
                  </button>
                </div>
              </div>
            )}

            {/* Merge Form */}
            {isMerging && (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg space-y-3 text-xs">
                <h3 className="font-bold text-amber-900">دمج هذه القصة في قصة مستهدفة:</h3>
                <input
                  type="text"
                  placeholder="معرف القصة المستهدفة (Target Story ID)..."
                  value={mergeTargetId}
                  onChange={(e) => setMergeTargetId(e.target.value)}
                  className="w-full p-2 bg-white border border-amber-300 rounded outline-none"
                />
                <input
                  type="text"
                  placeholder="مبرر الدمج التحليلي (مطلوب للتدقيق)..."
                  value={mergeReason}
                  onChange={(e) => setMergeReason(e.target.value)}
                  className="w-full p-2 bg-white border border-amber-300 rounded outline-none"
                />
                <div className="flex items-center space-x-2 space-x-reverse">
                  <button
                    type="button"
                    disabled={isSubmittingMerge || !mergeTargetId.trim() || !mergeReason.trim()}
                    onClick={handleExecuteMerge}
                    className="px-3 py-1.5 bg-brand hover:bg-brand-hover text-white rounded font-medium disabled:opacity-50"
                  >
                    {isSubmittingMerge ? "جاري الدمج..." : "تأكيد الدمج"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsMerging(false)}
                    className="px-3 py-1.5 bg-white border border-slate-300 rounded hover:bg-slate-50"
                  >
                    إلغاء
                  </button>
                </div>
              </div>
            )}

            {/* Split Form */}
            {isSplitting && (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg space-y-3 text-xs">
                <h3 className="font-bold text-amber-900">انشطار مقالات مختارة إلى قصة جديدة:</h3>
                <input
                  type="text"
                  placeholder="عنوان القصة الجديدة المنشطرة..."
                  value={splitNewTitle}
                  onChange={(e) => setSplitNewTitle(e.target.value)}
                  className="w-full p-2 bg-white border border-amber-300 rounded outline-none"
                />
                <input
                  type="text"
                  placeholder="سبب ومبرر الانشطار للتدقيق..."
                  value={splitReason}
                  onChange={(e) => setSplitReason(e.target.value)}
                  className="w-full p-2 bg-white border border-amber-300 rounded outline-none"
                />
                <p className="text-[11px] text-amber-800">
                  حدد المقالات المراد فصلها من الجدول أدناه ({splitSelectedArticles.length} محددة).
                </p>
                <div className="flex items-center space-x-2 space-x-reverse">
                  <button
                    type="button"
                    disabled={
                      isSubmittingSplit ||
                      splitSelectedArticles.length === 0 ||
                      !splitNewTitle.trim() ||
                      !splitReason.trim()
                    }
                    onClick={handleExecuteSplit}
                    className="px-3 py-1.5 bg-brand hover:bg-brand-hover text-white rounded font-medium disabled:opacity-50"
                  >
                    {isSubmittingSplit ? "جاري الانشطار..." : "تأكيد الانشطار"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsSplitting(false)}
                    className="px-3 py-1.5 bg-white border border-slate-300 rounded hover:bg-slate-50"
                  >
                    إلغاء
                  </button>
                </div>
              </div>
            )}

            {/* Member Articles Timeline */}
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-text flex items-center space-x-1.5 space-x-reverse">
                <Newspaper className="h-4 w-4 text-brand" />
                <span>الخط الزمني للمقالات والتغطيات ({selectedStory.member_articles.length})</span>
              </h3>

              <div className="space-y-2">
                {selectedStory.member_articles.map((art) => {
                  const isChecked = splitSelectedArticles.includes(art.article_id);
                  return (
                    <div
                      key={art.article_id}
                      className="p-3 bg-canvas border border-border rounded-lg flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center space-x-3 space-x-reverse">
                        {isSplitting && (
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSplitSelectedArticles([...splitSelectedArticles, art.article_id]);
                              } else {
                                setSplitSelectedArticles(
                                  splitSelectedArticles.filter((id) => id !== art.article_id)
                                );
                              }
                            }}
                            className="rounded border-slate-300"
                          />
                        )}
                        <div>
                          <div className="font-medium text-text hover:underline cursor-pointer" onClick={() => onSelectArticle(art.article_id)}>
                            <bdi>{art.title}</bdi>
                          </div>
                          <div className="flex items-center space-x-2 space-x-reverse text-[11px] text-muted pt-1">
                            <span className="font-mono bg-white px-1.5 py-0.5 rounded border border-border">
                              {art.source_id}
                            </span>
                            {art.published_at && (
                              <span>{new Date(art.published_at).toLocaleString("ar-EG")}</span>
                            )}
                          </div>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => onSelectArticle(art.article_id)}
                        className="inline-flex items-center space-x-1 space-x-reverse text-brand hover:underline flex-shrink-0"
                      >
                        <span>قراءة</span>
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Audit History Drawer */}
            {storyAudits.length > 0 && (
              <div className="pt-4 border-t border-border space-y-2">
                <h3 className="text-xs font-bold text-text flex items-center space-x-1.5 space-x-reverse">
                  <History className="h-3.5 w-3.5 text-muted" />
                  <span>سجل التدقيق والانشطار/الدمج غير القابل للتعديل</span>
                </h3>

                <div className="space-y-1.5 text-[11px]">
                  {storyAudits.map((aud) => (
                    <div
                      key={aud.audit_id}
                      className="p-2 bg-canvas border border-border rounded flex items-center justify-between text-muted"
                    >
                      <div className="flex items-center space-x-2 space-x-reverse">
                        <span className="font-mono font-bold text-text">{aud.action}</span>
                        <span>بواسطة: {aud.actor_id}</span>
                        <span>• {aud.reason}</span>
                      </div>
                      <span>{new Date(aud.timestamp).toLocaleTimeString("ar-EG")}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
