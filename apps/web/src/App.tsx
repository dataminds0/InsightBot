import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Header } from "./components/Header";
import { LoginForm } from "./components/LoginForm";
import { ArticleList, type ArticleFilterParams } from "./components/ArticleList";
import { ArticleDetailView } from "./components/ArticleDetailView";
import { SourcesView } from "./components/SourcesView";
import { AdminView } from "./components/AdminView";
import { WorkspaceView } from "./components/WorkspaceView";

function MainApp() {
  const { user, isLoading } = useAuth();
  const [currentTab, setCurrentTab] = useState<"articles" | "sources" | "admin" | "workspace">("articles");
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null);
  const [returnSearch, setReturnSearch] = useState<string>("");
  const [activeQueryFilters, setActiveQueryFilters] = useState<ArticleFilterParams | null>(null);

  // Synchronize browser history / URL paths
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname;
      if (path.startsWith("/articles/")) {
        const id = path.replace("/articles/", "").trim();
        setSelectedArticleId(id || null);
        setCurrentTab("articles");
      } else if (path === "/sources") {
        setCurrentTab("sources");
        setSelectedArticleId(null);
      } else if (path === "/workspace") {
        setCurrentTab("workspace");
        setSelectedArticleId(null);
      } else if (path === "/admin") {
        setCurrentTab("admin");
        setSelectedArticleId(null);
      } else {
        setSelectedArticleId(null);
        setCurrentTab("articles");
      }
    };

    handlePopState();
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const handleSelectArticle = (id: string) => {
    setReturnSearch(window.location.search);
    setSelectedArticleId(id);
    window.history.pushState({}, "", `/articles/${id}${window.location.search}`);
  };

  const handleBackToList = () => {
    setSelectedArticleId(null);
    window.history.pushState({}, "", returnSearch ? `/${returnSearch}` : "/");
  };

  const handleTabChange = (tab: "articles" | "sources" | "admin" | "workspace") => {
    setCurrentTab(tab);
    setSelectedArticleId(null);
    window.history.pushState({}, "", tab === "articles" ? "/" : `/${tab}`);
  };

  const handleRunSavedQuery = (queryParams: Record<string, unknown>) => {
    setActiveQueryFilters(queryParams as ArticleFilterParams);
    setCurrentTab("articles");
    setSelectedArticleId(null);
    window.history.pushState({}, "", "/");
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center" dir="rtl">
        <div className="text-center">
          <div className="h-10 w-10 border-4 border-brand border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-sm font-medium text-muted">جاري تحميل منصة InsightBot...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <LoginForm />;
  }

  return (
    <div className="min-h-screen bg-canvas text-text" dir="rtl">
      <Header currentTab={currentTab} onTabChange={handleTabChange} />

      <main className="pb-16">
        {selectedArticleId ? (
          <ArticleDetailView articleId={selectedArticleId} onBack={handleBackToList} />
        ) : currentTab === "articles" ? (
          <ArticleList
            onSelectArticle={handleSelectArticle}
            initialFilters={activeQueryFilters}
          />
        ) : currentTab === "sources" ? (
          <SourcesView />
        ) : currentTab === "workspace" ? (
          <WorkspaceView
            onSelectArticle={handleSelectArticle}
            onRunSavedQuery={handleRunSavedQuery}
          />
        ) : (
          <AdminView />
        )}
      </main>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}

export default App;
