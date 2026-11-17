import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import type { InAppNotification } from "../types/api";
import {
  BarChart3,
  Bell,
  CheckCheck,
  FolderKanban,
  Layers,
  LogOut,
  Newspaper,
  Radio,
  Scale,
  Shield,
  User as UserIcon,
} from "lucide-react";

interface HeaderProps {
  currentTab: "articles" | "stories" | "comparison" | "analytics" | "sources" | "admin" | "workspace";
  onTabChange: (tab: "articles" | "stories" | "comparison" | "analytics" | "sources" | "admin" | "workspace") => void;
  onSelectArticle?: (articleId: string) => void;
  onSelectStory?: (storyId: string) => void;
}

export function Header({ currentTab, onTabChange, onSelectArticle, onSelectStory }: HeaderProps) {
  const { user, logout } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<InAppNotification[]>([]);
  const [isLoadingNotifications, setIsLoadingNotifications] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Poll or fetch unread count
  useEffect(() => {
    if (!user) return;
    let isMounted = true;

    async function fetchUnread() {
      try {
        const res = await api.getUnreadNotificationCount();
        if (isMounted) setUnreadCount(res.unread_count);
      } catch {
        // Silently handle
      }
    }

    fetchUnread();
    const interval = setInterval(fetchUnread, 30000); // 30s background check
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [user]);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleToggleNotifications = async () => {
    const nextState = !showNotifications;
    setShowNotifications(nextState);
    if (nextState) {
      setIsLoadingNotifications(true);
      try {
        const res = await api.listNotifications({ limit: 15 });
        setNotifications(res.items);
        setUnreadCount(res.unread_count);
      } catch {
        // Silently handle
      } finally {
        setIsLoadingNotifications(false);
      }
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.markAllNotificationsRead();
      setUnreadCount(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch {
      // Silently handle
    }
  };

  const handleNotificationClick = async (notif: InAppNotification) => {
    if (!notif.is_read) {
      try {
        await api.markNotificationRead(notif.notification_id);
        setUnreadCount((c) => Math.max(0, c - 1));
        setNotifications((prev) =>
          prev.map((n) =>
            n.notification_id === notif.notification_id ? { ...n, is_read: true } : n
          )
        );
      } catch {
        // Silently handle
      }
    }

    setShowNotifications(false);

    if (notif.target_type === "article" && onSelectArticle) {
      onSelectArticle(notif.target_id);
    } else if (notif.target_type === "story" && onSelectStory) {
      onSelectStory(notif.target_id);
    } else if (notif.target_type === "saved_query") {
      onTabChange("workspace");
    }
  };

  const formatNotificationTime = (isoString: string) => {
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

  return (
    <header className="bg-surface border-b border-border shadow-sm sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo & Navigation */}
          <div className="flex items-center space-x-6 space-x-reverse">
            <div className="flex items-center space-x-2 space-x-reverse cursor-pointer" onClick={() => onTabChange("articles")}>
              <div className="bg-brand text-white p-2 rounded-lg flex items-center justify-center">
                <Newspaper className="h-5 w-5" />
              </div>
              <span className="font-bold text-xl text-text tracking-tight">InsightBot</span>
            </div>

            <nav className="flex space-x-2 space-x-reverse">
              <button
                type="button"
                onClick={() => onTabChange("articles")}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  currentTab === "articles"
                    ? "bg-brand-light text-brand"
                    : "text-muted hover:text-text hover:bg-slate-100"
                }`}
              >
                الأخبار والمقالات
              </button>

              <button
                type="button"
                onClick={() => onTabChange("stories")}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-1 space-x-reverse ${
                  currentTab === "stories"
                    ? "bg-brand-light text-brand"
                    : "text-muted hover:text-text hover:bg-slate-100"
                }`}
              >
                <Layers className="h-4 w-4" />
                <span>قصص وأحداث</span>
              </button>

              <button
                type="button"
                onClick={() => onTabChange("comparison")}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-1 space-x-reverse ${
                  currentTab === "comparison"
                    ? "bg-brand-light text-brand"
                    : "text-muted hover:text-text hover:bg-slate-100"
                }`}
              >
                <Scale className="h-4 w-4" />
                <span>مقارنة التغطية</span>
              </button>

              <button
                type="button"
                onClick={() => onTabChange("analytics")}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-1 space-x-reverse ${
                  currentTab === "analytics"
                    ? "bg-brand-light text-brand"
                    : "text-muted hover:text-text hover:bg-slate-100"
                }`}
              >
                <BarChart3 className="h-4 w-4" />
                <span>التحليلات والتقارير</span>
              </button>

              <button
                type="button"
                onClick={() => onTabChange("sources")}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  currentTab === "sources"
                    ? "bg-brand-light text-brand"
                    : "text-muted hover:text-text hover:bg-slate-100"
                }`}
              >
                المصادر المعتمدة
              </button>

              {(user?.role === "Admin" || user?.role === "Analyst") && (
                <button
                  type="button"
                  onClick={() => onTabChange("workspace")}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-1 space-x-reverse ${
                    currentTab === "workspace"
                      ? "bg-brand-light text-brand"
                      : "text-muted hover:text-text hover:bg-slate-100"
                  }`}
                >
                  <FolderKanban className="h-4 w-4" />
                  <span>مساحة العمل</span>
                </button>
              )}

              {user?.role === "Admin" && (
                <button
                  type="button"
                  onClick={() => onTabChange("admin")}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-1 space-x-reverse ${
                    currentTab === "admin"
                      ? "bg-brand-light text-brand"
                      : "text-muted hover:text-text hover:bg-slate-100"
                  }`}
                >
                  <Shield className="h-4 w-4" />
                  <span>الإدارة والرقابة</span>
                </button>
              )}
            </nav>
          </div>

          {/* User Profile & Actions */}
          <div className="flex items-center space-x-4 space-x-reverse">
            <div className="hidden sm:flex items-center text-xs text-muted bg-canvas border border-border px-2.5 py-1.5 rounded-full space-x-1.5 space-x-reverse">
              <Radio className="h-3 w-3 text-positive animate-pulse" />
              <span>نظام محلي 100% (بدون APIs مدفوعة)</span>
            </div>

            {/* In-App Notifications Bell (Task T19) */}
            {user && (
              <div className="relative" ref={dropdownRef}>
                <button
                  type="button"
                  onClick={handleToggleNotifications}
                  title="التنبيهات المباشرة"
                  aria-label="التنبيهات المباشرة"
                  className="relative p-2 text-muted hover:text-text hover:bg-slate-100 rounded-lg transition-colors"
                >
                  <Bell className="h-5 w-5" />
                  {unreadCount > 0 && (
                    <span className="absolute top-1 right-1 flex h-4 min-w-[1rem] px-1 items-center justify-center rounded-full bg-brand text-[10px] font-bold text-white shadow-xs">
                      {unreadCount > 99 ? "99+" : unreadCount}
                    </span>
                  )}
                </button>

                {showNotifications && (
                  <div className="absolute left-0 mt-2 w-80 sm:w-96 bg-surface border border-border rounded-xl shadow-xl z-50 overflow-hidden text-right">
                    {/* Header */}
                    <div className="p-3 bg-slate-50 border-b border-border flex items-center justify-between">
                      <div className="flex items-center space-x-1.5 space-x-reverse">
                        <Bell className="h-4 w-4 text-brand ml-1" />
                        <span className="font-bold text-xs text-text">التنبيهات المباشرة</span>
                        {unreadCount > 0 && (
                          <span className="bg-brand-light text-brand text-[10px] px-1.5 py-0.2 rounded-full font-bold">
                            {unreadCount} غير مقروء
                          </span>
                        )}
                      </div>

                      {unreadCount > 0 && (
                        <button
                          type="button"
                          onClick={handleMarkAllRead}
                          className="text-[11px] text-brand hover:underline font-semibold flex items-center space-x-1 space-x-reverse"
                        >
                          <CheckCheck className="h-3 w-3 ml-0.5" />
                          <span>تحديد الكل كمقروء</span>
                        </button>
                      )}
                    </div>

                    {/* List */}
                    <div className="max-h-80 overflow-y-auto divide-y divide-border">
                      {isLoadingNotifications && (
                        <div className="py-8 text-center text-xs text-muted">
                          جاري تحميل التنبيهات...
                        </div>
                      )}

                      {!isLoadingNotifications && notifications.length === 0 && (
                        <div className="py-8 text-center text-xs text-muted">
                          لا توجد تنبيهات حالياً.
                        </div>
                      )}

                      {!isLoadingNotifications &&
                        notifications.map((n) => (
                          <div
                            key={n.notification_id}
                            onClick={() => handleNotificationClick(n)}
                            className={`p-3 hover:bg-slate-50 cursor-pointer transition-colors text-xs ${
                              !n.is_read ? "bg-blue-50/40" : ""
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-bold text-text truncate max-w-[200px]">
                                {n.title}
                              </span>
                              <span className="text-[10px] text-muted">
                                {formatNotificationTime(n.created_at)}
                              </span>
                            </div>
                            <p className="text-muted leading-relaxed line-clamp-2 text-[11px]">
                              {n.message}
                            </p>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {user && (
              <div className="flex items-center space-x-3 space-x-reverse">
                <div className="flex items-center space-x-2 space-x-reverse">
                  <div className="h-8 w-8 rounded-full bg-slate-200 flex items-center justify-center text-muted">
                    <UserIcon className="h-4 w-4" />
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-text">{user.username}</div>
                    <div className="text-xs text-muted">
                      {user.role === "Admin" ? "مدير النظام" : user.role === "Analyst" ? "محلل استخباراتي" : "مستخدم استطلاع"}
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={logout}
                  title="تسجيل الخروج"
                  className="p-2 text-muted hover:text-negative hover:bg-red-50 rounded-md transition-colors"
                  aria-label="تسجيل الخروج"
                >
                  <LogOut className="h-5 w-5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
