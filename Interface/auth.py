import streamlit as st
import bcrypt
from storage import find_user_by_username, find_user_by_email, log_event, create_user
from datetime import datetime
from pymongo.errors import DuplicateKeyError

def hash_pw(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_pw(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), (hashed_password or "").encode('utf-8'))
    except Exception:
        return False

def authenticate(username, password):
    user = find_user_by_username(username)
    if user and check_pw(password, user.get('password_hash', '')):
        if not user.get('is_approved', True):
            return "User account is not approved. Please wait for an administrator to approve it."
        st.session_state.authenticated = True
        st.session_state.username = user['username']
        st.session_state.user_role = user.get('role', 'user')
        log_event("login")
        return None
    return "Invalid username or password."

def login_form(add_notification, set_auth_mode):
    st.markdown("""
        <style>
            .login-container {max-width: 350px; margin: 40px auto; padding: 25px; border-radius: 10px; background-color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.1);}
            .login-header {text-align: center; margin-bottom: 20px;}
            .login-header h1 {color: #2c3e50; font-size: 1.8rem; margin-bottom: 5px; font-weight: 600;}
            .login-header p {color: #7f8c8d; font-size: 0.9rem;}
        </style>
        <div class="login-container">
            <div class="login-header">
                <h1>InsightBot</h1>
                <p>Your intelligent news analysis platform</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", key="login_username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", key="login_password", placeholder="Enter your password")
        submitted = st.form_submit_button("Sign In", key="login_button")
        if submitted:
            error_message = authenticate(username, password)
            if error_message:
                add_notification(error_message, "error")
            else:
                st.rerun()

    st.markdown("""<div style="text-align:center;margin-top:10px;">Don't have an account?</div>""", unsafe_allow_html=True)
    if st.button("Register here", key="go_to_register_button"):
        set_auth_mode("register")
        st.rerun()

def register_form(add_notification, set_auth_mode):
    st.markdown("""
        <style>
            .register-container {max-width: 350px; margin: 20px auto; padding: 25px; border-radius: 10px; background-color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.1);}
            .register-header {text-align: center; margin-bottom: 20px;}
            .register-header h1 {color: #2c3e50; font-size: 1.8rem; margin-bottom: 5px; font-weight: 600;}
            .register-header p {color: #7f8c8d; font-size: 0.9rem;}
        </style>
        <div class="register-container">
            <div class="register-header">
                <h1>Create Account</h1>
                <p>Join InsightBot today</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    with st.form("register_form", clear_on_submit=False):
        new_username = st.text_input("Username", key="register_username", placeholder="Choose a username")
        new_email = st.text_input("Email", key="register_email", placeholder="Enter your email")
        new_password = st.text_input("Password", type="password", key="register_password", placeholder="Create a password")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password", placeholder="Confirm your password")
        submitted = st.form_submit_button("Sign Up", key="register_button")
        if submitted:
            if not new_username or not new_password or not new_email:
                add_notification("Username, email, and password are required.", "error")
            elif find_user_by_username(new_username):
                add_notification("Username already exists.", "warning")
            elif find_user_by_email(new_email):
                add_notification("Email already exists.", "warning")
            elif new_password != confirm_password:
                add_notification("Passwords do not match.", "error")
            else:
                try:
                    create_user({
                        "username": new_username,
                        "email": new_email,
                        "password_hash": hash_pw(new_password),
                        "role": "user",
                        "is_approved": False,
                        "join_date": datetime.utcnow(), 
                        "time_spent_minutes": 0
                    })
                    add_notification(f"Account for '{new_username}' created. Awaiting admin approval.", "success")
                    set_auth_mode("login")
                    st.rerun()
                except DuplicateKeyError:
                    add_notification("Duplicate key error: username or email already exists.", "error")

    st.markdown("""<div style="text-align:center;margin-top:10px;">Already have an account?</div>""", unsafe_allow_html=True)
    if st.button("Sign in here", key="go_to_login_button"):
        set_auth_mode("login")
        st.rerun()
