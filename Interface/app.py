import streamlit as st
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="InsightBot", page_icon="🧠")

from storage import (
    get_db, log_event, get_last_page,  
)
from auth import authenticate, login_form, register_form
from ui_admin import admin_dashboard
from ui_dashboard import user_dashboard

AUTO_REFRESH_INTERVAL_SEC = 5  

def logout():
    log_event("logout")
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.selected_article = None
    st.session_state.page = "login"

def init_state():
    ss = st.session_state
    ss.setdefault("page", get_last_page() or "login")
    ss.setdefault("authenticated", False)
    ss.setdefault("username", None)
    ss.setdefault("user_role", None)
    ss.setdefault("selected_article", None)
    ss.setdefault("notifications", [])
    ss.setdefault("articles_page_size", 8)
    ss.setdefault("theme", "light")
    ss.setdefault("search_q", "")
    ss.setdefault("date_range", (datetime.now().date() - timedelta(days=7), datetime.now().date()))
    ss.setdefault("selected_sentiment", "All")
    ss.setdefault("contexts", [])
    ss.setdefault("current_page", 1)
    ss.setdefault("auth_mode", "login")

    ss.setdefault("_last_auto_refresh", datetime.utcnow())


    ss.setdefault("_admin_default_tab", "Admin Panel")

def add_notification(message, type="info"):
    st.session_state.notifications.append({"message": message, "type": type})

def show_notifications():
    if st.session_state.notifications:
        for notif in st.session_state.notifications:
            if notif["type"] == "success": st.success(notif["message"])
            elif notif["type"] == "error": st.error(notif["message"])
            elif notif["type"] == "warning": st.warning(notif["message"])
            else: st.info(notif["message"])
        st.session_state.notifications = []

def set_auth_mode(mode):
    st.session_state.auth_mode = mode

def main():
    try:
        init_state()

        if st.session_state.authenticated:
            _ = get_db()  

            st.sidebar.title("InsightBot")
            st.sidebar.markdown(f"**User:** `{st.session_state.username}`")
            st.sidebar.markdown(f"**Role:** `{st.session_state.user_role}`")
            st.sidebar.button("Logout", on_click=logout)

         
            if st.session_state.user_role == "admin":
                main_tabs = ["Admin Panel", "Dashboard"]
                default_tab = st.session_state.get("_admin_default_tab", "Admin Panel")
            else:
                main_tabs = ["Dashboard"]
                default_tab = "Dashboard"

            selected_tab = st.sidebar.radio("Navigation", main_tabs, index=main_tabs.index(default_tab), key="nav_radio")

            if selected_tab == "Dashboard":
                user_dashboard()
            elif selected_tab == "Admin Panel" and st.session_state.user_role == "admin":
                st.session_state._admin_default_tab = "Admin Panel"
                admin_dashboard(add_notification, show_notifications)
            else:
                st.error("Access denied.")

            now = datetime.utcnow()
            article_open = bool(st.session_state.get("selected_article"))
            if not article_open:
                if (now - st.session_state._last_auto_refresh).total_seconds() >= AUTO_REFRESH_INTERVAL_SEC:
                    st.session_state._last_auto_refresh = now
                    st.rerun()

        else:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                show_notifications()
                if st.session_state.auth_mode == "login":
                    login_form(add_notification, set_auth_mode)
                else:
                    register_form(add_notification, set_auth_mode)

    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.stop()

if __name__ == "__main__":
    main()