"""Rate-limit rules for authentication (STAGE_2_DESIGN.md §6)."""

from app.core.rate_limit import RateLimitRule

SIGNUP_PER_IP = RateLimitRule("signup_ip", limit=5, window_seconds=3600)
LOGIN_PER_IP_AND_EMAIL = RateLimitRule("login_ip_email", limit=5, window_seconds=60)
LOGIN_PER_IP = RateLimitRule("login_ip", limit=30, window_seconds=60)
# Stops password guessing through a stolen, still-valid session.
PASSWORD_CHANGE_PER_USER = RateLimitRule("password_change_user", limit=5, window_seconds=900)
