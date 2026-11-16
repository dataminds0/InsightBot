import { useEffect, useState } from "react";
import { api, ApiClientError } from "../lib/api";
import type { AuditLog, Job, SourceHealthItem, User } from "../types/api";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Clock,
  History,
  Lock,
  Play,
  RefreshCw,
  RotateCcw,
  Shield,
  Users,
  XCircle,
} from "lucide-react";

export function AdminView() {
  const [activeSubTab, setActiveSubTab] = useState<"users" | "sources" | "jobs" | "audit">("users");

  // State: Users
  const [users, setUsers] = useState<User[]>([]);
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [userActionError, setUserActionError] = useState<string | null>(null);

  // State: Sources Health
  const [sourcesHealth, setSourcesHealth] = useState<SourceHealthItem[]>([]);
  const [isSourcesLoading, setIsSourcesLoading] = useState(false);

  // State: Jobs
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobStats, setJobStats] = useState<Record<string, number>>({});
  const [jobFilterStatus, setJobFilterStatus] = useState<string>("");
  const [isJobsLoading, setIsJobsLoading] = useState(false);

  // State: Audit
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [isAuditLoading, setIsAuditLoading] = useState(false);

  // Common notification
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 3500);
  };

  // Load Users
  const loadUsers = async () => {
    setIsUsersLoading(true);
    setUserActionError(null);
    try {
      const list = await api.listUsers();
      setUsers(list);
    } catch (err) {
      if (err instanceof ApiClientError) setUserActionError(err.message);
    } finally {
      setIsUsersLoading(false);
    }
  };

  // Load Sources Health
  const loadSourcesHealth = async () => {
    setIsSourcesLoading(true);
    try {
      const list = await api.getSourcesHealth();
      setSourcesHealth(list);
    } catch {
      // Ignored
    } finally {
      setIsSourcesLoading(false);
    }
  };

  // Load Jobs
  const loadJobs = async () => {
    setIsJobsLoading(true);
    try {
      const res = await api.listJobs({
        status: jobFilterStatus || undefined,
        limit: 50,
      });
      setJobs(res.jobs);
      setJobStats(res.stats);
    } catch {
      // Ignored
    } finally {
      setIsJobsLoading(false);
    }
  };

  // Load Audit
  const loadAuditLogs = async () => {
    setIsAuditLoading(true);
    try {
      const list = await api.listAuditLogs({ limit: 50 });
      setAuditLogs(list);
    } catch {
      // Ignored
    } finally {
      setIsAuditLoading(false);
    }
  };

  useEffect(() => {
    if (activeSubTab === "users") loadUsers();
    else if (activeSubTab === "sources") loadSourcesHealth();
    else if (activeSubTab === "jobs") loadJobs();
    else if (activeSubTab === "audit") loadAuditLogs();
  }, [activeSubTab, jobFilterStatus]);

  // Actions: User Management
  const handleUpdateRole = async (userId: string, newRole: string) => {
    setUserActionError(null);
    try {
      await api.updateUserRole(userId, newRole);
      showSuccess(`تم تعديل صلاحية المستخدم إلى ${newRole} بنجاح.`);
      loadUsers();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setUserActionError(err.message);
      }
    }
  };

  const handleUpdateStatus = async (userId: string, newStatus: string) => {
    setUserActionError(null);
    try {
      await api.updateUserStatus(userId, newStatus);
      showSuccess(`تم تحديث حالة المستخدم إلى ${newStatus} بنجاح.`);
      loadUsers();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setUserActionError(err.message);
      }
    }
  };

  // Actions: Sources
  const handleToggleSource = async (sourceId: string, currentEnabled: boolean) => {
    try {
      await api.toggleSource(sourceId, !currentEnabled);
      showSuccess(`تم ${!currentEnabled ? "تفعيل" : "تعطيل"} المصدر ${sourceId} بنجاح.`);
      loadSourcesHealth();
    } catch {
      // Handled
    }
  };

  const handleTriggerIngest = async (sourceId: string) => {
    try {
      await api.triggerJob(sourceId, 20);
      showSuccess(`تم جدولة مهمة جمع الأخبار من ${sourceId} بنجاح.`);
      if (activeSubTab === "sources") loadSourcesHealth();
    } catch {
      // Handled
    }
  };

  // Actions: Jobs
  const handleRetryJob = async (jobId: string) => {
    try {
      await api.retryJob(jobId);
      showSuccess(`تمت إعادة جدولة المهمة ${jobId} بنجاح.`);
      loadJobs();
    } catch {
      // Handled
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      await api.cancelJob(jobId);
      showSuccess(`تم إلغاء المهمة ${jobId} بنجاح.`);
      loadJobs();
    } catch {
      // Handled
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8" dir="rtl">
      {/* Page Title */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-text flex items-center space-x-2 space-x-reverse">
          <Shield className="h-6 w-6 text-brand" />
          <span>لوحة الرقابة والإدارة الفنية</span>
        </h1>
        <p className="text-sm text-muted mt-1">
          إدارة الحسابات والصلاحيات، ومتابعة صحة ومعدلات فشل مصادر الأخبار، وتشخيص مهام العمال وسجل التدقيق.
        </p>
      </div>

      {/* Success Notification */}
      {successMsg && (
        <div className="mb-6 bg-emerald-50 border border-emerald-200 text-positive px-4 py-3 rounded-lg text-sm flex items-center space-x-2 space-x-reverse animate-fade-in">
          <CheckCircle className="h-4 w-4 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* User Action Error (Last-Admin Guard / Conflict) */}
      {userActionError && (
        <div className="mb-6 bg-red-50 border border-red-200 text-negative px-4 py-3 rounded-lg text-sm flex items-start space-x-2 space-x-reverse" role="alert">
          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-bold">تعذر تنفيذ الإجراء:</div>
            <div>{userActionError}</div>
          </div>
        </div>
      )}

      {/* Sub Tabs Navigation */}
      <div className="flex border-b border-border mb-6 space-x-4 space-x-reverse">
        {[
          { id: "users", label: "المستخدمين والموافقات", icon: Users },
          { id: "sources", label: "صحة المصادر والمراقبة", icon: Activity },
          { id: "jobs", label: "مهام العمال والأعطال", icon: Clock },
          { id: "audit", label: "سجل التدقيق الأمني", icon: History },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveSubTab(tab.id as any)}
              className={`pb-3 px-3 text-sm font-semibold flex items-center space-x-2 space-x-reverse border-b-2 transition-colors ${
                isActive
                  ? "border-brand text-brand"
                  : "border-transparent text-muted hover:text-text hover:border-slate-300"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab 1: Users Administration */}
      {activeSubTab === "users" && (
        <div className="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-border flex justify-between items-center bg-canvas/50">
            <span className="font-bold text-sm text-text">إجمالي الحسابات المسجلة ({users.length})</span>
            <button
              type="button"
              onClick={loadUsers}
              className="p-1.5 text-muted hover:text-text hover:bg-slate-200 rounded"
              title="تحديث القائمة"
            >
              <RefreshCw className={`h-4 w-4 ${isUsersLoading ? "animate-spin" : ""}`} />
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="bg-slate-50 text-muted border-b border-border">
                <tr>
                  <th className="p-3.5">المستخدم</th>
                  <th className="p-3.5">البريد</th>
                  <th className="p-3.5">الصلاحية</th>
                  <th className="p-3.5">الحالة</th>
                  <th className="p-3.5 text-center">إجراءات الإدارة وحماية آخر مدير</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {users.map((u) => {
                  const isPending = u.status === "pending";
                  const isActive = u.status === "active";
                  return (
                    <tr key={u.user_id} className="hover:bg-slate-50 transition-colors">
                      <td className="p-3.5 font-bold text-text">{u.username}</td>
                      <td className="p-3.5 text-muted font-mono">{u.email || "—"}</td>
                      <td className="p-3.5">
                        <select
                          value={u.role}
                          onChange={(e) => handleUpdateRole(u.user_id, e.target.value)}
                          className="bg-canvas border border-border rounded px-2 py-1 text-xs focus:ring-1 focus:ring-focus"
                        >
                          <option value="viewer">استطلاع (Viewer)</option>
                          <option value="analyst">محلل (Analyst)</option>
                          <option value="admin">مدير نظام (Admin)</option>
                        </select>
                      </td>
                      <td className="p-3.5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full font-semibold text-[11px] ${
                            isActive
                              ? "bg-emerald-100 text-emerald-800"
                              : isPending
                              ? "bg-amber-100 text-amber-800"
                              : "bg-red-100 text-red-800"
                          }`}
                        >
                          {isActive ? "نشط ومفعل" : isPending ? "بانتظار الموافقة" : "معطل"}
                        </span>
                      </td>
                      <td className="p-3.5 text-center">
                        <div className="flex items-center justify-center space-x-2 space-x-reverse">
                          {isPending && (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(u.user_id, "active")}
                              className="px-2.5 py-1 bg-brand text-white rounded text-xs font-semibold hover:bg-brand-hover"
                            >
                              موافقة وتفعيل
                            </button>
                          )}

                          {isActive && (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(u.user_id, "disabled")}
                              className="px-2.5 py-1 bg-red-50 text-negative border border-red-200 rounded text-xs font-semibold hover:bg-red-100"
                            >
                              تعطيل الحساب
                            </button>
                          )}

                          {u.status === "disabled" && (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(u.user_id, "active")}
                              className="px-2.5 py-1 bg-slate-100 text-text border border-border rounded text-xs font-semibold hover:bg-slate-200"
                            >
                              إعادة التفعيل
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Sources Health & Diagnostics */}
      {activeSubTab === "sources" && (
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-bold text-sm text-text">حالة المصادر الثمانية المعتمدة ومعدلات الفشل</h2>
            <button
              type="button"
              onClick={loadSourcesHealth}
              className="p-1.5 text-muted hover:text-text bg-white border border-border rounded shadow-xs"
              title="تحديث حالة المصادر"
            >
              <RefreshCw className={`h-4 w-4 ${isSourcesLoading ? "animate-spin" : ""}`} />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {sourcesHealth.map((src) => (
              <div
                key={src.source_id}
                className="bg-surface border border-border rounded-xl p-5 shadow-sm flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono font-bold text-sm bg-slate-100 px-2 py-0.5 rounded">
                      {src.source_id}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleToggleSource(src.source_id, src.enabled)}
                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold transition-colors ${
                        src.enabled
                          ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {src.enabled ? (
                        <>
                          <CheckCircle className="h-3 w-3 ml-1 text-positive" />
                          مفعل (انقر للتعطيل)
                        </>
                      ) : (
                        <>
                          <Lock className="h-3 w-3 ml-1 text-slate-400" />
                          معطل (انقر للتفعيل)
                        </>
                      )}
                    </button>
                  </div>

                  <h3 className="font-bold text-base text-text mb-2">{src.name}</h3>

                  <div className="space-y-1 text-xs text-muted mb-4">
                    <div className="flex justify-between">
                      <span>إجمالي المقالات المخزنة:</span>
                      <strong className="text-text font-mono">{src.total_articles}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>آخر عملية جلب ناجحة:</span>
                      <span className="text-text font-mono">
                        {src.latest_fetched_at
                          ? new Date(src.latest_fetched_at).toLocaleDateString("ar-EG")
                          : "لم يتم بعد"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>المهام الفاشلة المسجلة:</span>
                      <span
                        className={`font-mono font-bold ${
                          src.failed_jobs_count > 0 ? "text-negative" : "text-positive"
                        }`}
                      >
                        {src.failed_jobs_count}
                      </span>
                    </div>
                  </div>

                  {src.recent_error && (
                    <div className="mb-4 bg-red-50 border border-red-200 rounded p-2.5 text-xs text-negative flex items-start space-x-1.5 space-x-reverse">
                      <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                      <span className="line-clamp-2" title={src.recent_error}>
                        {src.recent_error}
                      </span>
                    </div>
                  )}
                </div>

                <div className="pt-3 border-t border-border flex justify-between items-center">
                  <span className="text-xs text-muted">سقف: {src.rate_limit_per_minute}/دقيقة</span>
                  <button
                    type="button"
                    onClick={() => handleTriggerIngest(src.source_id)}
                    className="inline-flex items-center space-x-1 space-x-reverse px-2.5 py-1 bg-brand text-white rounded text-xs font-semibold hover:bg-brand-hover transition-colors"
                  >
                    <Play className="h-3 w-3" />
                    <span>بدء الجمع الفوري</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Worker Runs & Failures */}
      {activeSubTab === "jobs" && (
        <div>
          {/* Status Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
            {[
              { id: "pending", label: "قيد الانتظار", count: jobStats.pending || 0, color: "text-amber-700 bg-amber-50" },
              { id: "running", label: "قيد المعالجة (Leased)", count: jobStats.running || 0, color: "text-blue-700 bg-blue-50" },
              { id: "completed", label: "مكتملة بنجاح", count: jobStats.completed || 0, color: "text-emerald-700 bg-emerald-50" },
              { id: "failed", label: "مهام فشلت", count: jobStats.failed || 0, color: "text-red-700 bg-red-50" },
            ].map((stat) => (
              <div
                key={stat.id}
                onClick={() => setJobFilterStatus(jobFilterStatus === stat.id ? "" : stat.id)}
                className={`p-4 rounded-xl border border-border cursor-pointer transition-all ${
                  jobFilterStatus === stat.id ? "ring-2 ring-brand shadow-sm" : "hover:border-slate-300"
                } ${stat.color}`}
              >
                <div className="text-xs font-medium">{stat.label}</div>
                <div className="text-2xl font-bold mt-1 font-mono">{stat.count}</div>
              </div>
            ))}
          </div>

          {/* Jobs Table */}
          <div className="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border flex justify-between items-center bg-canvas/50">
              <div className="flex items-center space-x-2 space-x-reverse text-xs">
                <span className="font-bold text-text">قائمة المهام ({jobs.length})</span>
                {jobFilterStatus && (
                  <span className="bg-brand-light text-brand px-2 py-0.5 rounded font-mono">
                    تصفية: {jobFilterStatus}
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={loadJobs}
                className="p-1.5 text-muted hover:text-text hover:bg-slate-200 rounded"
                title="تحديث المهام"
              >
                <RefreshCw className={`h-4 w-4 ${isJobsLoading ? "animate-spin" : ""}`} />
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-right text-xs">
                <thead className="bg-slate-50 text-muted border-b border-border">
                  <tr>
                    <th className="p-3.5">النوع (Kind)</th>
                    <th className="p-3.5">المستهدف (Target)</th>
                    <th className="p-3.5">الحالة</th>
                    <th className="p-3.5">المحاولات</th>
                    <th className="p-3.5">تشخيص العطل والخطأ</th>
                    <th className="p-3.5 text-center">إجراءات الاستعادة</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {jobs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-muted">
                        لا توجد مهام مطابقة للشروط الحالية.
                      </td>
                    </tr>
                  ) : (
                    jobs.map((j) => (
                      <tr key={j.job_id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-3.5 font-mono font-bold text-text">{j.kind}</td>
                        <td className="p-3.5 font-mono text-muted">{j.target_id}</td>
                        <td className="p-3.5">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded font-mono text-[11px] font-bold ${
                              j.status === "completed"
                                ? "bg-emerald-100 text-emerald-800"
                                : j.status === "failed"
                                ? "bg-red-100 text-red-800"
                                : j.status === "running"
                                ? "bg-blue-100 text-blue-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {j.status}
                          </span>
                        </td>
                        <td className="p-3.5 font-mono">
                          {j.attempts}/{j.max_attempts}
                        </td>
                        <td className="p-3.5 text-negative max-w-xs truncate" title={j.error || "لا أخطاء"}>
                          {j.error || "—"}
                        </td>
                        <td className="p-3.5 text-center">
                          <div className="flex items-center justify-center space-x-1.5 space-x-reverse">
                            {j.status === "failed" && (
                              <button
                                type="button"
                                onClick={() => handleRetryJob(j.job_id)}
                                className="inline-flex items-center space-x-1 space-x-reverse px-2 py-1 bg-brand text-white rounded text-[11px] font-medium hover:bg-brand-hover"
                              >
                                <RotateCcw className="h-3 w-3" />
                                <span>إعادة المحاولة</span>
                              </button>
                            )}
                            {(j.status === "running" || j.status === "pending") && (
                              <button
                                type="button"
                                onClick={() => handleCancelJob(j.job_id)}
                                className="inline-flex items-center space-x-1 space-x-reverse px-2 py-1 bg-red-50 text-negative border border-red-200 rounded text-[11px] font-medium hover:bg-red-100"
                              >
                                <XCircle className="h-3 w-3" />
                                <span>إلغاء</span>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Audit Trail */}
      {activeSubTab === "audit" && (
        <div className="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-border flex justify-between items-center bg-canvas/50">
            <span className="font-bold text-sm text-text">سجل الأحداث والتدقيق الأمني ({auditLogs.length})</span>
            <button
              type="button"
              onClick={loadAuditLogs}
              className="p-1.5 text-muted hover:text-text hover:bg-slate-200 rounded"
              title="تحديث سجل التدقيق"
            >
              <RefreshCw className={`h-4 w-4 ${isAuditLoading ? "animate-spin" : ""}`} />
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="bg-slate-50 text-muted border-b border-border">
                <tr>
                  <th className="p-3.5">الوقت</th>
                  <th className="p-3.5">المنفذ (Actor ID)</th>
                  <th className="p-3.5">الإجراء (Action)</th>
                  <th className="p-3.5">الكيان (Entity)</th>
                  <th className="p-3.5">تفاصيل السجل</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {auditLogs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-8 text-center text-muted">
                      لا توجد سجلات تدقيق حتى الآن.
                    </td>
                  </tr>
                ) : (
                  auditLogs.map((log) => (
                    <tr key={log.log_id} className="hover:bg-slate-50 transition-colors">
                      <td className="p-3.5 font-mono text-muted">
                        {new Date(log.created_at).toLocaleString("ar-EG")}
                      </td>
                      <td className="p-3.5 font-mono text-text">{log.actor_id}</td>
                      <td className="p-3.5">
                        <span className="bg-slate-100 text-slate-800 font-mono px-2 py-0.5 rounded font-bold">
                          {log.action}
                        </span>
                      </td>
                      <td className="p-3.5 font-mono text-muted">
                        {log.entity_type}:{log.entity_id}
                      </td>
                      <td className="p-3.5 font-mono text-muted max-w-sm truncate" title={JSON.stringify(log.details)}>
                        {JSON.stringify(log.details)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
