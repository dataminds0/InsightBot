import { useEffect, useState } from "react";
import { api, ApiClientError } from "../lib/api";
import type { AnalyticsOverviewReport, ExportFormat } from "../types/api";
import {
  AlertCircle,
  BarChart3,
  Calendar,
  Clock,
  Download,
  FileSpreadsheet,
  Globe,
  Layers,
  Newspaper,
  RefreshCw,
  ShieldCheck,
  Table as TableIcon,
} from "lucide-react";

export function AnalyticsView() {
  const [report, setReport] = useState<AnalyticsOverviewReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Accessible Table Toggle (WCAG 2.2 AA Requirement)
  const [showTableMode, setShowTableMode] = useState(false);

  // Export State
  const [exportFormat, setExportFormat] = useState<ExportFormat>("csv");
  const [exportTarget, setExportTarget] = useState<"articles" | "stories">("articles");
  const [exportLimit, setExportLimit] = useState<number>(500);

  const loadAnalytics = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getAnalyticsOverview();
      setReport(data);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("فشل تحميل مؤشرات وإحصاءات المنصة.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  const handleDownloadExport = () => {
    let url = "";
    if (exportTarget === "articles") {
      url = api.getArticlesExportUrl({ format: exportFormat, limit: exportLimit });
    } else {
      url = api.getStoriesExportUrl({ format: exportFormat, limit: exportLimit });
    }
    window.open(url, "_blank");
  };

  const getLanguageLabel = (code: string) => {
    switch (code.toLowerCase()) {
      case "ar":
        return "العربية";
      case "en":
        return "English";
      case "ru":
        return "Русский";
      default:
        return code.toUpperCase();
    }
  };

  const getStatusLabel = (st: string) => {
    switch (st.toLowerCase()) {
      case "emerging":
        return "حدث عاجل أولي (Emerging)";
      case "peak":
        return "ذروة التغطية (Peak)";
      case "declining":
        return "تراجع واستقرار (Declining)";
      case "closed":
        return "مغلقة (Closed)";
      default:
        return st;
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
      {/* Page Header */}
      <div className="bg-surface border border-border rounded-xl p-6 mb-8 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-3 space-x-reverse">
            <div className="p-3 bg-brand-light rounded-xl text-brand">
              <BarChart3 className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2 space-x-reverse">
                <h1 className="text-xl font-bold text-text">التحليلات ومؤشرات التغطية والتقارير</h1>
                <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono">T17</span>
              </div>
              <p className="text-xs text-muted mt-1">
                رصد إحصائي لحجم الأخبار، حصة المصادر المعتمدة، فوارق التحديث الزمني، وتصدير البيانات المؤمن ضد الثغرات.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2 space-x-reverse">
            <button
              type="button"
              onClick={() => setShowTableMode(!showTableMode)}
              className={`px-3 py-2 rounded-lg text-xs font-semibold flex items-center space-x-1.5 space-x-reverse border transition-colors ${
                showTableMode
                  ? "bg-brand text-white border-brand"
                  : "bg-surface border-border text-text hover:bg-slate-50"
              }`}
              title="التبديل بين الرسوم البيانية والجداول النصية سهلة الوصول"
            >
              <TableIcon className="h-4 w-4" />
              <span>{showTableMode ? "عرض الرسوم البيانية" : "عرض الجداول النصية (WCAG)"}</span>
            </button>

            <button
              type="button"
              onClick={loadAnalytics}
              className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-text rounded-lg text-xs font-semibold flex items-center space-x-1.5 space-x-reverse transition-colors"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
              <span>تحديث المؤشرات</span>
            </button>
          </div>
        </div>
      </div>

      {/* Screen States */}
      {isLoading && (
        <div className="bg-surface border border-border rounded-xl p-16 text-center my-6 shadow-sm">
          <RefreshCw className="h-8 w-8 text-brand animate-spin mx-auto mb-4" />
          <h3 className="text-base font-bold text-text mb-1">جاري تجميع المؤشرات الإحصائية...</h3>
          <p className="text-xs text-muted">حساب حصص المصادر، متوسطات التأخر الزمني، والتوزيع اللغوي للأرشيف.</p>
        </div>
      )}

      {!isLoading && error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center my-6" role="alert">
          <AlertCircle className="h-10 w-10 text-negative mx-auto mb-3" />
          <h3 className="text-lg font-bold text-negative mb-2">فشل تحميل التحليلات</h3>
          <p className="text-sm text-muted mb-4">{error}</p>
          <button
            type="button"
            onClick={loadAnalytics}
            className="px-4 py-2 bg-white border border-border text-sm font-medium rounded-lg text-text hover:bg-slate-50 transition-colors"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      {!isLoading && !error && report && (
        <div className="space-y-8">
          {/* Key Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-surface border border-border rounded-xl p-5 shadow-xs">
              <span className="text-xs text-muted block mb-1">إجمالي المقالات المؤرشفة</span>
              <div className="flex items-center space-x-2 space-x-reverse">
                <Newspaper className="h-5 w-5 text-brand" />
                <span className="text-2xl font-bold text-text">{report.total_articles.toLocaleString("ar-EG")}</span>
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-5 shadow-xs">
              <span className="text-xs text-muted block mb-1">المصادر المعتمدة النشطة</span>
              <div className="flex items-center space-x-2 space-x-reverse">
                <Globe className="h-5 w-5 text-brand" />
                <span className="text-2xl font-bold text-text">{report.total_sources}</span>
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-5 shadow-xs">
              <span className="text-xs text-muted block mb-1">أحداث وقصص مجمعة</span>
              <div className="flex items-center space-x-2 space-x-reverse">
                <Layers className="h-5 w-5 text-brand" />
                <span className="text-2xl font-bold text-text">{report.total_stories}</span>
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-5 shadow-xs">
              <span className="text-xs text-muted block mb-1">تواريخ غير محددة (Defect A13)</span>
              <div className="flex items-center space-x-2 space-x-reverse">
                <Clock className="h-5 w-5 text-amber-600" />
                <span className="text-2xl font-bold text-amber-900">
                  {report.unknown_publication_date_count.toLocaleString("ar-EG")}
                </span>
              </div>
            </div>
          </div>

          {/* Section 1: Source Coverage & Distribution */}
          <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
            <h2 className="text-base font-bold text-text mb-4 flex items-center space-x-2 space-x-reverse">
              <Newspaper className="h-5 w-5 text-brand" />
              <span>توزيع التغطية الإخبارية حسب المصدر</span>
            </h2>

            {!showTableMode ? (
              <div className="space-y-4">
                {report.source_coverage.map((sc) => (
                  <div key={sc.source_id} className="space-y-1.5">
                    <div className="flex justify-between items-center text-xs">
                      <div className="flex items-center space-x-2 space-x-reverse">
                        <span className="font-bold text-text">{sc.name || sc.source_id}</span>
                        <span className="text-muted font-mono text-[11px]">({sc.source_id})</span>
                      </div>
                      <div className="flex items-center space-x-3 space-x-reverse font-mono text-[11px]">
                        <span>{sc.article_count} مقال ({sc.percentage}%)</span>
                        {sc.publishing_lag_minutes !== null && (
                          <span className="text-muted" title="متوسط الفارق الزمني بين وقت النشر ووقت الجمع">
                            تأخر: {sc.publishing_lag_minutes} دقيقة
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                      <div
                        className="bg-brand h-2.5 rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(100, Math.max(2, sc.percentage))}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-right border-collapse">
                  <thead>
                    <tr className="border-b border-border bg-canvas text-muted">
                      <th className="py-2.5 px-3 font-semibold">المصدر</th>
                      <th className="py-2.5 px-3 font-semibold">معرف المصدر</th>
                      <th className="py-2.5 px-3 font-semibold">عدد المقالات</th>
                      <th className="py-2.5 px-3 font-semibold">النسبة المئوية</th>
                      <th className="py-2.5 px-3 font-semibold">متوسط الكلمات</th>
                      <th className="py-2.5 px-3 font-semibold">متوسط زمن القراءة</th>
                      <th className="py-2.5 px-3 font-semibold">متوسط تأخر النشر</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.source_coverage.map((sc) => (
                      <tr key={sc.source_id} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-bold text-text">{sc.name || sc.source_id}</td>
                        <td className="py-2.5 px-3 font-mono text-muted">{sc.source_id}</td>
                        <td className="py-2.5 px-3 font-bold">{sc.article_count}</td>
                        <td className="py-2.5 px-3 font-mono">{sc.percentage}%</td>
                        <td className="py-2.5 px-3">{sc.average_word_count} كلمة</td>
                        <td className="py-2.5 px-3">{sc.average_reading_time_minutes} د</td>
                        <td className="py-2.5 px-3 font-mono">
                          {sc.publishing_lag_minutes !== null ? `${sc.publishing_lag_minutes} د` : "غير محدد"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Section 2: Language & Story Distributions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Language Distribution */}
            <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
              <h2 className="text-base font-bold text-text mb-4 flex items-center space-x-2 space-x-reverse">
                <Globe className="h-5 w-5 text-brand" />
                <span>التوزيع اللغوي للمحتوى</span>
              </h2>

              <div className="space-y-4">
                {report.language_distribution.map((ld) => (
                  <div key={ld.language} className="space-y-1.5">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-bold text-text">{getLanguageLabel(ld.language)}</span>
                      <span className="font-mono text-muted">{ld.count} مقال ({ld.percentage}%)</span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                      <div
                        className="bg-emerald-600 h-2.5 rounded-full"
                        style={{ width: `${Math.min(100, Math.max(2, ld.percentage))}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Story Lifecycle Distribution */}
            <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
              <h2 className="text-base font-bold text-text mb-4 flex items-center space-x-2 space-x-reverse">
                <Layers className="h-5 w-5 text-brand" />
                <span>دورة حياة القصص والأحداث</span>
              </h2>

              <div className="space-y-4">
                {report.story_status_distribution.map((sd) => (
                  <div key={sd.status} className="space-y-1.5">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-bold text-text">{getStatusLabel(sd.status)}</span>
                      <span className="font-mono text-muted">{sd.count} قصة ({sd.percentage}%)</span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                      <div
                        className="bg-amber-600 h-2.5 rounded-full"
                        style={{ width: `${Math.min(100, Math.max(2, sd.percentage))}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Section 3: 30-Day Timeline Trend */}
          {report.timeline_trend.length > 0 && (
            <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
              <h2 className="text-base font-bold text-text mb-4 flex items-center space-x-2 space-x-reverse">
                <Calendar className="h-5 w-5 text-brand" />
                <span>الاتجاه الزمني لحجم الأرشفة (آخر 30 يوماً)</span>
              </h2>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-right border-collapse">
                  <thead>
                    <tr className="border-b border-border bg-canvas text-muted">
                      <th className="py-2 px-3 font-semibold">التاريخ</th>
                      <th className="py-2 px-3 font-semibold">عدد المقالات</th>
                      <th className="py-2 px-3 font-semibold">المصادر المساهمة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.timeline_trend.map((tp) => (
                      <tr key={tp.date} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-2 px-3 font-mono font-bold text-text">{tp.date}</td>
                        <td className="py-2 px-3 font-bold text-brand">{tp.count}</td>
                        <td className="py-2 px-3 font-mono text-[11px] text-muted">
                          {Object.entries(tp.sources_breakdown)
                            .map(([s, c]) => `${s}: ${c}`)
                            .join(" | ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Section 4: Data Export Center (مركز تصدير البيانات) */}
          <div className="bg-surface border border-border rounded-xl p-6 shadow-sm">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-border">
              <div>
                <div className="flex items-center space-x-2 space-x-reverse">
                  <Download className="h-5 w-5 text-brand" />
                  <h2 className="text-base font-bold text-text">مركز التصدير والتقارير المقيدة</h2>
                </div>
                <p className="text-xs text-muted mt-1">
                  تصدير حزم مقيدة من المقالات أو القصص بصيغ CSV وJSONL وMarkdown مع حماية كاملة ضد ثغرات حقن المعادلات.
                </p>
              </div>

              {/* Formula Protection Badge */}
              <div className="flex items-center space-x-1.5 space-x-reverse bg-emerald-50 text-emerald-800 border border-emerald-200 px-3 py-1.5 rounded-lg text-xs font-semibold">
                <ShieldCheck className="h-4 w-4 text-positive" />
                <span>محمي ضد حقن معادلات CSV (CWE-1236)</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <label className="block text-xs font-semibold text-text mb-1">البيانات المراد تصديرها:</label>
                <select
                  value={exportTarget}
                  onChange={(e) => setExportTarget(e.target.value as "articles" | "stories")}
                  className="w-full py-2 px-3 border border-border rounded-lg text-xs bg-canvas focus:ring-2 focus:ring-focus font-medium"
                >
                  <option value="articles">المقالات المؤرشفة (Articles)</option>
                  <option value="stories">عناقيد القصص والأحداث (Stories)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text mb-1">صيغة الملف:</label>
                <select
                  value={exportFormat}
                  onChange={(e) => setExportFormat(e.target.value as ExportFormat)}
                  className="w-full py-2 px-3 border border-border rounded-lg text-xs bg-canvas focus:ring-2 focus:ring-focus font-medium"
                >
                  <option value="csv">ملف جداول CSV (مع الحماية)</option>
                  <option value="jsonl">ملف كائنات JSON Lines (JSONL)</option>
                  <option value="markdown">تقرير منسق Markdown (.md)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text mb-1">الحد الأقصى للعناصر:</label>
                <select
                  value={exportLimit}
                  onChange={(e) => setExportLimit(Number(e.target.value))}
                  className="w-full py-2 px-3 border border-border rounded-lg text-xs bg-canvas focus:ring-2 focus:ring-focus font-medium"
                >
                  <option value={100}>100 عنصر</option>
                  <option value={250}>250 عنصر</option>
                  <option value={500}>500 عنصر (الافتراضي)</option>
                  <option value={1000}>1000 عنصر (الحد الأقصى)</option>
                </select>
              </div>

              <div>
                <button
                  type="button"
                  onClick={handleDownloadExport}
                  className="w-full py-2.5 px-4 bg-brand hover:bg-brand-hover text-white rounded-lg text-xs font-semibold flex items-center justify-center space-x-1.5 space-x-reverse transition-colors shadow-xs"
                >
                  <FileSpreadsheet className="h-4 w-4" />
                  <span>بدء التصدير والتحميل المباشر</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
