import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta


class AIScheduledTask(Document):

    def before_insert(self):
        if not self.user:
            self.user = frappe.session.user
        self.run_count = self.run_count or 0
        next_run = self.calculate_next_run()
        if next_run:
            self.next_run = next_run

    def validate(self):
        self._validate_trigger_fields()

    def _validate_trigger_fields(self):
        if self.trigger_type == "Once" and not self.trigger_date:
            frappe.throw("Trigger Date is required for 'Once' tasks.")
        if self.trigger_type == "Weekly" and not self.day_of_week:
            frappe.throw("Day of Week is required for 'Weekly' tasks.")
        if self.trigger_type == "Monthly":
            dom = self.day_of_month or 0
            if not dom or dom < 1 or dom > 28:
                frappe.throw("Day of Month must be between 1 and 28 for 'Monthly' tasks.")

    def calculate_next_run(self):
        """Calculate the next run datetime based on trigger_type/date/time/day.

        Returns a datetime object, or None if the schedule cannot be determined.
        """
        time_str = str(self.trigger_time or "08:00:00")
        parts = time_str.split(":")
        hour = int(parts[0]) if len(parts) > 0 else 8
        minute = int(parts[1]) if len(parts) > 1 else 0

        if self.trigger_type == "Once":
            if self.trigger_date:
                trigger_date = frappe.utils.getdate(self.trigger_date)
                return datetime(
                    trigger_date.year, trigger_date.month, trigger_date.day, hour, minute, 0
                )
            return None

        now = frappe.utils.now_datetime()
        today = now.date()

        if self.trigger_type == "Daily":
            next_dt = datetime(today.year, today.month, today.day, hour, minute, 0)
            if next_dt <= now:
                next_dt += timedelta(days=1)
            return next_dt

        if self.trigger_type == "Weekly":
            day_map = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6,
            }
            target_day = day_map.get(self.day_of_week, 0)
            days_ahead = target_day - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_date = today + timedelta(days=days_ahead)
            return datetime(next_date.year, next_date.month, next_date.day, hour, minute, 0)

        if self.trigger_type == "Monthly":
            dom = min(self.day_of_month or 1, 28)
            if today.day < dom:
                next_date = today.replace(day=dom)
            else:
                if today.month == 12:
                    next_date = today.replace(year=today.year + 1, month=1, day=dom)
                else:
                    next_date = today.replace(month=today.month + 1, day=dom)
            return datetime(next_date.year, next_date.month, next_date.day, hour, minute, 0)

        return None
