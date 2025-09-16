__all__ = ["admin_dashboard"]
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime
from pymongo.errors import DuplicateKeyError
from auth import hash_pw
from storage import (
    get_db,
    list_users, list_pending_users,
    find_user_by_username, create_user, update_user_by_username,
    approve_user, reject_user,  
)

def _inject_css():
    st.markdown("""
    <style>
      .kpi-card{border-radius:16px;padding:16px;background:linear-gradient(145deg,#fff 0%,#f8fafc 100%);
        border:1px solid #e6eaf1;box-shadow:0 10px 24px rgba(15,23,42,.08),inset 0 1px 0 rgba(255,255,255,.6);text-align:center;}
      .kpi-card.blue{background:linear-gradient(145deg,#e9f2ff 0%,#fff 70%);}
      .kpi-card.green{background:linear-gradient(145deg,#e9fbf3 0%,#fff 70%);}
      .kpi-card.pink{background:linear-gradient(145deg,#fdeef6 0%,#fff 70%);}
      .kpi-card.gold{background:linear-gradient(145deg,#fff7e6 0%,#fff 70%);}
      .kpi-card.purple{background:linear-gradient(145deg,#f1e8ff 0%,#fff 70%);}
      .kpi-card.slate{background:linear-gradient(145deg,#eef2f7 0%,#fff 70%);}
      .kpi-title{font-size:12px;color:#64748b;margin:0 0 6px 0;letter-spacing:.2px;display:flex;gap:8px;align-items:center;justify-content:center;}
      .kpi-emoji{font-size:14px;}
      .kpi-value{font-size:30px;font-weight:800;color:#0f172a;margin:0;}
      .card{border:1px solid #e6eaf1;border-radius:14px;padding:12px 14px;background:#fff;box-shadow:0 8px 22px rgba(16,24,40,.06);margin-bottom:12px;}
      .sec-title{font-size:16px;font-weight:800;color:#0f172a;margin:6px 0 10px 0;display:flex;align-items:center;gap:10px;}
      .small-note{color:#6b7280;font-size:12px;margin-top:6px;}
      .chip{font-size:11px;padding:2px 8px;border-radius:999px;background:#eff6ff;color:#1d4ed8;border:1px solid #dbeafe;}
      .pending-row{display:flex;align-items:center;justify-content:space-between;border:1px solid #e6eaf1;border-radius:12px;padding:10px 12px;margin:6px 0;}
      .pending-meta{display:flex;gap:10px;flex-wrap:wrap;color:#475569;font-size:13px;}
      .badge{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid #e6eaf1;background:#f8fafc;color:#334155;}
      .actions{display:flex;gap:8px;}
    </style>
    """, unsafe_allow_html=True)

def _kpi_card(title, value, emoji, color):
    val = "0" if value is None else f"{value}"
    st.markdown(f"""
      <div class="kpi-card {color}">
        <div class="kpi-title"><span class="kpi-emoji">{emoji}</span>{title}</div>
        <div class="kpi-value">{val}</div>
      </div>
    """, unsafe_allow_html=True)

def _scalarize(v):
    import pandas as _pd
    if v is None or (isinstance(v, float) and _pd.isna(v)): return ""
    if isinstance(v, list): return ", ".join(str(x).strip() for x in v if str(x).strip())
    if isinstance(v, dict):
        for k in ("name","title","label","value","id","source","context","sentiment"):
            if v.get(k): return str(v[k]).strip()
        return str(v)
    return str(v).strip()

def _read_all_articles(db) -> pd.DataFrame:
    rows = list(db.articles.find({}, {"_id":0,"id":1,"source":1,"fetched_at":1,"context":1,"language":1}))
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["id","source","fetched_at","context","language"])
    if not df.empty:
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], errors="coerce")
        df["source"]  = df.get("source","").apply(_scalarize).astype(str).str.strip()
        df["context"] = df.get("context","").apply(_scalarize).astype(str).str.strip().replace("", "General")
        df["language"]= df.get("language","").apply(_scalarize).astype(str).str.strip()
    return df

def _read_all_logs(db) -> pd.DataFrame:
    rows = list(db.logs.find({}, {"_id":0,"ts":1,"user":1,"event":1,"meta":1}))
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["ts","user","event","meta"])
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df["event"] = df["event"].astype(str).str.lower()
    return df

def _reads_by_context(arts: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    if not logs.empty and "open_article" in logs["event"].unique():
        l = logs[logs["event"]=="open_article"].copy()
        l["aid"] = l["meta"].apply(lambda m: str((m or {}).get("id")))
        a = arts.copy()
        a["id"] = a.get("id", pd.Series(dtype=str)).apply(lambda x: str(x))
        a["context"] = a.get("context", pd.Series(dtype=str)).astype(str).str.strip().replace("", "General")
        m = l.merge(a[["id","context"]], left_on="aid", right_on="id", how="left")
        s = m["context"].fillna("General").value_counts()
    else:
        s = arts.get("context", pd.Series(dtype=str)).value_counts() if not arts.empty else pd.Series(dtype=int)
    if s.empty:
        return pd.DataFrame(columns=["label","reads"])
    out = s.reset_index()
    out.columns = ["label","reads"]
    return out

def _articles_per_day(arts: pd.DataFrame) -> pd.DataFrame:
    if arts.empty or "fetched_at" not in arts.columns:
        return pd.DataFrame(columns=["date","count"])
    d = arts.copy()
    d["date"] = d["fetched_at"].dt.date
    agg = d.groupby("date").size().reset_index(name="count")
    agg["date"] = pd.to_datetime(agg["date"])
    return agg.sort_values("date")

def _dau_last_30(logs: pd.DataFrame) -> pd.DataFrame:
    if logs.empty: return pd.DataFrame(columns=["date","users"])
    d = logs.copy()
    d = d[d["user"].notna()]
    d["date"] = d["ts"].dt.date
    out = d.groupby("date")["user"].nunique().reset_index(name="users")
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").tail(30)
    return out

def _mau_from_logs(logs: pd.DataFrame) -> int:
    if logs.empty: return 0
    cutoff = logs["ts"].max() - pd.Timedelta(days=30)
    d = logs[logs["ts"] >= cutoff]
    return int(d["user"].dropna().nunique())

def _top_readers(logs: pd.DataFrame, k=10) -> pd.DataFrame:
    if logs.empty: return pd.DataFrame(columns=["user","reads"])
    l = logs[(logs["event"]=="open_article") & (logs["user"].notna())]
    if l.empty: return pd.DataFrame(columns=["user","reads"])
    out = l["user"].value_counts().head(k).reset_index()
    out.columns = ["user","reads"]
    return out.sort_values("reads")


def admin_dashboard(add_notification, show_notifications):
    _inject_css()
    st.header("Admin Panel")
    show_notifications()

    db = get_db()
    users   = list_users()
    pending = list_pending_users()
    logs    = _read_all_logs(db)
    arts    = _read_all_articles(db)

    try:
        total_articles_real = int(db.articles.estimated_document_count())
    except Exception:
        total_articles_real = int(len(arts))
    total_users = len(users)
    logins_cnt  = int((logs["event"] == "login").sum()) if not logs.empty else 0
    reads_cnt   = int((logs["event"] == "open_article").sum()) if not logs.empty else 0
    fetch_jobs  = int((logs["event"] == "fetch_articles").sum()) if not logs.empty else 0
    pending_ct  = len(pending)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: _kpi_card("Users", total_users, "👥", "blue")
    with c2: _kpi_card("Logins", logins_cnt, "🔐", "green")
    with c3: _kpi_card("Reads", reads_cnt, "📖", "pink")
    with c4: _kpi_card("Total Articles", total_articles_real, "🗞️", "gold")
    with c5: _kpi_card("Pending Approvals", pending_ct, "⏳", "purple")
    with c6: _kpi_card("Fetch Jobs", fetch_jobs, "⚙️", "slate")

    st.markdown("---")

    st.markdown('<div class="card"><div class="sec-title">Active Users — DAU (Last 30 days) <span class="chip">stickiness</span></div>', unsafe_allow_html=True)
    dau = _dau_last_30(logs)
    if dau.empty:
        st.info("No user activity yet.")
    else:
        mau = _mau_from_logs(logs)
        dau_mean = int(dau["users"].mean()) if not dau.empty else 0
        stickiness = round((dau_mean / max(mau, 1)) * 100, 1) if mau else 0.0
        colA, colB = st.columns([3,1])
        with colA:
            fig = px.line(dau, x="date", y="users", markers=True)
            fig.update_layout(height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_title="", yaxis_title="Unique users")
            st.plotly_chart(fig, use_container_width=True)
        with colB:
            st.metric("MAU (30d)", mau)
            st.metric("Avg DAU", dau_mean)
            st.metric("Stickiness", f"{stickiness}%")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sec-title">Reads by Context (All Time)</div>', unsafe_allow_html=True)
    ctx_df = _reads_by_context(arts, logs)
    if ctx_df.empty:
        st.info("No reads/contexts yet.")
    else:
        tot = int(ctx_df["reads"].sum())
        dfc = ctx_df.sort_values("reads", ascending=True).copy()
        dfc["percent"] = (dfc["reads"]/max(tot,1)*100).round(1)
        dfc["label2"] = dfc["label"] + " (" + dfc["percent"].astype(str) + "%)"
        fig_ctx = px.bar(dfc, x="reads", y="label2", orientation="h", text="reads")
        fig_ctx.update_layout(height=340, margin=dict(l=0,r=0,t=0,b=0), xaxis_title="Reads", yaxis_title="")
        fig_ctx.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_ctx, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sec-title">Events per Day (All Time)</div>', unsafe_allow_html=True)
    if logs.empty:
        st.info("No logs yet.")
    else:
        d = logs.copy()
        d["day"] = d["ts"].dt.date
        d["is_login"] = (d["event"]=="login").astype(int)
        d["is_read"]  = (d["event"]=="open_article").astype(int)
        daily = d.groupby("day")[["is_login","is_read"]].sum().reset_index()
        plot_df = daily.melt(id_vars="day", var_name="metric", value_name="count")
        plot_df["metric"] = plot_df["metric"].map({"is_login":"Logins","is_read":"Reads"})
        fig = px.bar(plot_df, x="day", y="count", color="metric")
        fig.update_layout(height=280, margin=dict(l=0,r=0,t=0,b=0), xaxis_title="", yaxis_title="Events", barmode="stack")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sec-title">Articles per Day (All Time)</div>', unsafe_allow_html=True)
    apd = _articles_per_day(arts)
    if apd.empty:
        st.info("No articles yet.")
    else:
        fig_apd = px.line(apd, x="date", y="count", markers=True)
        fig_apd.update_layout(height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_title="", yaxis_title="Articles")
        st.plotly_chart(fig_apd, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sec-title">Top Readers (All Time)</div>', unsafe_allow_html=True)
    tr = _top_readers(logs, k=10)
    if tr.empty:
        st.info("No reads yet.")
    else:
        fig_tr = px.bar(tr, x="reads", y="user", orientation="h", text="reads")
        fig_tr.update_layout(height=300, margin=dict(l=0,r=0,t=0,b=0), xaxis_title="Reads", yaxis_title="")
        fig_tr.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_tr, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    st.markdown('<div class="card"><div class="sec-title">Pending Approvals</div>', unsafe_allow_html=True)
    if pending:
        for u in pending:
            uname = u.get("username","")
            email = u.get("email","")
            jdate = u.get("join_date")
            jstr = ""
            try:
                jstr = pd.to_datetime(jdate).strftime("%Y-%m-%d %H:%M") if jdate else ""
            except Exception:
                jstr = str(jdate or "")
            col1, col2 = st.columns([3,1])
            with col1:
                st.markdown(
                    f'<div class="pending-row"><div class="pending-meta">'
                    f'<span class="badge">@{uname}</span>'
                    f'<span class="badge">{email}</span>'
                    f'<span class="badge">Joined: {jstr}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            with col2:
                a1, a2 = st.columns(2)
                with a1:
                    if st.button("Approve", key=f"approve_{uname}"):
                        try:
                            approve_user(uname)
                            st.success(f"Approved {uname}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to approve: {e}")
                with a2:
                    if st.button("Reject", key=f"reject_{uname}"):
                        try:
                            reject_user(uname)
                            st.warning(f"Rejected {uname}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reject: {e}")
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No pending users.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sec-title">Manage Users</div>', unsafe_allow_html=True)
    mu1, mu2 = st.columns(2)

    with mu1:
        st.markdown('<div class="card"><div class="sec-title">Add User</div>', unsafe_allow_html=True)
        with st.form("add_u_form", clear_on_submit=True):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            e = st.text_input("Email (required)")
            r = st.selectbox("Role", ["user","admin"], index=0)
            ok = st.form_submit_button("Create")
            if ok:
                if not u or not p or not e:
                    st.warning("Username, password, and email are required.")
                elif find_user_by_username(u):
                    st.warning("Username already exists.")
                elif db.users.find_one({"email": e}):
                    st.warning("Email already exists.")
                else:
                    doc = {
                        "username": u,
                        "email": e,
                        "password_hash": hash_pw(p),
                        "role": r,
                        "is_approved": True,
                        "join_date": datetime.utcnow(),
                        "time_spent_minutes": 0.0
                    }
                    try:
                        create_user(doc)
                        st.success(f"Added '{u}'")
                    except DuplicateKeyError:
                        st.error("Duplicate key error: username or email already exists.")
        st.markdown("</div>", unsafe_allow_html=True)

    with mu2:
        st.markdown('<div class="card"><div class="sec-title">Update User</div>', unsafe_allow_html=True)
        if len(users) > 0:
            sel = st.selectbox("User", [u["username"] for u in users], key="upd_sel")
            current = find_user_by_username(sel) or {}
            with st.form("upd_u_form"):
                em = st.text_input("Email", value=current.get("email",""))
                pw = st.text_input("New Password (optional)", type="password")
                rl = st.selectbox("Role", ["user","admin"], index=["user","admin"].index(current.get("role","user")))
                ap = st.checkbox("Approved", value=current.get("is_approved", False))
                save = st.form_submit_button("Save changes")
                if save:
                    if not em:
                        st.warning("Email cannot be empty (unique index).")
                    elif db.users.find_one({"email": em, "username": {"$ne": sel}}):
                        st.warning("This email is already used by another account.")
                    else:
                        upd = {"email": em, "role": rl, "is_approved": ap}
                        if pw: upd["password_hash"] = hash_pw(pw)
                        update_user_by_username(sel, upd)
                        st.success("User updated.")
        else:
            st.info("No users to update.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="sec-title">All Users</div>', unsafe_allow_html=True)
    users_df = pd.DataFrame(users)
    if not users_df.empty:
        users_df = users_df.drop(columns=["password","password_hash","_id","time_spent_minutes"], errors="ignore")
        cols = [c for c in ["username","email","role","is_approved","join_date"] if c in users_df.columns]
        if cols:
            st.dataframe(users_df[cols].set_index("username"), use_container_width=True, height=300)
    else:
        st.info("No users found.")
    st.markdown("</div>", unsafe_allow_html=True)