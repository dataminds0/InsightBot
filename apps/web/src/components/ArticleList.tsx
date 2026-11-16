import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "../context/AuthContext";
import { api, ApiClientError } from "../lib/api";
import type { ArticleListItem, Source } from "../types/api";
import { ArticleCard } from "./ArticleCard";
import {
  AlertCircle,
  BookmarkPlus,
  Check,
  ChevronLeft,
  ChevronRight,
  Filter,
  RefreshCw,
  RotateCcw,
  Search,
  Tag,
  X,
} from "lucide-react";

export interface ArticleFilterParams {
  q?: string;
  source?: string;
  source_id?: string;
  lang?: string;
  language?: string;
  unknown_date?: boolean;
  include_unknown_date?: boolean;
}

interface ArticleListProps {
  onSelectArticle: (articleId: string) => void;
  initialFilters?: ArticleFilterParams | null;
}

export function ArticleList({ onSelectArticle, initialFilters }: ArticleListProps) {
  const { user } = useAuth();
  const isAnalystOrAdmin = user?.role === "Admin" || user?.role === "Analyst";

  // Read initial filters from props or URL query parameters (Shareable links)
  const getInitialFilters = () => {
    if (initialFilters) {
      return {
        q: initialFilters.q || "",
        source: initialFilters.source || initialFilters.source_id || "",
        lang: initialFilters.lang || initialFilters.language || "",
        unknownDate:
          initialFilters.unknown_date !== undefined
            ? initialFilters.unknown_date
            : initialFilters.include_unknown_date !== undefined
            ? initialFilters.include_unknown_date
            : true,
      };
    }
    if (typeof window === "undefined") {
      return { q: "", source: "", lang: "", unknownDate: true };
    }
    const params = new URLSearchParams(window.location.search);
    return {
      q: params.get("q") || "",
      source: params.get("source") || params.get("source_id") || "",
      lang: params.get("lang") || params.get("language") || "",
      unknownDate: params.get("unknown_date") !== "false",
    };
  };

  const initial = getInitialFilters();
  const [searchQuery, setSearchQuery] = useState(initial.q);
  const [selectedSource, setSelectedSource] = useState(initial.source);
  const [selectedLang, setSelectedLang] = useState(initial.lang);
  const [includeUnknownDate, setIncludeUnknownDate] = useState(initial.unknownDate);

  // Saved Query Modal State
  const [showSaveQueryModal, setShowSaveQueryModal] = useState(false);
  const [saveQueryName, setSaveQueryName] = useState("");
  const [isSavingQuery, setIsSavingQuery] = useState(false);
  const [saveSuccessNotice, setSaveSuccessNotice] = useState<string | null>(null);

  const [articles, setArticles] = useState<ArticleListItem[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<string[]>([]);
  const [currentCursor, setCurrentCursor] = useState<string | undefined>(undefined);

  // States
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Inflight request cancellation ref
  const abortControllerRef = useRef<AbortController | null>(null);

  // Synchronize URL with active filters (without full page reload)
  const syncUrlParams = (q: string, source: string, lang: string, unknownDate: boolean) => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (source) params.set("source", source);
    if (lang) params.set("lang", lang);
    if (!unknownDate) params.set("unknown_date", "false");

    const qs = params.toString();
    const newUrl = qs ? `/?${qs}` : "/";
    window.history.replaceState({}, "", newUrl);
  };

  // React to external initialFilters updates (e.g. from Saved Queries in Workspace)
  useEffect(() => {
    if (initialFilters) {
      const q = initialFilters.q || "";
      const s = initialFilters.source || initialFilters.source_id || "";
      const l = initialFilters.lang || initialFilters.language || "";
      const u =
        initialFilters.unknown_date !== undefined
          ? initialFilters.unknown_date
          : initialFilters.include_unknown_date !== undefined
          ? initialFilters.include_unknown_date
          : true;
      setSearchQuery(q);
      setSelectedSource(s);
      setSelectedLang(l);
      setIncludeUnknownDate(u);
      syncUrlParams(q, s, l, u);
      setCurrentCursor(undefined);
      setCursorHistory([]);
    }
  }, [initialFilters]);

  // Fetch sources once for filter dropdown
  useEffect(() => {
    async function loadSources() {
      try {
        const sList = await api.listSources();
        setSources(sList);
      } catch {
        // Handled silently
      }
    }
    loadSources();
  }, []);

  const handleSaveQuery = async (e: FormEvent) => {
    e.preventDefault();
    if (!saveQueryName.trim()) return;
    setIsSavingQuery(true);
    try {
      await api.createSavedQuery({
        name: saveQueryName.trim(),
        query_params: {
          q: searchQuery,
          source_id: selectedSource,
          language: selectedLang,
          include_unknown_date: includeUnknownDate,
        },
        alerts_enabled: false,
      });
      setShowSaveQueryModal(false);
      setSaveQueryName("");
      setSaveSuccessNotice("تم حفظ الاستعلام في مساحة عملك بنجاح!");
      setTimeout(() => setSaveSuccessNotice(null), 3500);
    } catch {
      // Non-blocking
    } finally {
      setIsSavingQuery(false);
    }
  };

  const loadArticles = async (cursor?: string, isBackground = false) => {
    // Abort previous inflight request to avoid race conditions
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (isBackground) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    setError(null);

    try {
      const res = await api.listArticles(
        {
          q: searchQuery.trim() || undefined,
          source_id: selectedSource || undefined,
          language: selectedLang || undefined,
          include_unknown_date: includeUnknownDate,
          cursor: cursor,
          limit: 12,
        },
        controller.signal
      );

      setArticles(res.items);
      setTotalCount(res.total_count);
      setNextCursor(res.next_cursor || null);
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        return; // Request was cleanly cancelled, ignore
      }
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل الاتصال بالخادم لجلب قائمة المقالات.");
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  // Trigger search and update URL on filter changes
  useEffect(() => {
    syncUrlParams(searchQuery, selectedSource, selectedLang, includeUnknownDate);
    setCurrentCursor(undefined);
    setCursorHistory([]);
    loadArticles(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSource, selectedLang, includeUnknownDate]);

  const handleSearchSubmit = (e: FormEvent) => {
    e.preventDefault();
    syncUrlParams(searchQuery, selectedSource, selectedLang, includeUnknownDate);
    setCurrentCursor(undefined);
    setCursorHistory([]);
    loadArticles(undefined);
  };

  const handleNextPage = () => {
    if (!nextCursor) return;
    setCursorHistory((prev) => [...prev, currentCursor || ""]);
    setCurrentCursor(nextCursor);
    loadArticles(nextCursor);
  };

  const handlePrevPage = () => {
    if (cursorHistory.length === 0) return;
    const prevCursor = cursorHistory[cursorHistory.length - 1];
    setCursorHistory((prev) => prev.slice(0, -1));
    const targetCursor = prevCursor === "" ? undefined : prevCursor;
    setCurrentCursor(targetCursor);
    loadArticles(targetCursor);
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setSelectedSource("");
    setSelectedLang("");
    setIncludeUnknownDate(true);
    syncUrlParams("", "", "", true);
    setCurrentCursor(undefined);
    setCursorHistory([]);
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

  const hasActiveFilters = Boolean(
    searchQuery || selectedSource || selectedLang || !includeUnknownDate
  );

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
      {/* Search & Filter Bar */}
      <div className="bg-surface border border-border rounded-xl p-5 mb-8 shadow-sm">
        <form onSubmit={handleSearchSubmit} className="flex flex-col md:flex-row gap-4 mb-4">
          {/* Keyword Search */}
          <div className="flex-1 relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="البحث في عناوين الأخبار المجمعة..."
              className="w-full pr-10 pl-10 py-2.5 border border-border rounded-lg text-sm focus:ring-2 focus:ring-focus focus:border-focus bg-canvas text-text"
            />
            <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-muted">
              <Search className="h-4 w-4" />
            </div>
            {searchQuery && (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery("");
                  syncUrlParams("", selectedSource, selectedLang, includeUnknownDate);
                }}
                className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted hover:text-text"
                title="مسح البحث"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Source Dropdown */}
          <div className="w-full md:w-56">
            <select
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              className="w-full py-2.5 px-3 border border-border rounded-lg text-sm bg-canvas text-text focus:ring-2 focus:ring-focus"
            >
              <option value="">جميع المصادر (8 معتمدة)</option>
              {sources.map((s) => (
                <option key={s.source_id} value={s.source_id}>
                  {s.name} ({s.source_id})
                </option>
              ))}
            </select>
          </div>

          {/* Search Button */}
          <button
            type="submit"
            className="px-5 py-2.5 bg-brand hover:bg-brand-hover text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center space-x-2 space-x-reverse"
          >
            <Search className="h-4 w-4" />
            <span>بحث</span>
          </button>
        </form>

        {/* Filter Controls Row */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-100 text-xs">
          {/* Language Selector */}
          <div className="flex items-center space-x-2 space-x-reverse">
            <span className="text-muted font-medium ml-1">اللغة:</span>
            {[
              { id: "", label: "الكل" },
              { id: "ar", label: "العربية" },
              { id: "en", label: "English" },
              { id: "ru", label: "Русский" },
            ].map((lang) => (
              <button
                key={lang.id}
                type="button"
                onClick={() => setSelectedLang(lang.id)}
                className={`px-2.5 py-1 rounded-full font-medium transition-colors ${
                  selectedLang === lang.id
                    ? "bg-brand text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                {lang.label}
              </button>
            ))}
          </div>

          {/* Unknown Date Toggle */}
          <div className="flex items-center space-x-4 space-x-reverse">
            <label className="flex items-center space-x-2 space-x-reverse cursor-pointer">
              <input
                type="checkbox"
                checked={includeUnknownDate}
                onChange={(e) => setIncludeUnknownDate(e.target.checked)}
                className="rounded border-border text-brand focus:ring-focus h-4 w-4"
              />
              <span className="text-muted">تضمين التواريخ غير المحددة</span>
            </label>
          </div>
        </div>

        {/* Active Filter Chips Bar (بطاقات المرشحات النشطة) */}
        {hasActiveFilters && (
          <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center gap-2">
            <div className="flex items-center space-x-1.5 space-x-reverse text-xs text-muted font-semibold ml-2">
              <Tag className="h-3.5 w-3.5 text-brand" />
              <span>المرشحات النشطة:</span>
            </div>

            {searchQuery && (
              <span className="inline-flex items-center space-x-1 space-x-reverse bg-brand-light text-brand px-2.5 py-1 rounded-full text-xs font-medium border border-brand/20">
                <span>بحث: "{searchQuery}"</span>
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery("");
                    syncUrlParams("", selectedSource, selectedLang, includeUnknownDate);
                  }}
                  className="hover:text-brand-hover p-0.5 rounded-full"
                  title="إزالة مرشح البحث"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}

            {selectedSource && (
              <span className="inline-flex items-center space-x-1 space-x-reverse bg-brand-light text-brand px-2.5 py-1 rounded-full text-xs font-medium border border-brand/20">
                <span>المصدر: {selectedSource}</span>
                <button
                  type="button"
                  onClick={() => setSelectedSource("")}
                  className="hover:text-brand-hover p-0.5 rounded-full"
                  title="إزالة مرشح المصدر"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}

            {selectedLang && (
              <span className="inline-flex items-center space-x-1 space-x-reverse bg-brand-light text-brand px-2.5 py-1 rounded-full text-xs font-medium border border-brand/20">
                <span>اللغة: {getLanguageLabel(selectedLang)}</span>
                <button
                  type="button"
                  onClick={() => setSelectedLang("")}
                  className="hover:text-brand-hover p-0.5 rounded-full"
                  title="إزالة مرشح اللغة"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}

            {!includeUnknownDate && (
              <span className="inline-flex items-center space-x-1 space-x-reverse bg-amber-50 text-amber-800 px-2.5 py-1 rounded-full text-xs font-medium border border-amber-200">
                <span>استبعاد التواريخ غير المحددة</span>
                <button
                  type="button"
                  onClick={() => setIncludeUnknownDate(true)}
                  className="hover:text-amber-950 p-0.5 rounded-full"
                  title="إعادة تضمين التواريخ المجهولة"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}

            <button
              type="button"
              onClick={handleResetFilters}
              className="text-xs text-muted hover:text-negative font-medium flex items-center space-x-1 space-x-reverse mr-2 underline"
            >
              <RotateCcw className="h-3 w-3" />
              <span>إعادة ضبط الكل</span>
            </button>

            {isAnalystOrAdmin && (
              <button
                type="button"
                onClick={() => setShowSaveQueryModal(true)}
                className="inline-flex items-center space-x-1 space-x-reverse text-xs text-brand hover:underline font-semibold bg-brand-light/60 px-3 py-1 rounded-full border border-brand/20 mr-auto"
              >
                <BookmarkPlus className="h-3.5 w-3.5" />
                <span>حفظ هذا البحث في مساحة العمل</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Save Query Confirmation Notice */}
      {saveSuccessNotice && (
        <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs flex items-center space-x-2 space-x-reverse font-medium">
          <Check className="h-4 w-4 text-positive" />
          <span>{saveSuccessNotice}</span>
        </div>
      )}

      {/* Results Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2 space-x-reverse text-sm text-muted">
          <span>نتائج البحث:</span>
          <strong className="text-text font-bold">{totalCount}</strong>
          <span>مقال مؤرشف</span>
          {isRefreshing && (
            <span className="flex items-center space-x-1 space-x-reverse text-brand text-xs">
              <RefreshCw className="h-3 w-3 animate-spin" />
              <span>تحديث في الخلفية...</span>
            </span>
          )}
        </div>
      </div>

      {/* Screen States */}
      {/* 1. Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="bg-surface border border-border rounded-xl p-5 shadow-sm animate-pulse h-48 flex flex-col justify-between">
              <div>
                <div className="flex justify-between mb-3">
                  <div className="h-4 w-20 bg-slate-200 rounded"></div>
                  <div className="h-4 w-12 bg-slate-200 rounded"></div>
                </div>
                <div className="h-5 bg-slate-200 rounded w-full mb-2"></div>
                <div className="h-5 bg-slate-200 rounded w-4/5"></div>
              </div>
              <div className="h-4 bg-slate-100 rounded w-1/3"></div>
            </div>
          ))}
        </div>
      )}

      {/* 2. Network Error State */}
      {!isLoading && error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center my-6" role="alert">
          <AlertCircle className="h-10 w-10 text-negative mx-auto mb-3" />
          <h3 className="text-lg font-bold text-negative mb-2">فشل تحميل المقالات</h3>
          <p className="text-sm text-muted mb-4">{error}</p>
          <button
            type="button"
            onClick={() => loadArticles(currentCursor)}
            className="px-4 py-2 bg-white border border-border text-sm font-medium rounded-lg text-text hover:bg-slate-50 transition-colors"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      {/* 3. Genuine Empty State */}
      {!isLoading && !error && articles.length === 0 && (
        <div className="bg-surface border border-border rounded-xl p-12 text-center my-6 shadow-sm">
          <div className="h-12 w-12 bg-slate-100 text-muted rounded-full flex items-center justify-center mx-auto mb-4">
            <Filter className="h-6 w-6" />
          </div>
          <h3 className="text-lg font-bold text-text mb-2">لا توجد مقالات مطابقة للبحث</h3>
          <p className="text-sm text-muted max-w-md mx-auto mb-6">
            لم يتم العثور على أي مقالات تطابق شروط التصفية المحددة. جرب تغيير كلمة البحث أو توسيع نطاق المصادر.
          </p>
          <button
            type="button"
            onClick={handleResetFilters}
            className="px-4 py-2 bg-brand text-white text-sm font-medium rounded-lg hover:bg-brand-hover transition-colors"
          >
            إعادة ضبط جميع المرشحات
          </button>
        </div>
      )}

      {/* 4. Loaded Articles Grid */}
      {!isLoading && !error && articles.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {articles.map((art) => (
              <ArticleCard key={art.article_id} article={art} onSelect={onSelectArticle} />
            ))}
          </div>

          {/* Cursor Pagination Controls */}
          <div className="mt-8 flex items-center justify-between border-t border-border pt-4">
            <button
              type="button"
              disabled={cursorHistory.length === 0}
              onClick={handlePrevPage}
              className="inline-flex items-center space-x-1.5 space-x-reverse px-4 py-2 border border-border rounded-lg text-sm font-medium text-text bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronRight className="h-4 w-4" />
              <span>الصفحة السابقة</span>
            </button>

            <span className="text-xs text-muted">
              عرض {articles.length} من أصل {totalCount}
            </span>

            <button
              type="button"
              disabled={!nextCursor}
              onClick={handleNextPage}
              className="inline-flex items-center space-x-1.5 space-x-reverse px-4 py-2 border border-border rounded-lg text-sm font-medium text-text bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>الصفحة التالية</span>
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        </>
      )}

      {/* Modal to Save Query */}
      {showSaveQueryModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-surface rounded-xl max-w-md w-full p-6 shadow-xl border border-border">
            <h3 className="text-base font-bold text-text mb-2">حفظ البحث في مساحة العمل</h3>
            <p className="text-xs text-muted mb-4 leading-relaxed">
              سيتم حفظ معايير هذا البحث ({searchQuery ? `"${searchQuery}"` : "المرشحات النشطة"}) لتتمكن من إعادة تشغيله ومتابعته بنقرة واحدة في أي وقت.
            </p>
            <form onSubmit={handleSaveQuery} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-text mb-1">اسم الاستعلام</label>
                <input
                  type="text"
                  required
                  autoFocus
                  placeholder="مثلاً: متابعة أحداث غزة، أخبار الطاقة..."
                  value={saveQueryName}
                  onChange={(e) => setSaveQueryName(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm bg-canvas focus:ring-2 focus:ring-focus outline-none"
                />
              </div>
              <div className="flex justify-end space-x-2 space-x-reverse pt-2">
                <button
                  type="button"
                  onClick={() => setShowSaveQueryModal(false)}
                  className="px-4 py-2 border border-border rounded-lg text-xs font-medium text-muted hover:bg-slate-50"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={isSavingQuery || !saveQueryName.trim()}
                  className="px-4 py-2 bg-brand text-white rounded-lg text-xs font-semibold hover:bg-brand-hover disabled:opacity-50 shadow-xs"
                >
                  {isSavingQuery ? "جاري الحفظ..." : "حفظ في مساحة العمل"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
