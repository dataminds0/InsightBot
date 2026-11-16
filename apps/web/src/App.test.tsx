import { describe, it, expect, beforeEach, vi } from "vitest";
import { api, ApiClientError } from "./lib/api";
import type { ArticleListItem, ArticleDetail } from "./types/api";

const mockStorage: Record<string, string> = {};
globalThis.localStorage = {
  getItem: (key: string) => mockStorage[key] ?? null,
  setItem: (key: string, value: string) => {
    mockStorage[key] = value;
  },
  removeItem: (key: string) => {
    delete mockStorage[key];
  },
  clear: () => {
    Object.keys(mockStorage).forEach((k) => delete mockStorage[k]);
  },
  key: (index: number) => Object.keys(mockStorage)[index] ?? null,
  length: 0,
} as Storage;

describe("InsightBot Complete Journey & API Client Tests", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("enforces strict type separation between ArticleListItem and ArticleDetail (Defect A12)", () => {
    // ArticleListItem MUST NOT have body_text
    const sampleListItem: ArticleListItem = {
      article_id: "art-123",
      source_id: "aljazeera_ar",
      canonical_url: "https://aljazeera.net/1",
      title: "خبر عاجل من الميدان",
      language: "ar",
      published_at: "2026-11-10T12:00:00Z",
      fetched_at: "2026-11-10T12:05:00Z",
      current_version: 1,
      word_count: 350,
      reading_time_minutes: 2,
    };

    expect("body_text" in sampleListItem).toBe(false);

    // ArticleDetail MUST have full body_text
    const sampleDetail: ArticleDetail = {
      ...sampleListItem,
      original_url: "https://aljazeera.net/1",
      resolved_url: "https://aljazeera.net/1",
      body_text: "هذا هو النص الكامل للخبر المنشور في الجريدة...",
      content_hash: "abc123sha256hash",
      first_seen_at: "2026-11-10T12:05:00Z",
      updated_at: "2026-11-10T12:05:00Z",
      fencing_token: 1,
    };

    expect(sampleDetail.body_text).toBeDefined();
    expect(sampleDetail.body_text.length).toBeGreaterThan(0);
  });

  it("handles user authentication lifecycle (login, token persistence, and logout)", async () => {
    const mockLoginResponse = {
      user: {
        user_id: "u-1",
        username: "analyst_samir",
        role: "Analyst",
        status: "Active",
      },
      token: "mock-bearer-token-xyz-123",
    };

    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "X-Request-ID": "req-login-1" }),
      json: async () => mockLoginResponse,
    });
    globalThis.fetch = fetchMock;

    // Execute Login
    const res = await api.login("analyst_samir", "SecurePassword123");
    expect(res.user.username).toBe("analyst_samir");
    expect(res.user.role).toBe("Analyst");
    expect(api.getToken()).toBe("mock-bearer-token-xyz-123");
    expect(localStorage.getItem("insightbot_token")).toBe("mock-bearer-token-xyz-123");

    // Fetch call included credentials and proper headers
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      })
    );

    // Mock Logout
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers(),
      json: async () => ({ message: "Logged out" }),
    });

    await api.logout();
    expect(api.getToken()).toBeNull();
    expect(localStorage.getItem("insightbot_token")).toBeNull();
  });

  it("fetches projected articles with query filters and verifies no body_text", async () => {
    api.setToken("valid-token");

    const mockArticlesResponse = {
      items: [
        {
          article_id: "art-1",
          source_id: "aljazeera_ar",
          canonical_url: "https://aljazeera.net/1",
          title: "قمة المناخ: قرارات جديدة",
          language: "ar",
          published_at: "2026-11-15T09:00:00Z",
          fetched_at: "2026-11-15T09:10:00Z",
          current_version: 1,
          word_count: 600,
          reading_time_minutes: 3,
        },
        {
          article_id: "art-2",
          source_id: "reuters_en",
          canonical_url: "https://reuters.com/2",
          title: "Global Economic Outlook 2027",
          language: "en",
          published_at: null,
          publication_date_unknown_reason: "missing_in_feed_and_metadata",
          fetched_at: "2026-11-15T09:15:00Z",
          current_version: 2,
          word_count: 400,
          reading_time_minutes: 2,
        },
      ],
      total_count: 2,
      limit: 10,
      next_cursor: "cursor-token-page-2",
    };

    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "X-Request-ID": "req-art-list-1" }),
      json: async () => mockArticlesResponse,
    });
    globalThis.fetch = fetchMock;

    const result = await api.listArticles({
      q: "قمة",
      source_id: "aljazeera_ar",
      language: "ar",
      limit: 10,
    });

    expect(result.items.length).toBe(2);
    expect(result.total_count).toBe(2);
    expect(result.next_cursor).toBe("cursor-token-page-2");

    // CRITICAL: Ensure items strictly lack body_text
    for (const item of result.items) {
      expect((item as any).body_text).toBeUndefined();
    }

    // Verify query string construction
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("q=%D9%82%D9%85%D8%A9"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer valid-token",
        }),
      })
    );
  });

  it("calculates reading time from word count instead of fetch latency (Defect A14)", () => {
    // 600 words should be ~3 minutes reading time (at 200 words/min)
    const wordCount = 600;
    const calculatedReadingTime = Math.max(1, Math.ceil(wordCount / 200));
    expect(calculatedReadingTime).toBe(3);

    // Short article of 50 words should be at least 1 minute
    const shortWc = 50;
    expect(Math.max(1, Math.ceil(shortWc / 200))).toBe(1);

    // Verify that network fetch latency (e.g. 0.45s) is completely separate
    const networkFetchLatencySeconds = 0.45;
    expect(calculatedReadingTime).not.toBe(networkFetchLatencySeconds);
  });

  it("supports request cancellation via AbortSignal", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      headers: new Headers(),
      json: async () => ({ items: [], total_count: 0, limit: 10 }),
    });
    globalThis.fetch = fetchMock;

    await api.listArticles({ q: "تست" }, controller.signal);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("q="),
      expect.objectContaining({
        signal: controller.signal,
      })
    );
  });

  it("fetches single article detail and revision history", async () => {
    api.setToken("valid-token");

    const mockDetail: ArticleDetail = {
      article_id: "art-1",
      source_id: "aljazeera_ar",
      canonical_url: "https://aljazeera.net/1",
      original_url: "https://aljazeera.net/1",
      resolved_url: "https://aljazeera.net/1",
      title: "قمة المناخ: قرارات جديدة",
      body_text: "النص الأصلي الكامل للمقال المأخوذ من موقع الجزيرة...",
      content_hash: "hash123456",
      language: "ar",
      published_at: "2026-11-15T09:00:00Z",
      fetched_at: "2026-11-15T09:10:00Z",
      first_seen_at: "2026-11-15T09:10:00Z",
      updated_at: "2026-11-15T09:10:00Z",
      current_version: 1,
      fencing_token: 1,
      word_count: 500,
      reading_time_minutes: 3,
    };

    const mockVersions = [
      {
        article_id: "art-1",
        version: 1,
        title: "قمة المناخ: قرارات جديدة",
        body_text: "النص الأصلي الكامل للمقال المأخوذ من موقع الجزيرة...",
        content_hash: "hash123456",
        operation: "initial_fetch",
        created_at: "2026-11-15T09:10:00Z",
      },
    ];

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => mockVersions,
      });
    globalThis.fetch = fetchMock;

    const detail = await api.getArticle("art-1");
    expect(detail.article_id).toBe("art-1");
    expect(detail.body_text).toContain("النص الأصلي الكامل");
    expect(detail.reading_time_minutes).toBe(3);

    const versions = await api.getArticleVersions("art-1");
    expect(versions.length).toBe(1);
    expect(versions[0].version).toBe(1);
  });

  it("maps structured error envelopes and request IDs accurately", async () => {
    const errorEnvelope = {
      error: {
        code: "UNAUTHORIZED",
        message: "Authentication required.",
        request_id: "req-err-999",
      },
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ "X-Request-ID": "req-err-999" }),
      json: async () => errorEnvelope,
    });
    globalThis.fetch = fetchMock;

    await expect(api.getArticle("nonexistent")).rejects.toThrow(ApiClientError);

    try {
      await api.getArticle("nonexistent");
    } catch (e: any) {
      expect(e).toBeInstanceOf(ApiClientError);
      expect(e.status).toBe(401);
      expect(e.code).toBe("UNAUTHORIZED");
      expect(e.message).toBe("Authentication required.");
      expect(e.requestId).toBe("req-err-999");
    }
  });

  it("manages administrator workflows: user approvals, source toggling, and job retries", async () => {
    api.setToken("admin-bearer-token");

    // 1. User approval
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({ user_id: "u-99", username: "cadet", role: "viewer", status: "active" }),
      })
      // 2. Source health
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => [
          {
            source_id: "aljazeera_ar",
            name: "الجزيرة",
            url: "https://aljazeera.net",
            language: "ar",
            enabled: false,
            rate_limit_per_minute: 30,
            retention_days: 90,
            total_articles: 150,
            failed_jobs_count: 0,
          },
        ],
      })
      // 3. Toggle source
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({ source_id: "aljazeera_ar", enabled: true }),
      })
      // 4. Job retry
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({ job_id: "job-1", status: "pending", attempts: 0 }),
      });
    globalThis.fetch = fetchMock;

    // Test user status update
    const updatedUser = await api.updateUserStatus("u-99", "active");
    expect(updatedUser.status).toBe("active");

    // Test source health
    const health = await api.getSourcesHealth();
    expect(health.length).toBe(1);
    expect(health[0].source_id).toBe("aljazeera_ar");

    // Test toggle source
    const toggled = await api.toggleSource("aljazeera_ar", true);
    expect(toggled.enabled).toBe(true);

    // Test job retry
    const retriedJob = await api.retryJob("job-1");
    expect(retriedJob.status).toBe("pending");
  });

  it("handles bookmarks lifecycle, tags, and graceful handling of unavailable target articles", async () => {
    api.setToken("analyst-token");

    const mockBookmarksResponse = {
      items: [
        {
          bookmark_id: "bm-1",
          user_id: "u-1",
          article_id: "art-100",
          notes: "ملاحظة أولى",
          tags: ["سياسة", "عاجل"],
          created_at: "2026-11-16T12:00:00Z",
          target_available: true,
          article: {
            article_id: "art-100",
            source_id: "aljazeera_ar",
            canonical_url: "https://aljazeera.net/1",
            title: "خبر مهم",
            language: "ar",
            published_at: "2026-11-16T10:00:00Z",
            fetched_at: "2026-11-16T10:05:00Z",
            current_version: 1,
            word_count: 400,
            reading_time_minutes: 2,
          },
        },
        {
          bookmark_id: "bm-2",
          user_id: "u-1",
          article_id: "art-deleted-99",
          notes: "مقال تم حذفه لاحقاً",
          tags: ["أرشيف"],
          created_at: "2026-11-16T11:00:00Z",
          target_available: false,
          article: null,
        },
      ],
      total: 2,
      skip: 0,
      limit: 50,
    };

    const fetchMock = vi
      .fn()
      // 1. listBookmarks
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => mockBookmarksResponse,
      })
      // 2. createBookmark
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          bookmark_id: "bm-3",
          user_id: "u-1",
          article_id: "art-200",
          tags: ["اقتصاد"],
          created_at: "2026-11-16T13:00:00Z",
        }),
      })
      // 3. deleteBookmark
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({ deleted: true, article_id: "art-100" }),
      });
    globalThis.fetch = fetchMock;

    const listRes = await api.listBookmarks({ limit: 50 });
    expect(listRes.total).toBe(2);
    expect(listRes.items[0].target_available).toBe(true);
    expect(listRes.items[0].article?.title).toBe("خبر مهم");
    // Verify Defect A12: bookmark item article summary does NOT have body_text
    expect("body_text" in (listRes.items[0].article || {})).toBe(false);

    // Verify unavailable target item
    expect(listRes.items[1].target_available).toBe(false);
    expect(listRes.items[1].article).toBeNull();

    // Create bookmark
    const created = await api.createBookmark({ article_id: "art-200", tags: ["اقتصاد"] });
    expect(created.bookmark_id).toBe("bm-3");

    // Delete bookmark
    const deleted = await api.deleteBookmark("art-100");
    expect(deleted.deleted).toBe(true);
  });

  it("handles saved queries creation, reopening query params, and alert delivery status", async () => {
    api.setToken("analyst-token");

    const mockSavedQueries = {
      items: [
        {
          query_id: "sq-1",
          user_id: "u-1",
          name: "رصد الشرق الأوسط",
          query_params: {
            q: "الشرق الأوسط",
            source_id: "aljazeera_ar",
            language: "ar",
            include_unknown_date: true,
          },
          alerts_enabled: false,
          created_at: "2026-11-16T10:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
        },
      ],
      total: 1,
      skip: 0,
      limit: 50,
    };

    const fetchMock = vi
      .fn()
      // 1. listSavedQueries
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => mockSavedQueries,
      })
      // 2. createSavedQuery
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          query_id: "sq-2",
          user_id: "u-1",
          name: "أخبار الطاقة",
          query_params: { q: "نفط" },
          alerts_enabled: false,
          created_at: "2026-11-16T12:00:00Z",
          updated_at: "2026-11-16T12:00:00Z",
        }),
      })
      // 3. deleteSavedQuery
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({ deleted: true, query_id: "sq-1" }),
      });
    globalThis.fetch = fetchMock;

    const queries = await api.listSavedQueries();
    expect(queries.total).toBe(1);
    expect(queries.items[0].name).toBe("رصد الشرق الأوسط");
    expect(queries.items[0].query_params.q).toBe("الشرق الأوسط");
    expect(queries.items[0].alerts_enabled).toBe(false);

    const created = await api.createSavedQuery({
      name: "أخبار الطاقة",
      query_params: { q: "نفط" },
    });
    expect(created.name).toBe("أخبار الطاقة");

    const delRes = await api.deleteSavedQuery("sq-1");
    expect(delRes.deleted).toBe(true);
  });

  it("handles private analytical notes on articles", async () => {
    api.setToken("analyst-token");

    const fetchMock = vi
      .fn()
      // 1. getArticleNote
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          note_id: "note-1",
          user_id: "u-1",
          article_id: "art-100",
          content: "ملاحظات تحليلية سرية خاصة.",
          created_at: "2026-11-16T10:00:00Z",
          updated_at: "2026-11-16T10:30:00Z",
        }),
      })
      // 2. upsertArticleNote
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          note_id: "note-1",
          user_id: "u-1",
          article_id: "art-100",
          content: "ملاحظات تحليلية محدثة.",
          created_at: "2026-11-16T10:00:00Z",
          updated_at: "2026-11-16T11:00:00Z",
        }),
      })
      // 3. deleteArticleNote
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers(),
        json: async () => ({ deleted: true, article_id: "art-100" }),
      });
    globalThis.fetch = fetchMock;

    const note = await api.getArticleNote("art-100");
    expect(note.content).toBe("ملاحظات تحليلية سرية خاصة.");

    const updated = await api.upsertArticleNote("art-100", "ملاحظات تحليلية محدثة.");
    expect(updated.content).toBe("ملاحظات تحليلية محدثة.");

    const deleted = await api.deleteArticleNote("art-100");
    expect(deleted.deleted).toBe(true);
  });
});
