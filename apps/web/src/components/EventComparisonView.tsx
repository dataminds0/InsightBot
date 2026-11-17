import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api, ApiClientError } from "../lib/api";
import type {
  EventComparisonReport,
  StoryItem,
} from "../types/api";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  GitCompare,
  Layers,
  Newspaper,
  Quote,
  RefreshCw,
  Scale,
  ShieldAlert,
  UserCheck,
} from "lucide-react";

interface EventComparisonViewProps {
  initialStoryId?: string | null;
  onSelectArticle: (articleId: string) => void;
  onBackToStories?: () => void;
}

export function EventComparisonView({
  initialStoryId,
  onSelectArticle,
  onBackToStories,
}: EventComparisonViewProps) {
  const { user } = useAuth();
  const isAnalystOrAdmin = user?.role === "Admin" || user?.role === "Analyst";

  const [availableStories, setAvailableStories] = useState<StoryItem[]>([]);
  const [selectedStoryId, setSelectedStoryId] = useState<string>(initialStoryId || "");
  const [report, setReport] = useState<EventComparisonReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Active Tab: "perspectives" | "timeline" | "divergences" | "evidence"
  const [activeTab, setActiveTab] = useState<"perspectives" | "timeline" | "divergences" | "evidence">(
    "perspectives"
  );

  // Review Form State
  const [reviewStatus, setReviewStatus] = useState<"verified" | "flagged" | "in_dispute">("verified");
  const [reviewNotes, setReviewNotes] = useState("");
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [reviewFeedback, setReviewFeedback] = useState<string | null>(null);

  // Load available stories for the selector
  useEffect(() => {
    async function loadStoriesList() {
      try {
        const res = await api.listStories({ limit: 50 });
        setAvailableStories(res.items);
        if (!selectedStoryId && res.items.length > 0) {
          setSelectedStoryId(res.items[0].story_id);
        }
      } catch {
        // Handled silently
      }
    }
    loadStoriesList();
  }, [selectedStoryId]);

  // Load comparison report when selected story changes
  const loadComparison = async (storyId: string) => {
    if (!storyId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getStoryComparison(storyId);
      setReport(data);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تحميل تقرير مقارنة التغطية للحدث المحدد.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (selectedStoryId) {
      loadComparison(selectedStoryId);
    }
  }, [selectedStoryId]);

  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStoryId || !reviewNotes.trim()) return;
    setIsSubmittingReview(true);
    setReviewFeedback(null);
    try {
      await api.submitStoryReview(selectedStoryId, {
        status: reviewStatus,
        notes: reviewNotes.trim(),
        excluded_article_ids: [],
      });
      setReviewFeedback("تم تسجيل المراجعة التحليلية بنجاح وحفظها في سجل التدقيق.");
      setReviewNotes("");
      // Reload report to refresh review status
      loadComparison(selectedStoryId);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setReviewFeedback(`خطأ: ${err.message}`);
      } else {
        setReviewFeedback("فشل إرسال المراجعة التحليلية.");
      }
    } finally {
      setIsSubmittingReview(false);
    }
  };

  const formatDateTime = (isoString?: string | null) => {
    if (!isoString) return "تاريخ غير محدد";
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

  const getStatusBadge = (st: string) => {
    switch (st.toLowerCase()) {
      case "emerging":
        return <span className="bg-amber-100 text-amber-800 px-2.5 py-1 rounded text-xs font-bold">حدث عاجل أولي</span>;
      case "peak":
        return <span className="bg-emerald-100 text-emerald-800 px-2.5 py-1 rounded text-xs font-bold">ذروة التغطية</span>;
      case "declining":
        return <span className="bg-slate-100 text-slate-700 px-2.5 py-1 rounded text-xs font-bold">تراجع التغطية</span>;
      case "closed":
        return <span className="bg-slate-200 text-slate-500 px-2.5 py-1 rounded text-xs font-bold">مغلقة</span>;
      default:
        return <span className="bg-slate-100 text-slate-600 px-2.5 py-1 rounded text-xs">{st}</span>;
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
      {/* Top Header & Story Selector */}
      <div className="bg-surface border border-border rounded-xl p-6 mb-8 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div className="flex items-center space-x-3 space-x-reverse">
            <div className="p-3 bg-brand-light rounded-xl text-brand">
              <Scale className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2 space-x-reverse">
                <h1 className="text-xl font-bold text-text">مقارنة زوايا التغطية الإخبارية بين المصادر</h1>
                <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">T16</span>
              </div>
              <p className="text-xs text-muted mt-1">
                تحليل متزامن لكيفية تناول المصادر المعتمدة لنفس الحدث الواقعي، رصد الفوارق الزمنية، والأرقام المتباينة.
              </p>
            </div>
          </div>

          {onBackToStories && (
            <button
              type="button"
              onClick={onBackToStories}
              className="inline-flex items-center space-x-1.5 space-x-reverse px-4 py-2 border border-border rounded-lg text-xs font-medium text-text bg-white hover:bg-slate-50 transition-colors shadow-xs"
            >
              <ArrowRight className="h-4 w-4" />
              <span>العودة للقصص والأحداث</span>
            </button>
          )}
        </div>

        {/* Story Dropdown Selector */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-4 border-t border-border">
          <label className="text-xs font-semibold text-text whitespace-nowrap">الحدث المراد مقارنته:</label>
          <select
            value={selectedStoryId}
            onChange={(e) => setSelectedStoryId(e.target.value)}
            className="flex-1 py-2 px-3 border border-border rounded-lg text-sm bg-canvas text-text focus:ring-2 focus:ring-focus font-medium"
          >
            {availableStories.map((s) => (
              <option key={s.story_id} value={s.story_id}>
                {s.title} ({s.sources_count} مصادر | {s.article_count} مقالات)
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => loadComparison(selectedStoryId)}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-text rounded-lg text-xs font-semibold flex items-center justify-center space-x-1.5 space-x-reverse transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>تحديث التقرير</span>
          </button>
        </div>
      </div>

      {/* Screen States */}
      {isLoading && (
        <div className="bg-surface border border-border rounded-xl p-16 text-center my-6 shadow-sm">
          <RefreshCw className="h-8 w-8 text-brand animate-spin mx-auto mb-4" />
          <h3 className="text-base font-bold text-text mb-1">جاري تحليل ومقارنة زوايا التغطية...</h3>
          <p className="text-xs text-muted">استخراج الخط الزمني، رصد التباينات الرقمية، واستخلاص الأدلة الموثقة.</p>
        </div>
      )}

      {!isLoading && error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center my-6" role="alert">
          <AlertCircle className="h-10 w-10 text-negative mx-auto mb-3" />
          <h3 className="text-lg font-bold text-negative mb-2">فشل تحميل مقارنة الحدث</h3>
          <p className="text-sm text-muted mb-4">{error}</p>
          <button
            type="button"
            onClick={() => loadComparison(selectedStoryId)}
            className="px-4 py-2 bg-white border border-border text-sm font-medium rounded-lg text-text hover:bg-slate-50 transition-colors"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      {!isLoading && !error && report && (
        <>
          {/* Story Key Metrics Banner */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="bg-surface border border-border rounded-xl p-4 shadow-xs">
              <span className="text-xs text-muted block mb-1">حالة الحدث</span>
              <div>{getStatusBadge(report.story_status)}</div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-4 shadow-xs">
              <span className="text-xs text-muted block mb-1">المصادر المقارنة</span>
              <div className="flex items-center space-x-1 space-x-reverse font-bold text-lg text-text">
                <Newspaper className="h-4 w-4 text-brand" />
                <span>{report.sources_count}</span>
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-4 shadow-xs">
              <span className="text-xs text-muted block mb-1">المقالات المؤرشفة</span>
              <div className="flex items-center space-x-1 space-x-reverse font-bold text-lg text-text">
                <Layers className="h-4 w-4 text-brand" />
                <span>{report.articles_count}</span>
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-4 shadow-xs">
              <span className="text-xs text-muted block mb-1">النطاق الزمني للتغطية</span>
              <div className="flex items-center space-x-1 space-x-reverse font-bold text-lg text-text">
                <Clock className="h-4 w-4 text-brand" />
                <span>{report.reporting_span_hours} ساعة</span>
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-4 shadow-xs col-span-2 md:col-span-1">
              <span className="text-xs text-muted block mb-1">أول من أورد الخبر</span>
              <span className="font-bold text-sm text-brand truncate block" title={report.first_reported_source || "غير محدد"}>
                {report.first_reported_source || "غير محدد"}
              </span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex border-b border-border mb-6 text-sm font-semibold space-x-6 space-x-reverse">
            <button
              type="button"
              onClick={() => setActiveTab("perspectives")}
              className={`pb-3 px-1 border-b-2 transition-colors flex items-center space-x-2 space-x-reverse ${
                activeTab === "perspectives"
                  ? "border-brand text-brand"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              <GitCompare className="h-4 w-4 ml-1" />
              <span>زوايا التغطية ({report.perspectives.length})</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("timeline")}
              className={`pb-3 px-1 border-b-2 transition-colors flex items-center space-x-2 space-x-reverse ${
                activeTab === "timeline"
                  ? "border-brand text-brand"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              <Clock className="h-4 w-4 ml-1" />
              <span>الخط الزمني المقارن ({report.timeline.length})</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("divergences")}
              className={`pb-3 px-1 border-b-2 transition-colors flex items-center space-x-2 space-x-reverse ${
                activeTab === "divergences"
                  ? "border-brand text-brand"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              <ShieldAlert className="h-4 w-4 ml-1" />
              <span>نقاط التباين المنسوبة ({report.divergent_points.length})</span>
              {report.divergent_points.length > 0 && (
                <span className="bg-amber-100 text-amber-900 text-xs px-1.5 py-0.2 rounded-full font-bold">
                  {report.divergent_points.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("evidence")}
              className={`pb-3 px-1 border-b-2 transition-colors flex items-center space-x-2 space-x-reverse ${
                activeTab === "evidence"
                  ? "border-brand text-brand"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              <UserCheck className="h-4 w-4 ml-1" />
              <span>الأدلة والمراجعة التحليلية</span>
            </button>
          </div>

          {/* TAB 1: Source Perspectives Grid */}
          {activeTab === "perspectives" && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {report.perspectives.map((p) => (
                <div
                  key={p.source_id}
                  className="bg-surface border border-border rounded-xl p-5 shadow-sm flex flex-col justify-between"
                >
                  <div>
                    {/* Header */}
                    <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
                      <span className="font-bold text-brand bg-brand-light px-2.5 py-1 rounded text-xs">
                        {p.source_id}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded font-mono font-medium ${
                          p.latency_minutes_from_first === 0
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {p.latency_minutes_from_first === 0
                          ? "أسبقية النشر (الأول)"
                          : `+${p.latency_minutes_from_first} دقيقة فارق`}
                      </span>
                    </div>

                    {/* Headline */}
                    <h3 className="font-bold text-base text-text mb-3 leading-snug">
                      <bdi>{p.headline}</bdi>
                    </h3>

                    {/* Numerical Claims */}
                    {p.numerical_claims.length > 0 && (
                      <div className="mb-3">
                        <span className="text-[11px] font-semibold text-muted block mb-1">
                          الأرقام والإحصاءات المذكورة:
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {p.numerical_claims.map((claim, idx) => (
                            <span
                              key={idx}
                              className="bg-amber-50 text-amber-900 border border-amber-200 px-2 py-0.5 rounded text-xs font-mono font-bold"
                            >
                              {claim}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Key Entities */}
                    {p.key_entities.length > 0 && (
                      <div className="mb-3">
                        <span className="text-[11px] font-semibold text-muted block mb-1">الكيانات المركزية:</span>
                        <div className="flex flex-wrap gap-1">
                          {p.key_entities.map((ent, idx) => (
                            <span key={idx} className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px]">
                              {ent}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Footer Meta */}
                  <div className="pt-3 mt-4 border-t border-slate-100 text-xs text-muted flex items-center justify-between">
                    <span>
                      {p.article_count} {p.article_count === 1 ? "مقال" : "مقالات"} ({p.word_count} كلمة)
                    </span>
                    <button
                      type="button"
                      onClick={() => onSelectArticle(p.lead_article_id)}
                      className="text-brand hover:underline font-semibold"
                    >
                      عرض المقال الافتتاحي
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* TAB 2: Comparative Timeline */}
          {activeTab === "timeline" && (
            <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
              <div className="space-y-6 relative before:absolute before:inset-0 before:right-3 before:w-0.5 before:bg-slate-200">
                {report.timeline.map((item, idx) => (
                  <div key={item.milestone_id || idx} className="relative pr-8">
                    {/* Circle marker */}
                    <div
                      className={`absolute right-1.5 top-1.5 h-3.5 w-3.5 rounded-full border-2 border-white -translate-x-1/2 ${
                        item.is_lead_article ? "bg-brand ring-4 ring-brand-light" : "bg-slate-400"
                      }`}
                    />

                    <div className="bg-canvas border border-border rounded-lg p-4 shadow-2xs">
                      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                        <div className="flex items-center space-x-2 space-x-reverse">
                          <span className="font-bold text-xs bg-brand-light text-brand px-2 py-0.5 rounded">
                            {item.source_id}
                          </span>
                          {item.is_lead_article && (
                            <span className="bg-amber-100 text-amber-900 px-2 py-0.5 rounded text-[11px] font-bold">
                              الخبر الافتتاحي
                            </span>
                          )}
                          <span className="text-xs text-muted font-mono">{formatDateTime(item.timestamp)}</span>
                        </div>

                        {item.timestamp_basis === "unknown" && (
                          <span
                            className="bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded text-[11px]"
                            title="تاريخ النشر غير محدد من المصدر، اعتمد وقت الجلب (Defect A13)"
                          >
                            تاريخ النشر غير محدد
                          </span>
                        )}
                      </div>

                      <h4
                        className="font-bold text-sm text-text hover:text-brand cursor-pointer mb-2"
                        onClick={() => onSelectArticle(item.article_id)}
                      >
                        <bdi>{item.title}</bdi>
                      </h4>

                      {item.lead_quote && (
                        <p className="text-xs text-muted leading-relaxed line-clamp-2 bg-white p-2 rounded border border-slate-100">
                          <span className="font-semibold text-brand ml-1">اقتباس:</span>
                          <span>"{item.lead_quote}"</span>
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: Attributed Divergences */}
          {activeTab === "divergences" && (
            <div className="space-y-4">
              {report.divergent_points.length === 0 ? (
                <div className="bg-surface border border-border rounded-xl p-12 text-center shadow-sm">
                  <CheckCircle2 className="h-10 w-10 text-positive mx-auto mb-3" />
                  <h3 className="text-base font-bold text-text mb-1">لا توجد تباينات متناقضة رئيسية</h3>
                  <p className="text-xs text-muted">
                    تتطابق الروايات الأساسية والأرقام والإحصاءات بين المصادر المقارنة ضمن هذا الحدث.
                  </p>
                </div>
              ) : (
                report.divergent_points.map((diff) => (
                  <div
                    key={diff.difference_id}
                    className="bg-surface border border-border rounded-xl p-5 shadow-sm"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center space-x-2 space-x-reverse">
                        <AlertTriangle className="h-4 w-4 text-amber-600 ml-1" />
                        <span className="font-bold text-sm text-text">{diff.description}</span>
                      </div>
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded font-bold ${
                          diff.severity === "high"
                            ? "bg-red-100 text-red-900 border border-red-200"
                            : "bg-amber-100 text-amber-900 border border-amber-200"
                        }`}
                      >
                        {diff.severity === "high" ? "تباين عالي الأهمية" : "تباين متوسط"}
                      </span>
                    </div>

                    {/* Side by side comparison */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                      <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                        <div className="flex items-center justify-between text-xs font-bold text-brand mb-1">
                          <span>رواية المصدر: {diff.source_a}</span>
                          <span className="font-mono text-[11px] text-muted">إحالة: {diff.source_a_citation}</span>
                        </div>
                        <p className="text-xs text-text font-medium leading-relaxed">"{diff.source_a_claim}"</p>
                      </div>

                      <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                        <div className="flex items-center justify-between text-xs font-bold text-brand mb-1">
                          <span>رواية المصدر: {diff.source_b}</span>
                          <span className="font-mono text-[11px] text-muted">إحالة: {diff.source_b_citation}</span>
                        </div>
                        <p className="text-xs text-text font-medium leading-relaxed">"{diff.source_b_claim}"</p>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* TAB 4: Evidence & Analyst Review */}
          {activeTab === "evidence" && (
            <div className="space-y-6">
              {/* Analyst Review Section */}
              <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
                <div className="flex items-center justify-between mb-4 pb-3 border-b border-border">
                  <div className="flex items-center space-x-2 space-x-reverse">
                    <UserCheck className="h-5 w-5 text-brand" />
                    <h3 className="font-bold text-base text-text">المراجعة والتدقيق التحليلي (Analyst Review)</h3>
                  </div>

                  {report.latest_review ? (
                    <span className="bg-emerald-100 text-emerald-900 px-3 py-1 rounded text-xs font-bold flex items-center space-x-1 space-x-reverse">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-700 ml-1" />
                      <span>تمت المراجعة والتحقق: {report.latest_review.status}</span>
                    </span>
                  ) : (
                    <span className="bg-slate-100 text-slate-600 px-3 py-1 rounded text-xs font-medium">
                      بانتظار المراجعة التحليلية
                    </span>
                  )}
                </div>

                {report.latest_review && (
                  <div className="mb-6 p-4 bg-emerald-50/70 border border-emerald-200 rounded-lg text-xs">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-emerald-900">
                        ملاحظات المحلل: {report.latest_review.reviewer_id}
                      </span>
                      <span className="text-muted font-mono">{formatDateTime(report.latest_review.reviewed_at)}</span>
                    </div>
                    <p className="text-emerald-950 font-medium leading-relaxed">{report.latest_review.notes}</p>
                  </div>
                )}

                {/* Analyst Review Form */}
                {isAnalystOrAdmin ? (
                  <form onSubmit={handleSubmitReview} className="space-y-4 pt-2">
                    <div>
                      <label className="block text-xs font-semibold text-text mb-1">حالة التقييم التحليلي:</label>
                      <select
                        value={reviewStatus}
                        onChange={(e) =>
                          setReviewStatus(e.target.value as "verified" | "flagged" | "in_dispute")
                        }
                        className="w-full sm:w-64 px-3 py-2 border border-border rounded-lg text-sm bg-canvas focus:ring-2 focus:ring-focus font-medium"
                      >
                        <option value="verified">موثق ومعتمد (Verified)</option>
                        <option value="flagged">ملاحظات وتباينات (Flagged)</option>
                        <option value="in_dispute">روايات متنازع عليها (In Dispute)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-text mb-1">
                        تقرير الملاحظات التحليلية:
                      </label>
                      <textarea
                        rows={3}
                        required
                        value={reviewNotes}
                        onChange={(e) => setReviewNotes(e.target.value)}
                        placeholder="دون تحليلك للتباينات بين المصادر وأسباب اعتماد أو التشكيك في أرقام معينة..."
                        className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-canvas focus:ring-2 focus:ring-focus outline-none"
                      />
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <span className="text-xs text-muted">
                        سيتم توثيق اسمك وتوقيت المراجعة في سجل التدقيق غير القابل للتعديل.
                      </span>

                      <button
                        type="submit"
                        disabled={isSubmittingReview || !reviewNotes.trim()}
                        className="px-5 py-2 bg-brand hover:bg-brand-hover text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 shadow-xs"
                      >
                        {isSubmittingReview ? "جاري الحفظ..." : "حفظ المراجعة التحليلية"}
                      </button>
                    </div>

                    {reviewFeedback && (
                      <div className="mt-3 p-3 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded text-xs font-medium">
                        {reviewFeedback}
                      </div>
                    )}
                  </form>
                ) : (
                  <p className="text-xs text-muted">
                    يتطلب تسجيل الملاحظات والتدقيق التحليلي صلاحيات محلل (Analyst) أو مسؤول (Admin).
                  </p>
                )}
              </div>

              {/* Versioned Evidence Items */}
              <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
                <div className="flex items-center space-x-2 space-x-reverse mb-4">
                  <Quote className="h-5 w-5 text-brand ml-1" />
                  <h3 className="font-bold text-base text-text">الأدلة الموثقة برقم الإصدار (Versioned Evidence)</h3>
                </div>

                <div className="space-y-3">
                  {report.evidence_items.map((ev, idx) => (
                    <div
                      key={ev.evidence_id || idx}
                      className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs flex flex-col justify-between"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center space-x-2 space-x-reverse">
                          <span className="font-bold text-brand bg-brand-light px-2 py-0.5 rounded">
                            {ev.source_id}
                          </span>
                          <span className="font-mono text-muted text-[11px]">
                            {ev.article_id}:v{ev.version}
                          </span>
                        </div>

                        <a
                          href={ev.canonical_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand hover:underline flex items-center space-x-1 space-x-reverse text-[11px]"
                        >
                          <span>الرابط الأصلي</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>

                      <p className="text-text font-serif leading-relaxed italic bg-white p-2.5 rounded border border-slate-100">
                        "{ev.exact_quote}"
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
