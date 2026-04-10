import frappe
from frappe import _


class RateLimiter:
    """Per-user rate limiting using Frappe's Redis cache."""

    def __init__(self, user: str):
        self.user = user
        self.settings = frappe.get_cached_doc("AI Bot Settings")

    def check(self):
        """Raise an exception if the user has exceeded rate limits."""
        cache = frappe.cache()

        # Per-minute check
        minute_key = f"ai_rate:{self.user}:minute"
        minute_count = cache.get(minute_key) or 0
        if int(minute_count) >= (self.settings.max_requests_per_minute or 10):
            frappe.throw(
                _("Rate limit exceeded. Please wait a moment."),
                title=_("Too Many Requests"),
            )

        # Per-day check
        day_key = f"ai_rate:{self.user}:day:{frappe.utils.today()}"
        day_count = cache.get(day_key) or 0
        if int(day_count) >= (self.settings.max_requests_per_day or 200):
            frappe.throw(
                _("Daily request limit reached. Try again tomorrow."),
                title=_("Daily Limit Exceeded"),
            )

    def increment(self):
        """Increment the counters after a successful request."""
        cache = frappe.cache()

        minute_key = f"ai_rate:{self.user}:minute"
        cache.incrby(minute_key, 1)
        cache.expire(minute_key, 60)

        day_key = f"ai_rate:{self.user}:day:{frappe.utils.today()}"
        cache.incrby(day_key, 1)
        cache.expire(day_key, 86400)
