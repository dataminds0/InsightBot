import random
from datetime import datetime, timedelta, date
import pandas as pd
import plotly.express as px
import streamlit as st
from storage import get_articles_df, log_event, set_last_page

def _inject_css_dashboard():
    st.markdown("""
    <style>
      :root{
        --bg:#f6f8fb; --card:#ffffff; --line:#eaeef3; --ink:#0f172a; --muted:#64748b;
        --accent:#3b82f6; --accent-2:#7c3aed; --success:#10b981; --warn:#f59e0b; --danger:#ef4444;
      }
      .block-container{ padding-top: 1.25rem; }

      section[data-testid="stSidebar"]{
        background:var(--bg); border-right:1px solid var(--line);
      }

      h1,h2,h3,h4{ color:var(--ink); letter-spacing:.1px; }

      .page-title{
        margin-top: 10px;
        display:flex; align-items:center; gap:10px;
        padding:8px 12px; border:1px solid var(--line); border-radius:12px;
        background:linear-gradient(180deg,#fff 0%, #fafcff 100%);
        box-shadow:0 6px 18px rgba(16,24,40,.05);
        margin-bottom:12px;
      }
      .page-chip{
        font-size:11px; padding:2px 8px; border-radius:999px;
        background:#eff6ff; color:#1d4ed8; border:1px solid #dbeafe;
      }

      .card{
        border:1px solid var(--line); border-radius:14px; padding:14px 16px;
        background:var(--card); box-shadow:0 8px 20px rgba(16,24,40,.06);
        margin-bottom:12px;
      }
      .sec-title{
        font-size:16px; font-weight:800; color:var(--ink); margin:2px 0 10px 0; letter-spacing:.2px;
        display:flex; align-items:center; gap:8px;
      }
      .subtle{ color:var(--muted); font-size:12px; }

      .viz{ padding-top:6px; }
      .viz .stPlotlyChart{ height:260px !important; }

      .article-wrap{ margin-bottom:10px; }
      .article-card{
        border:1px solid var(--line); border-radius:12px; padding:12px 14px; background:#fff;
        box-shadow:0 6px 18px rgba(16,24,40,.05);
        transition:transform .08s ease, box-shadow .12s ease;
      }
      .article-card:hover{ transform:translateY(-1px); box-shadow:0 10px 22px rgba(16,24,40,.08); }

      .meta-row{ display:flex; flex-wrap:wrap; gap:6px 8px; align-items:center; color:#64748b; font-size:12px; margin-top:2px; }
      .tag{ font-size:11px; padding:2px 8px; border-radius:999px; border:1px solid var(--line); background:#f8fafc; color:#334155; }
      .tag.lang{ background:#eef2ff; color:#3730a3; border-color:#e0e7ff; }
      .tag.ctx{ background:#ecfeff; color:#0369a1; border-color:#cffafe; }
      .tag.sent.pos{ background:#ecfdf5; color:#047857; border-color:#a7f3d0; }
      .tag.sent.neu{ background:#f0f9ff; color:#0369a1; border-color:#bae6fd; }
      .tag.sent.neg{ background:#fff1f2; color:#be123c; border-color:#fecdd3; }

      .pager{ display:flex; align-items:center; justify-content:center; gap:6px; margin-top:6px; }
      .pill{ padding:4px 10px; border:1px solid var(--line); border-radius:999px; background:#fff; font-size:12px; }
      .pill.active{ background:#eff6ff; border-color:#dbeafe; color:#1d4ed8; font-weight:700; }

      .sb-group{ margin-top:6px; margin-bottom:6px; font-weight:700; color:#0f172a; }
    </style>
    """, unsafe_allow_html=True)

def _to_date(x):
    if isinstance(x, datetime): return x.date()
    if isinstance(x, date): return x
    return None

def _normalize_date_input(val):
    if isinstance(val, (list, tuple)):
        s, e = (_to_date(val[0]), _to_date(val[-1]))
    else:
        s = e = _to_date(val)
    today = datetime.now().date()
    if s is None or e is None:
        return today - timedelta(days=7), today
    return s, e

def _clamp_date_range(val, data_min, data_max):
    s, e = _normalize_date_input(val)
    s = max(min(s, data_max), data_min)
    e = max(min(e, data_max), data_min)
    if s > e: s, e = data_min, data_max
    return s, e

def _scalarize(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return 
    if isinstance(v, list): return ", ".join([str(x).strip() for x in v if str(x).strip()])
    if isinstance(v, dict):
        for k in ("name","title","label","value","id","source","context","sentiment","topic"):
            if k in v and v[k]: return str(v[k]).strip()
        return str(v)
    return str(v).strip()

def _context_to_scalar(v):
    s = _scalarize(v)
    return s or "General"

def _fmt_date_safe(d):
    try:
        d = pd.to_datetime(d, errors="coerce")
        return d.strftime("%Y-%m-%d") if pd.notna(d) else ""
    except Exception:
        return ""

def _series_or_default(df, col, fill=""):
    return df[col] if col in df.columns else pd.Series([fill]*len(df), index=df.index)

def _sentiment_class(sentiment: str) -> str:
    s = (sentiment or "").strip().lower()
    if s == "positive": return "pos"
    if s == "negative": return "neg"
    return "neu"

def _render_badges(source, ctx, lang, sent, dstr) -> str:
    sent_cls = _sentiment_class(sent)
    source = source or "Unknown"
    ctx = ctx or "General"
    lang = lang or "Other"
    sent = sent or "Neutral"
    dstr = dstr or ""
    return (
        f'<div class="meta-row">'
        f'<span class="tag">{source}</span>'
        f'<span class="tag ctx">{ctx}</span>'
        f'<span class="tag lang">{lang}</span>'
        f'<span class="tag sent {sent_cls}">{sent}</span>'
        f'<span class="tag">{dstr}</span>'
        f'</div>'
    )

def user_dashboard():
    _inject_css_dashboard()

    st.markdown('<div class="page-title"><h2 style="margin:0;">InsightBot — Dashboard</h2><span class="page-chip">news analytics</span></div>', unsafe_allow_html=True)

    ss = st.session_state
    ss.setdefault("current_page", 1)
    ss.setdefault("selected_article", None)
    ss.setdefault("articles_page_size", 8)

    log_event("view_dashboard")
    set_last_page("dashboard")

    df = get_articles_df()
    if df.empty:
        st.info("No articles available to display.")
        return

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    lang_code = _series_or_default(df, "language").apply(_scalarize).astype(str).str.strip().str.casefold()
    df["language_code"] = lang_code
    _code_to_label = {"en": "English", "ar": "Arabic", "ru": "Russian"}
    df["language_label"] = df["language_code"].map(_code_to_label).fillna("Other")

    df["source_norm"]    = _series_or_default(df, "source").apply(_scalarize).astype(str).str.strip()
    df["sentiment_norm"] = _series_or_default(df, "sentiment").apply(_scalarize).astype(str).str.strip()
    df["context_norm"]   = _series_or_default(df, "context").apply(_context_to_scalar).astype(str).str.strip()

    data_min = (df["date"].min().date() if df["date"].notna().any() else datetime.now().date() - timedelta(days=30))
    data_max = (df["date"].max().date() if df["date"].notna().any() else datetime.now().date())

    st.sidebar.markdown('<div class="sb-group">Analytics</div>', unsafe_allow_html=True)
    show_analytics = st.sidebar.toggle("Show Analytics", value=True, key="show_analytics_toggle")

    st.sidebar.markdown('<div class="sb-group">Date Range</div>', unsafe_allow_html=True)
    safe_default = _clamp_date_range(ss.get("date_range", (data_min, data_max)), data_min, data_max)
    ss["date_range"] = safe_default
    date_range_val = st.sidebar.date_input(
        "Select Date Range",
        value=safe_default,
        min_value=data_min, max_value=data_max,
        key="date_range_widget",
    )
    start_date, end_date = _clamp_date_range(date_range_val if date_range_val else safe_default, data_min, data_max)
    ss["date_range"] = (start_date, end_date)

    st.sidebar.markdown('<div class="sb-group">Search</div>', unsafe_allow_html=True)
    search_q = st.sidebar.text_input("Search Articles", value=ss.get("search_q",""), key="search_widget")
    ss["search_q"] = search_q

    st.sidebar.markdown('<div class="sb-group">Language</div>', unsafe_allow_html=True)
    LANG_OPTIONS = ["All", "English", "Arabic", "Russian"]
    default_lang = ss.get("lang_filter", "All")
    lang_index = LANG_OPTIONS.index(default_lang) if default_lang in LANG_OPTIONS else 0
    lang_sel = st.sidebar.selectbox("Select language", options=LANG_OPTIONS, index=lang_index, key="lang_filter_widget")
    ss["lang_filter"] = lang_sel

    st.sidebar.markdown('<div class="sb-group">Context</div>', unsafe_allow_html=True)
    ctxs = sorted([c for c in df["context_norm"].unique().tolist() if isinstance(c, str) and c])
    default_ctxs = ss.get("contexts", [])
    contexts_sel = st.sidebar.multiselect("Select Contexts", options=["All"] + ctxs,
                                          default=default_ctxs, key="contexts_widget")
    contexts = [] if ("All" in contexts_sel) else contexts_sel
    ss["contexts"] = contexts

    st.sidebar.markdown('<div class="sb-group">Sentiment</div>', unsafe_allow_html=True)
    _sent_opts = ["All","Positive","Negative","Neutral"]
    default_sent = ss.get("selected_sentiment", "All")
    sent_index = _sent_opts.index(default_sent) if default_sent in _sent_opts else 0
    chosen_sent = st.sidebar.selectbox("Sentiment", options=_sent_opts, index=sent_index, key="sentiment_widget_select")
    ss["selected_sentiment"] = chosen_sent

    st.sidebar.divider()
    if st.sidebar.button("Clear Filters"):
        ss.update({
            "contexts": [],
            "selected_sentiment": "All",
            "search_q": "",
            "lang_filter": "All",
            "date_range": (data_min, data_max),
            "current_page": 1,
            "selected_article": None
        })
        for k in ["contexts_widget", "sentiment_widget_select", "search_widget",
                  "lang_filter_widget", "date_range_widget"]:
            if k in ss:
                del ss[k]
        st.rerun()

    filtered = df.copy()

    if lang_sel and lang_sel != "All":
        filtered = filtered[filtered["language_label"] == lang_sel]

    if contexts:
        ctx_fold = set([str(c).casefold() for c in contexts])
        filtered = filtered[filtered["context_norm"].astype(str).str.casefold().isin(ctx_fold)]

    if chosen_sent != "All":
        filtered = filtered[filtered["sentiment_norm"].astype(str).str.casefold() == str(chosen_sent).casefold()]

    if "date" in filtered.columns:
        mask = (filtered["date"].dt.date >= start_date) & (filtered["date"].dt.date <= end_date)
        filtered = filtered[mask]

    if search_q:
        terms = [t.strip() for t in str(search_q).split() if t.strip()]
        if terms:
            title = _series_or_default(filtered, "title").astype(str)
            content = _series_or_default(filtered, "content").astype(str)
            m = pd.Series(False, index=filtered.index)
            for t in terms:
                m = m | title.str.contains(t, case=False, na=False, regex=False) | \
                        content.str.contains(t, case=False, na=False, regex=False)
            filtered = filtered[m]

    if ss.get("selected_article"):
        art = dict(ss["selected_article"])
        ctx  = art.get("context_norm") or _context_to_scalar(art.get("context"))
        lang = art.get("language_label") or "Other"
        sent = art.get("sentiment_norm") or _scalarize(art.get("sentiment"))
        src  = art.get("source_norm")  or _scalarize(art.get("source"))
        dstr = _fmt_date_safe(art.get("date"))

        st.markdown('<div class="card"><div class="sec-title">Article</div>', unsafe_allow_html=True)
        with st.container():
            st.subheader(art.get("title", "(no title)"))
            st.markdown(_render_badges(src, ctx, lang, sent, dstr), unsafe_allow_html=True)
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            st.markdown(art.get("content", ""))
            url = art.get("url") or "#"
            st.markdown(f"[Read Full Article]({url})")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card"><div class="sec-title">Recommended Articles</div>', unsafe_allow_html=True)
        rec = filtered.copy()
        if ctx: rec = rec[rec["context_norm"].str.casefold() == str(ctx).casefold()]
        if sent and sent in ["Positive","Negative","Neutral"]:
            rec = rec[rec["sentiment_norm"].str.casefold() == str(sent).casefold()]
        if "id" in rec.columns and art.get("id") is not None:
            rec = rec[rec["id"] != art.get("id")]
        if rec.empty:
            st.info("No recommendations available right now.")
        else:
            for i, (_, r) in enumerate(rec.head(3).iterrows()):
                st.markdown('<div class="article-wrap"><div class="article-card">', unsafe_allow_html=True)
                with st.container():
                    st.markdown(f"**[{r.get('title','(no title)')}]({r.get('url','#')})**")
                    ddstr = _fmt_date_safe(r.get("date"))
                    st.markdown(_render_badges(
                        r.get("source_norm",""),
                        r.get("context_norm",""),
                        r.get("language_label",""),
                        r.get("sentiment_norm",""),
                        ddstr
                    ), unsafe_allow_html=True)
                    st.markdown(f"*{str(r.get('content',''))[:150]}...*")
                    key_id = str(r.get('id')) if r.get('id') is not None else f"rec{i}"
                    if st.button("Read Article", key=f"rec_{key_id}_{i}"):
                        log_event("open_article", {
                            "id": r.get('id'),
                            "title": r.get('title'),
                            "context": r.get('context_norm')
                        })
                        ss.selected_article = r.to_dict()
                        st.rerun()
                st.markdown('</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        if st.button("⬅ Back to list"):
            ss["selected_article"] = None
            st.rerun()

        st.stop()

    if show_analytics:
        a, b, c = st.columns(3)
        with a:
            st.markdown('<div class="card viz"><div class="sec-title">Articles Over Time <span class="subtle">(filtered)</span></div>', unsafe_allow_html=True)
            if "date" in filtered.columns and filtered["date"].notna().any():
                daily = (
                    filtered.assign(_d=filtered["date"].dt.date)
                            .groupby("_d").size().reset_index(name="count")
                            .rename(columns={"_d": "date"})
                )
                fig = px.line(daily, x="date", y="count", markers=True, title="")
                fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=260)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No date information available.")
            st.markdown('</div>', unsafe_allow_html=True)

        with b:
            st.markdown('<div class="card viz"><div class="sec-title">Articles by Sources</div>', unsafe_allow_html=True)
            ser = _series_or_default(filtered, "source_norm").astype(str).str.strip()
            ser = ser.replace("", pd.NA).dropna()
            dfc = ser.value_counts().reset_index()
            if not dfc.empty:
                dfc.columns = ["source","count"]
                fig = px.bar(dfc.head(10), x="count", y="source", orientation="h", title="")
                fig.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=260)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No source data available.")
            st.markdown('</div>', unsafe_allow_html=True)

        with c:
            st.markdown('<div class="card viz"><div class="sec-title">Sentiment Distribution</div>', unsafe_allow_html=True)
            sen = _series_or_default(filtered, "sentiment_norm").astype(str).str.strip()
            dfs = sen.value_counts().reset_index()
            if not dfs.empty:
                dfs.columns = ["sentiment","count"]
                fig = px.pie(dfs, values="count", names="sentiment", hole=0.55, title="")
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=260)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No sentiment data available.")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card viz"><div class="sec-title">Source × Sentiment Heatmap</div>', unsafe_allow_html=True)
        if not filtered.empty:
            hm = (
                filtered.assign(_cnt=1)
                        .pivot_table(index="source_norm", columns="sentiment_norm", values="_cnt", aggfunc="sum", fill_value=0)
            )
            if not hm.empty:
                sent_order = [s for s in ["Positive","Neutral","Negative"] if s in hm.columns] + \
                             [s for s in hm.columns if s not in ["Positive","Neutral","Negative"]]
                hm = hm.reindex(columns=sent_order)
                fig_hm = px.imshow(hm.values, x=list(hm.columns), y=list(hm.index), aspect="auto", labels=dict(color="Count"))
                fig_hm.update_layout(margin=dict(l=0,r=0,t=0,b=0), height=320)
                st.plotly_chart(fig_hm, use_container_width=True)
            else:
                st.info("No data for heatmap.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("---")

    if filtered.empty:
        st.info("No articles found.")
        return

    st.markdown('<div class="card"><div class="sec-title">Articles</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="meta-row" style="margin-bottom:8px;">'
        f'<span class="tag">Total: {len(filtered)}</span>'
        f'</div>', unsafe_allow_html=True
    )

    page_size = st.selectbox("Articles per page", options=[8,16,24,40],
                             index=[8,16,24,40].index(ss.get("articles_page_size", 8)))
    ss["articles_page_size"] = int(page_size)
    per_page = ss["articles_page_size"]

    if "date" in filtered.columns and filtered["date"].notna().any():
        sorted_df = filtered.sort_values("date", ascending=False, kind="mergesort")
    else:
        random.seed(42)
        sorted_df = filtered.sample(frac=1.0, random_state=42)

    total = len(sorted_df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    ss["current_page"] = max(1, min(ss.get("current_page", 1), total_pages))

    start_i = (ss["current_page"] - 1) * per_page
    page_df = sorted_df.iloc[start_i:start_i + per_page]

    st.subheader(f"Showing {len(page_df)} of {total} (Page {ss['current_page']} / {total_pages})", help="After filtering")

    for i, (idx, row) in enumerate(page_df.iterrows()):
        st.markdown('<div class="article-wrap"><div class="article-card">', unsafe_allow_html=True)
        with st.container():
            colA, colB = st.columns([0.72, 0.28])
            with colA:
                st.markdown(f"**[{row.get('title','(no title)')}]({row.get('url','#')})**")
                dstr = _fmt_date_safe(row.get("date"))
                st.markdown(_render_badges(
                    row.get("source_norm",""),
                    row.get("context_norm",""),
                    row.get("language_label",""),
                    row.get("sentiment_norm",""),
                    dstr
                ), unsafe_allow_html=True)
                content_preview = str(row.get('content',''))
                if len(content_preview) > 250:
                    st.markdown("<div style='margin-top:6px'></div>" + f"*{content_preview[:250]}...*", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='margin-top:6px'></div>" + content_preview, unsafe_allow_html=True)
            with colB:
                tsec = row.get("t_total_sec") or 0
                est = max(0.1, round(float(tsec)/60.0, 1)) if tsec else max(0.1, round(max(0.5, len(str(row.get('content','')))/1000), 1))
                st.metric("Read Time (est.)", f"{est} min")

                key_id = str(row.get('id')) if row.get('id') is not None else f"idx{idx}"
                if st.button("Open Article", key=f"read_{key_id}_{i}"):
                    log_event("open_article", {
                        "id": row.get('id'),
                        "title": row.get('title'),
                        "context": row.get('context_norm')
                    })
                    ss.selected_article = row.to_dict()
                    st.rerun()
        st.markdown('</div></div>', unsafe_allow_html=True)

    if total_pages > 1:
        nums = list(range(max(1, ss["current_page"] - 4), min(total_pages, ss["current_page"] + 4) + 1))
        st.markdown('<div class="pager">', unsafe_allow_html=True)
        cprev, *cc, cnext = st.columns(len(nums)+2)
        with cprev:
            if ss["current_page"] > 1 and st.button("‹ Prev"):
                ss["current_page"] -= 1; st.rerun()
        for i, p in enumerate(nums):
            with cc[i]:
                label = "pill active" if p == ss["current_page"] else "pill"
                if st.button(f"{p}", key=f"page_{p}"):
                    ss["current_page"] = p; st.rerun()
                st.markdown(f'<div class="{label}" style="display:none">{p}</div>', unsafe_allow_html=True)
        with cnext:
            if ss["current_page"] < total_pages and st.button("Next ›"):
                ss["current_page"] += 1; st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)