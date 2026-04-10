app_name = "erpnext_ai_bots"
app_title = "ERPNext AI Bots"
app_publisher = "Benchi"
app_description = "AI Agent platform for ERPNext with streaming, subagents, and role-based tool access"
app_version = "1.1.0"
app_icon = "octicon octicon-hubot"
app_color = "#6c5ce7"
app_email = "info@benchi.io"
app_license = "MIT"
required_apps = ["frappe", "erpnext"]

# JS/CSS includes in desk
app_include_js = [
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js",
    "/assets/erpnext_ai_bots/js/chat_stream.js",
    "/assets/erpnext_ai_bots/js/chat_widget.js",
    "/assets/erpnext_ai_bots/js/openai_oauth.js",
]
app_include_css = [
    "/assets/erpnext_ai_bots/css/chat_widget.css",
    "/assets/erpnext_ai_bots/css/openai_oauth.css",
]

# DocType permissions
has_permission = {
    "AI Chat Session": "erpnext_ai_bots.ai_bots.doctype.ai_chat_session.ai_chat_session.has_permission",
    "AI Direct Message": "erpnext_ai_bots.ai_bots.doctype.ai_direct_message.ai_direct_message.has_permission",
}

# Scheduled tasks
scheduler_events = {
    "cron": {
        "*/15 * * * *": [
            "erpnext_ai_bots.utils.task_runner.run_scheduled_tasks",
        ],
    },
    "daily_long": [
        "erpnext_ai_bots.utils.token_counter.cleanup_old_usage_records",
    ],
}

# Fixtures (default field whitelists shipped with the app)
fixtures = [
    {
        "dt": "AI Field Whitelist",
        "filters": [["ref_doctype", "in", [
            "Sales Invoice", "Purchase Invoice", "Journal Entry",
            "Sales Order", "Purchase Order", "Quotation",
            "Stock Entry", "Delivery Note", "Purchase Receipt",
            "Leave Application", "Salary Slip", "Employee",
            "Customer", "Supplier", "Item",
        ]]]
    }
]
