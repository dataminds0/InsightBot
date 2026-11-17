import { useEffect, useState } from "react";
import { api, ApiClientError } from "../lib/api";
import type { BookmarkItem, NoteItem, SavedQuery } from "../types/api";
import {
  AlertCircle,
  AlertTriangle,
  Bell,
  BellOff,
  Bookmark as BookmarkIcon,
  Clock,
  ExternalLink,
  FileText,
  FolderKanban,
  Play,
  Plus,
  RefreshCw,
  Search,
  Tag,
  Trash2,
} from "lucide-react";

interface WorkspaceViewProps {
  onSelectArticle: (articleId: string) => void;
  onRunSavedQuery: (queryParams: Record<string, unknown>) => void;
}

type WorkspaceTab = "bookmarks" | "queries" | "notes";

export function WorkspaceView({ onSelectArticle, onRunSavedQuery }: WorkspaceViewProps) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("bookmarks");

  // Bookmarks state
  const [bookmarks, setBookmarks] = useState<BookmarkItem[]>([]);
  const [bookmarksTotal, setBookmarksTotal] = useState(0);
  const [selectedTag, setSelectedTag] = useState<string>("");
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [isLoadingBookmarks, setIsLoadingBookmarks] = useState(false);

  // Saved Queries state
  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([]);
  const [queriesTotal, setQueriesTotal] = useState(0);
  const [isLoadingQueries, setIsLoadingQueries] = useState(false);
  const [showNewQueryModal, setShowNewQueryModal] = useState(false);
  const [newQueryName, setNewQueryName] = useState("");
  const [newQueryTerm, setNewQueryTerm] = useState("");

  // Notes state
  const [notes, setNotes] = useState<NoteItem[]>([]);
  const [notesTotal, setNotesTotal] = useState(0);
  const [isLoadingNotes, setIsLoadingNotes] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const showNotification = (msg: string) => {
    setActionSuccess(msg);
    setTimeout(() => setActionSuccess(null), 3000);
  };

  // 1. Load Bookmarks
  const loadBookmarks = async (tag?: string) => {
    setIsLoadingBookmarks(true);
    setError(null);
    try {
      const res = await api.listBookmarks({ tag: tag || undefined, limit: 100 });
      setBookmarks(res.items);
      setBookmarksTotal(res.total);

      // Collect unique tags
      const tagSet = new Set<string>();
      res.items.forEach((bm) => {
        bm.tags.forEach((t) => tagSet.add(t));
      });
      setAvailableTags(Array.from(tagSet));
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تحميل الإشارات المرجعية.");
      }
    } finally {
      setIsLoadingBookmarks(false);
    }
  };

  // 2. Load Saved Queries
  const loadSavedQueries = async () => {
    setIsLoadingQueries(true);
    setError(null);
    try {
      const res = await api.listSavedQueries({ limit: 100 });
      setSavedQueries(res.items);
      setQueriesTotal(res.total);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تحميل الاستعلامات المحفوظة.");
      }
    } finally {
      setIsLoadingQueries(false);
    }
  };

  // 3. Load Notes
  const loadNotes = async () => {
    setIsLoadingNotes(true);
    setError(null);
    try {
      const res = await api.listNotes({ limit: 100 });
      setNotes(res.items);
      setNotesTotal(res.total);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تحميل الملاحظات التحليلية.");
      }
    } finally {
      setIsLoadingNotes(false);
    }
  };

  useEffect(() => {
    if (activeTab === "bookmarks") {
      loadBookmarks(selectedTag);
    } else if (activeTab === "queries") {
      loadSavedQueries();
    } else if (activeTab === "notes") {
      loadNotes();
    }
  }, [activeTab, selectedTag]);

  // Actions: Delete Bookmark
  const handleDeleteBookmark = async (articleId: string) => {
    try {
      await api.deleteBookmark(articleId);
      showNotification("تمت إزالة الإشارة المرجعية بنجاح.");
      loadBookmarks(selectedTag);
    } catch {
      setError("فشل حذف الإشارة المرجعية.");
    }
  };

  // Actions: Create Saved Query
  const handleCreateSavedQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newQueryName.trim()) return;

    try {
      await api.createSavedQuery({
        name: newQueryName.trim(),
        query_params: {
          q: newQueryTerm.trim(),
        },
        alerts_enabled: false,
      });
      setShowNewQueryModal(false);
      setNewQueryName("");
      setNewQueryTerm("");
      showNotification("تم حفظ الاستعلام في مساحة عملك.");
      loadSavedQueries();
    } catch {
      setError("فشل حفظ الاستعلام.");
    }
  };

  // Actions: Delete Saved Query
  const handleDeleteQuery = async (queryId: string) => {
    try {
      await api.deleteSavedQuery(queryId);
      showNotification("تم حذف الاستعلام المحفوظ.");
      loadSavedQueries();
    } catch {
      setError("فشل حذف الاستعلام.");
    }
  };

  const handleToggleAlert = async (
    queryId: string,
    nextEnabled: boolean,
    nextPaused: boolean,
    cooldownHours: number = 1
  ) => {
    try {
      const updated = await api.toggleQueryAlert({
        query_id: queryId,
        alerts_enabled: nextEnabled,
        is_paused: nextPaused,
        cooldown_hours: cooldownHours,
      });
      setSavedQueries((prev) =>
        prev.map((q) => (q.query_id === queryId ? { ...q, ...updated } : q))
      );
      showNotification(
        nextEnabled
          ? nextPaused
            ? "تم إيقاف تنبيهات الاستعلام مؤقتاً."
            : "تم تفعيل تنبيهات الاستعلام بنجاح."
          : "تم تعطيل تنبيهات الاستعلام."
      );
    } catch {
      setError("فشل تحديث إعدادات التنبيه للاستعلام.");
    }
  };

  // Actions: Delete Note
  const handleDeleteNote = async (articleId: string) => {
    try {
      await api.deleteArticleNote(articleId);
      showNotification("تم حذف الملاحظة التحليلية.");
      loadNotes();
    } catch {
      setError("فشل حذف الملاحظة.");
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
      {/* Workspace Header */}
      <div className="mb-8">
        <div className="flex items-center space-x-3 space-x-reverse mb-2">
          <div className="p-2.5 bg-brand-light text-brand rounded-xl">
            <FolderKanban className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-text tracking-tight">
              مساحة العمل التحليلية الشخصية
            </h1>
            <p className="text-sm text-muted">
              سجلاتك الخاصة المنعزلة تماماً: الإشارات المرجعية، استعلامات الرصد المحفوظة، والملاحظات التحليلية.
            </p>
          </div>
        </div>

        {/* Global Feedback Notifications */}
        {actionSuccess && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm flex items-center space-x-2 space-x-reverse">
            <span className="font-bold">✓</span>
            <span>{actionSuccess}</span>
          </div>
        )}
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 text-negative rounded-lg text-sm flex items-center space-x-2 space-x-reverse">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b border-border space-x-8 space-x-reverse mb-6">
        <button
          type="button"
          onClick={() => setActiveTab("bookmarks")}
          className={`pb-3 font-medium text-sm flex items-center space-x-2 space-x-reverse transition-colors border-b-2 ${
            activeTab === "bookmarks"
              ? "border-brand text-brand font-bold"
              : "border-transparent text-muted hover:text-text"
          }`}
        >
          <BookmarkIcon className="h-4 w-4" />
          <span>الإشارات المرجعية</span>
          <span className="bg-slate-100 text-slate-700 font-mono text-xs px-2 py-0.5 rounded-full">
            {bookmarksTotal}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("queries")}
          className={`pb-3 font-medium text-sm flex items-center space-x-2 space-x-reverse transition-colors border-b-2 ${
            activeTab === "queries"
              ? "border-brand text-brand font-bold"
              : "border-transparent text-muted hover:text-text"
          }`}
        >
          <Search className="h-4 w-4" />
          <span>الاستعلامات المحفوظة</span>
          <span className="bg-slate-100 text-slate-700 font-mono text-xs px-2 py-0.5 rounded-full">
            {queriesTotal}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("notes")}
          className={`pb-3 font-medium text-sm flex items-center space-x-2 space-x-reverse transition-colors border-b-2 ${
            activeTab === "notes"
              ? "border-brand text-brand font-bold"
              : "border-transparent text-muted hover:text-text"
          }`}
        >
          <FileText className="h-4 w-4" />
          <span>الملاحظات التحليلية</span>
          <span className="bg-slate-100 text-slate-700 font-mono text-xs px-2 py-0.5 rounded-full">
            {notesTotal}
          </span>
        </button>
      </div>

      {/* TAB 1: BOOKMARKS */}
      {activeTab === "bookmarks" && (
        <section className="space-y-4">
          {/* Tag filters bar */}
          {availableTags.length > 0 && (
            <div className="flex items-center space-x-2 space-x-reverse bg-surface p-3 rounded-lg border border-border text-xs">
              <Tag className="h-4 w-4 text-muted" />
              <span className="text-muted font-medium">تصفية حسب الوسم:</span>
              <button
                type="button"
                onClick={() => setSelectedTag("")}
                className={`px-2.5 py-1 rounded-full ${
                  selectedTag === "" ? "bg-brand text-white" : "bg-slate-100 hover:bg-slate-200"
                }`}
              >
                الكل
              </button>
              {availableTags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => setSelectedTag(tag)}
                  className={`px-2.5 py-1 rounded-full ${
                    selectedTag === tag ? "bg-brand text-white" : "bg-slate-100 hover:bg-slate-200"
                  }`}
                >
                  #{tag}
                </button>
              ))}
            </div>
          )}

          {isLoadingBookmarks ? (
            <div className="py-12 text-center text-muted">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand" />
              <span>جاري تحميل إشاراتك المرجعية...</span>
            </div>
          ) : bookmarks.length === 0 ? (
            <div className="bg-surface border border-border rounded-xl p-12 text-center text-muted">
              <BookmarkIcon className="h-10 w-10 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-text mb-1">لا توجد إشارات مرجعية محفوظة</h3>
              <p className="text-sm max-w-md mx-auto">
                يمكنك تمييز أي مقال وحفظه في مساحتك الخاصة بالضغط على زر الإشارة المرجعية أثناء تصفح المقالات.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {bookmarks.map((bm) => {
                const isRtl = bm.article ? bm.article.language === "ar" : true;
                return (
                  <div
                    key={bm.bookmark_id}
                    className="bg-surface border border-border rounded-xl p-5 shadow-xs hover:border-slate-300 transition-all"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-2 flex-1">
                        {/* Target Availability Badge */}
                        {!bm.target_available ? (
                          <div className="inline-flex items-center space-x-1.5 space-x-reverse bg-amber-50 border border-amber-200 text-amber-800 px-2.5 py-1 rounded text-xs">
                            <AlertTriangle className="h-3.5 w-3.5 text-warning" />
                            <span>المقال الأصلي غير متوفر حالياً في قاعدة البيانات</span>
                          </div>
                        ) : (
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                            <span className="font-medium bg-slate-100 px-2 py-0.5 rounded text-slate-800">
                              {bm.article?.source_id}
                            </span>
                            {bm.article?.published_at ? (
                              <span className="flex items-center space-x-1 space-x-reverse">
                                <Clock className="h-3.5 w-3.5" />
                                <span>
                                  {new Date(bm.article.published_at).toLocaleDateString("ar-EG")}
                                </span>
                              </span>
                            ) : (
                              <span className="text-warning">تاريخ النشر غير محدد</span>
                            )}
                            {bm.article?.reading_time_minutes && (
                              <span>~{bm.article.reading_time_minutes} دقيقة قراءة</span>
                            )}
                          </div>
                        )}

                        {/* Title */}
                        {bm.target_available && bm.article ? (
                          <h3
                            onClick={() => onSelectArticle(bm.article_id)}
                            className={`text-lg font-bold text-text hover:text-brand cursor-pointer transition-colors leading-snug ${
                              isRtl ? "text-right" : "text-left"
                            }`}
                            dir={isRtl ? "rtl" : "ltr"}
                          >
                            <bdi>{bm.article.title}</bdi>
                          </h3>
                        ) : (
                          <h3 className="text-base font-semibold text-muted font-mono">
                            المعرف المرجعي: {bm.article_id}
                          </h3>
                        )}

                        {/* Bookmark personal notes */}
                        {bm.notes && (
                          <div className="bg-slate-50 border-r-2 border-brand p-2 text-xs text-slate-700 rounded-l">
                            <span className="font-bold ml-1">ملاحظتك:</span>
                            <span>{bm.notes}</span>
                          </div>
                        )}

                        {/* Tags */}
                        {bm.tags && bm.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            {bm.tags.map((t) => (
                              <span
                                key={t}
                                className="bg-brand-light/60 text-brand text-[11px] font-medium px-2 py-0.5 rounded"
                              >
                                #{t}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex items-center space-x-2 space-x-reverse flex-shrink-0">
                        {bm.target_available && (
                          <button
                            type="button"
                            onClick={() => onSelectArticle(bm.article_id)}
                            className="p-2 text-muted hover:text-brand hover:bg-slate-100 rounded-lg transition-colors"
                            title="فتح وقراءة المقال"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleDeleteBookmark(bm.article_id)}
                          className="p-2 text-muted hover:text-negative hover:bg-red-50 rounded-lg transition-colors"
                          title="إزالة الإشارة المرجعية"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* TAB 2: SAVED QUERIES */}
      {activeTab === "queries" && (
        <section className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-base font-bold text-text">استعلامات الرصد المحفوظة</h2>
            <button
              type="button"
              onClick={() => setShowNewQueryModal(true)}
              className="inline-flex items-center space-x-1.5 space-x-reverse px-3 py-1.5 bg-brand hover:bg-brand-hover text-white rounded-lg text-xs font-semibold transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>حفظ استعلام جديد</span>
            </button>
          </div>

          {isLoadingQueries ? (
            <div className="py-12 text-center text-muted">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand" />
              <span>جاري تحميل الاستعلامات...</span>
            </div>
          ) : savedQueries.length === 0 ? (
            <div className="bg-surface border border-border rounded-xl p-12 text-center text-muted">
              <Search className="h-10 w-10 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-text mb-1">لا توجد استعلامات بحث محفوظة</h3>
              <p className="text-sm max-w-md mx-auto">
                يمكنك حفظ معايير بحثك المتكررة للوصول إليها بنقرة واحدة وتشغيلها فورياً.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {savedQueries.map((sq) => {
                const params = sq.query_params || {};
                const qTerm = (params.q as string) || "";
                const source = (params.source_id as string) || (params.source as string) || "";
                const lang = (params.language as string) || (params.lang as string) || "";

                return (
                  <div
                    key={sq.query_id}
                    className="bg-surface border border-border rounded-xl p-5 shadow-xs flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <h3 className="font-bold text-base text-text">{sq.name}</h3>
                        <button
                          type="button"
                          onClick={() => handleDeleteQuery(sq.query_id)}
                          className="text-muted hover:text-negative p-1 rounded"
                          title="حذف الاستعلام"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>

                      {/* Criteria Chips */}
                      <div className="flex flex-wrap gap-1.5 text-xs text-muted mb-4">
                        {qTerm && (
                          <span className="bg-slate-100 text-slate-800 px-2 py-0.5 rounded font-mono">
                            البحث: "{qTerm}"
                          </span>
                        )}
                        {source && (
                          <span className="bg-slate-100 text-slate-800 px-2 py-0.5 rounded">
                            المصدر: {source}
                          </span>
                        )}
                        {lang && (
                          <span className="bg-slate-100 text-slate-800 px-2 py-0.5 rounded">
                            اللغة: {lang}
                          </span>
                        )}
                        {!qTerm && !source && !lang && (
                          <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                            استعلام شامل
                          </span>
                        )}
                      </div>

                      {/* Interactive Alert Delivery Controls (Task T19) */}
                      <div className="mb-4 bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-1.5 space-x-reverse">
                            {sq.alerts_enabled ? (
                              <Bell className="h-3.5 w-3.5 text-brand ml-1" />
                            ) : (
                              <BellOff className="h-3.5 w-3.5 text-muted ml-1" />
                            )}
                            <span className="font-semibold text-text">التنبيهات المباشرة:</span>
                            <span
                              className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                                sq.alerts_enabled
                                  ? sq.is_paused
                                    ? "bg-amber-100 text-amber-800"
                                    : "bg-emerald-100 text-emerald-800"
                                  : "bg-slate-200 text-slate-600"
                              }`}
                            >
                              {!sq.alerts_enabled ? "معطلة" : sq.is_paused ? "موقوفة مؤقتاً" : "نشطة"}
                            </span>
                          </div>

                          <button
                            type="button"
                            onClick={() =>
                              handleToggleAlert(
                                sq.query_id,
                                !sq.alerts_enabled,
                                false,
                                sq.cooldown_hours || 1
                              )
                            }
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-colors ${
                              sq.alerts_enabled
                                ? "bg-slate-200 hover:bg-slate-300 text-slate-700"
                                : "bg-brand hover:bg-brand-hover text-white"
                            }`}
                          >
                            {sq.alerts_enabled ? "تعطيل" : "تفعيل"}
                          </button>
                        </div>

                        {sq.alerts_enabled && (
                          <div className="flex items-center justify-between pt-1 border-t border-slate-200/60 text-[11px] text-muted">
                            <div className="flex items-center space-x-1.5 space-x-reverse">
                              <span>فترة التهدئة:</span>
                              <select
                                value={sq.cooldown_hours || 1}
                                onChange={(e) =>
                                  handleToggleAlert(
                                    sq.query_id,
                                    true,
                                    sq.is_paused || false,
                                    Number(e.target.value)
                                  )
                                }
                                className="bg-white border border-slate-200 rounded px-1.5 py-0.5 text-[11px] text-text"
                              >
                                <option value={1}>ساعة واحدة</option>
                                <option value={6}>6 ساعات</option>
                                <option value={24}>24 ساعة</option>
                              </select>
                            </div>

                            <button
                              type="button"
                              onClick={() =>
                                handleToggleAlert(
                                  sq.query_id,
                                  true,
                                  !sq.is_paused,
                                  sq.cooldown_hours || 1
                                )
                              }
                              className="text-brand hover:underline font-semibold"
                            >
                              {sq.is_paused ? "استئناف التنبيه" : "إيقاف مؤقت"}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Run Query Action */}
                    <button
                      type="button"
                      onClick={() => onRunSavedQuery(sq.query_params)}
                      className="w-full inline-flex items-center justify-center space-x-2 space-x-reverse px-4 py-2 bg-brand text-white hover:bg-brand-hover rounded-lg text-xs font-semibold transition-colors shadow-xs"
                    >
                      <Play className="h-3.5 w-3.5" />
                      <span>تشغيل الاستعلام في الأخبار</span>
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {/* New Query Modal */}
          {showNewQueryModal && (
            <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
              <div className="bg-surface rounded-xl max-w-md w-full p-6 shadow-xl border border-border">
                <h3 className="text-lg font-bold text-text mb-4">حفظ استعلام بحث جديد</h3>
                <form onSubmit={handleCreateSavedQuery} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-text mb-1">اسم الاستعلام</label>
                    <input
                      type="text"
                      required
                      placeholder="مثلاً: متابعة أخبار الشرق الأوسط"
                      value={newQueryName}
                      onChange={(e) => setNewQueryName(e.target.value)}
                      className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-canvas focus:ring-2 focus:ring-focus outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-text mb-1">كلمات البحث</label>
                    <input
                      type="text"
                      placeholder="مثلاً: الطاقة، غزة، الذكاء الاصطناعي"
                      value={newQueryTerm}
                      onChange={(e) => setNewQueryTerm(e.target.value)}
                      className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-canvas focus:ring-2 focus:ring-focus outline-none"
                    />
                  </div>

                  <div className="flex justify-end space-x-2 space-x-reverse pt-2">
                    <button
                      type="button"
                      onClick={() => setShowNewQueryModal(false)}
                      className="px-4 py-2 border border-border rounded-lg text-xs font-medium text-muted hover:bg-slate-50"
                    >
                      إلغاء
                    </button>
                    <button
                      type="submit"
                      className="px-4 py-2 bg-brand text-white rounded-lg text-xs font-semibold hover:bg-brand-hover shadow-xs"
                    >
                      حفظ الاستعلام
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </section>
      )}

      {/* TAB 3: NOTES */}
      {activeTab === "notes" && (
        <section className="space-y-4">
          <h2 className="text-base font-bold text-text">الملاحظات والتحليلات الخاصة على المقالات</h2>

          {isLoadingNotes ? (
            <div className="py-12 text-center text-muted">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand" />
              <span>جاري تحميل الملاحظات التحليلية...</span>
            </div>
          ) : notes.length === 0 ? (
            <div className="bg-surface border border-border rounded-xl p-12 text-center text-muted">
              <FileText className="h-10 w-10 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-text mb-1">لا توجد ملاحظات تحليلية بعد</h3>
              <p className="text-sm max-w-md mx-auto">
                يمكنك كتابة ملاحظاتك الخاصة وتحليلاتك الميدانية في قسم الملاحظات داخل صفحة قراءة أي مقال.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {notes.map((n) => {
                const isRtl = n.article ? n.article.language === "ar" : true;
                return (
                  <div
                    key={n.note_id}
                    className="bg-surface border border-border rounded-xl p-5 shadow-xs"
                  >
                    <div className="flex items-start justify-between gap-4 mb-3">
                      <div>
                        {n.target_available && n.article ? (
                          <h3
                            onClick={() => onSelectArticle(n.article_id)}
                            className={`font-bold text-base text-text hover:text-brand cursor-pointer ${
                              isRtl ? "text-right" : "text-left"
                            }`}
                            dir={isRtl ? "rtl" : "ltr"}
                          >
                            <bdi>{n.article.title}</bdi>
                          </h3>
                        ) : (
                          <div className="text-xs text-amber-700 font-mono bg-amber-50 px-2 py-0.5 rounded inline-block">
                            المقال الأصلي غير متوفر ({n.article_id})
                          </div>
                        )}
                        <span className="text-[11px] text-muted">
                          آخر تحديث: {new Date(n.updated_at).toLocaleString("ar-EG")}
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleDeleteNote(n.article_id)}
                        className="text-muted hover:text-negative p-1 rounded"
                        title="حذف الملاحظة"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>

                    {/* Note Content */}
                    <div className="bg-canvas border border-border rounded-lg p-3 text-sm text-text leading-relaxed whitespace-pre-wrap">
                      {n.content}
                    </div>

                    {n.target_available && (
                      <div className="mt-3 flex justify-end">
                        <button
                          type="button"
                          onClick={() => onSelectArticle(n.article_id)}
                          className="text-xs font-semibold text-brand hover:underline inline-flex items-center space-x-1 space-x-reverse"
                        >
                          <span>فتح المقال في القارئ لتعديل الملاحظة</span>
                          <ExternalLink className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
