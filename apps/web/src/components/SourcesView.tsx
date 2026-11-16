import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Source } from "../types/api";
import { AlertCircle, CheckCircle, ExternalLink, Globe, Lock } from "lucide-react";

export function SourcesView() {
  const [sources, setSources] = useState<Source[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const list = await api.listSources();
        setSources(list);
      } catch (err) {
        setError("فشل تحميل قائمة المصادر المعتمدة.");
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-200 rounded w-1/4"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-32 bg-slate-200 rounded-xl"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <AlertCircle className="h-8 w-8 text-negative mx-auto mb-2" />
          <p className="text-negative font-medium">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-text">المصادر الإخبارية المعتمدة (8 مصادر حقيقية)</h1>
        <p className="text-sm text-muted mt-1">
          جميع المصادر تبدأ معطلة افتراضياً لحماية السياسة والشبكة، مع تطبيق قيود SSRF الصارمة على مستوى النطاق وIP.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sources.map((s) => (
          <div
            key={s.source_id}
            className="bg-surface border border-border rounded-xl p-5 shadow-sm flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="font-mono font-bold text-sm text-text bg-slate-100 px-2 py-0.5 rounded">
                  {s.source_id}
                </span>
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                    s.enabled
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {s.enabled ? (
                    <>
                      <CheckCircle className="h-3 w-3 ml-1 text-positive" />
                      مفعل للجمع
                    </>
                  ) : (
                    <>
                      <Lock className="h-3 w-3 ml-1 text-slate-400" />
                      معطل (Default)
                    </>
                  )}
                </span>
              </div>

              <h3 className="text-lg font-bold text-text mb-1">{s.name}</h3>

              <div className="flex items-center space-x-2 space-x-reverse text-xs text-muted mb-4">
                <Globe className="h-3.5 w-3.5 text-slate-400" />
                <span>اللغة: {s.language.toUpperCase()}</span>
                <span>•</span>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand hover:underline flex items-center space-x-1 space-x-reverse"
                >
                  <span>زيارة الموقع</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>

            <div className="bg-canvas border border-border rounded-lg p-3 text-xs text-muted space-y-1.5">
              <div className="flex justify-between">
                <span>سقف الطلبات:</span>
                <span className="font-mono text-text font-medium">
                  {s.policy.rate_limit_per_minute} طلب/دقيقة
                </span>
              </div>
              <div className="flex justify-between">
                <span>مدة الاحتفاظ بالبيانات:</span>
                <span className="font-mono text-text font-medium">{s.policy.retention_days} يوم</span>
              </div>
              <div className="flex justify-between">
                <span>أرشفة HTML الخام:</span>
                <span className="font-medium text-text">
                  {s.policy.allow_raw_storage ? "مفعل محلياً" : "معطل"}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
