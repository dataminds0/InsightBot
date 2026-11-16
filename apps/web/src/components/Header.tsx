import { useAuth } from "../context/AuthContext";
import { FolderKanban, LogOut, Newspaper, Radio, Shield, User as UserIcon } from "lucide-react";

interface HeaderProps {
  currentTab: "articles" | "sources" | "admin" | "workspace";
  onTabChange: (tab: "articles" | "sources" | "admin" | "workspace") => void;
}

export function Header({ currentTab, onTabChange }: HeaderProps) {
  const { user, logout } = useAuth();

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
