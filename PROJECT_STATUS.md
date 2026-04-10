# ERPNext AI Bots — Project Status & Overview

**Last Updated:** 2026-03-28
**Version:** 1.1.0
**Branches:** community (free), commercial (SaaS + enterprise licensing)

---

## What This App Does

An **AI-powered brain for ERPNext** — a Frappe app that adds an intelligent chat assistant to any ERPNext installation. Think of it as having a smart colleague who has instant access to all company data and can take actions on your behalf.

---

## How It Helps Different Users

### For Employees (Day-to-Day Users)

| What They Can Do | Example |
|---|---|
| Ask business questions in plain English | "What are our top 10 customers this year?" |
| Create documents without navigating menus | "Create a quotation for Acme Corp, 10 units of Widget A" |
| Check their data | "What's my leave balance?" / "Show my salary slip" |
| Get reminders | "Remind me to follow up on that quotation in 3 days" |
| Email reports | "Email me the overdue invoices" |
| Look up anything | "What's the stock level of Widget A in all warehouses?" |

### For Managers / Decision Makers

| What They Can Do | Example |
|---|---|
| Get instant reports | "Show me P&L for last quarter" |
| Monitor cash flow | "What's our bank balance?" / "How much are receivables?" |
| Track overdue payments | "List all overdue invoices over 10,000" |
| Compare branch performance | "What are sales for Branch A vs Branch B this month?" |
| Schedule recurring reports | "Send me a weekly sales summary every Monday at 8am" |
| Run complex queries | AI writes SQL directly for JOINs, GROUP BY, aggregates |

### For Admins / IT

| What They Can Do | Example |
|---|---|
| One-time setup | Connect ChatGPT OAuth, set accent color, configure DB |
| Control access | Per-user ERPNext permissions enforced automatically |
| Monitor usage | Token costs tracked per session, audit logs for every tool call |
| Security | Prompt injection detection, field whitelisting, rate limiting, blocked DocTypes |
| Two editions | Community (free, BYOK) and Commercial (SaaS billing + enterprise licensing) |

---

## What's Built (Inventory)

| Component | Count | Details |
|---|---|---|
| **DocTypes** | 7 | Settings, Chat Session, Audit Log, Usage Record, Scheduled Task, Field Whitelist, OpenAI Token |
| **AI Tools** | 32 | Accounting (6), HR (5), Stock (5), Sales (5), Core CRUD (9), Email, SQL, Scheduling |
| **API Endpoints** | 11 | Chat (7), OAuth (5) |
| **Security Layers** | 4 | Permissions, Input Sanitizer, Prompt Defense, Rate Limiter |
| **Frontend** | 6 files | Chat widget, stream handler, OAuth UI, sidebar, categories |
| **Tests** | 6 files | 417 lines covering tools, permissions, sanitization, prompt defense |

### DocTypes

1. **AI Bot Settings** (Single) — Provider config, API keys, rate limits, security settings, accent color, DB connection
2. **AI Chat Session** — Conversation storage with JSON messages, categories (Finance/Sales/Stock/HR/General), pin support
3. **AI Audit Log** — Immutable record of every tool call (input, output, status, execution time, fields blocked)
4. **AI Usage Record** — Token counts and cost per request (90-day retention)
5. **AI Scheduled Task** — Cron-style recurring tasks (Once/Daily/Weekly/Monthly)
6. **AI Field Whitelist** — Per-DocType field access control for the AI
7. **AI OpenAI Token** — OAuth PKCE token storage (global shared connection)

### Tools (32 Total)

**Core (9):** get_document, get_list, create_document, update_document, submit_document, run_report, raw_sql, frappe_api, send_email

**Accounting (6):** get_trial_balance, get_outstanding_invoices, get_bank_balances, get_profit_and_loss, create_journal_entry, get_account_balance

**HR (5):** get_leave_balance, create_leave_application, get_salary_slip, get_attendance_summary, get_employee_info

**Stock (5):** get_stock_balance, create_stock_entry, get_warehouse_summary, get_item_info, get_reorder_levels

**Sales (5):** get_pipeline, create_quotation, get_sales_orders, get_customer_info (4-stage fuzzy matching), get_revenue_summary (territory/company/warehouse filters)

**Meta (2):** spawn_subagent (complex multi-step tasks), schedule_task (reminders/recurring reports)

### Security

- **Permission Guard** — Every tool checked against ERPNext's role-based permissions per user
- **Input Sanitizer** — Blocked DocTypes (User, Role, System Settings, etc.), blocked fields (password, api_key, etc.), field name validation, string length limits
- **Prompt Defense** — 19 regex patterns detecting injection attempts (jailbreak, prompt reveal, mode switching)
- **Rate Limiter** — Per-user per-minute (10) and per-day (200) limits via Redis

### AI Intelligence

- **Live Context Injection** — Company snapshot (top customers, items, invoices, overdue alerts, low stock) injected into system prompt, cached 5 min
- **Oracle System Prompt** — 300-line prompt making the AI a knowledgeable company colleague
- **Persistent Reasoning** — AI tries 3+ approaches before giving up, shows thinking steps
- **Time Awareness** — Current date/time/day for scheduling relative reminders
- **Raw SQL** — Direct database queries for complex analytics
- **Fuzzy Search** — Multi-stage customer/item matching (exact → partial → word-by-word)

---

## Architecture

```
User (ERPNext Desk)
  -> Chat Widget (JS/Socket.IO)
    -> API Layer (chat.py)
      -> Background Worker (frappe.enqueue)
        -> Orchestrator
          -> System Prompt + Live Context
          -> ChatGPT Codex API (OAuth) OR Anthropic API
            -> Tool Calls (32 tools)
              -> Permission Guard -> Sanitizer -> Execute -> Audit Log
            -> Stream response back via Socket.IO
              -> Thinking indicator -> Message bubbles -> Tables/Links
```

### Provider Support

| Provider | Status | Auth Method |
|---|---|---|
| OpenAI (ChatGPT OAuth) | Working | OAuth 2.0 PKCE, global shared token |
| Anthropic | Implemented | API key (BYOK) |
| Custom | Planned | Configurable endpoint |

### Editions

| Feature | Community | Commercial |
|---|---|---|
| All 32 tools | Yes | Yes |
| Chat widget | Yes | Yes |
| Scheduled tasks | Yes | Yes |
| Raw SQL | Yes | Yes |
| SaaS billing | No | Yes |
| Enterprise licensing | No | Yes |
| Cost gates/quotas | No | Yes |
| License server (benchi.io) | No | Yes |

---

## What's Missing / Needs Work

### Critical (Broken/Incomplete)

| Item | Status | Impact |
|---|---|---|
| AI responses silently fail | Token tracker crash fixed but some sessions still show 0 responses | Users think the AI is dead |
| Background session streaming | Frontend stops listening when switching conversations | Lost AI responses |
| Metric card rendering removed | Data shows as plain tables only | Looks basic |

### Important Features Missing

| Feature | What It Would Do | Priority |
|---|---|---|
| Notification system | Push notifications when scheduled tasks complete | High |
| Conversation export | Export chat as PDF/CSV for reporting or sharing | High |
| Multi-company support | Switch between companies within the same chat | High |
| File attachments | Upload files (invoices, receipts) and ask the AI about them | High |
| Voice input | Speech-to-text for mobile users | Medium |
| Dashboard page | Dedicated AI dashboard showing usage stats, cost, active tasks | Medium |
| Webhook/API triggers | External systems can trigger AI tasks | Medium |
| User onboarding | Guided first-use experience showing what the AI can do | Medium |
| Chat templates | Pre-built prompts ("Daily sales report", "Stock alert check") | Medium |
| Approval workflows | AI creates draft, sends approval request to manager | Medium |

### UI Polish Needed

| Issue | Current State | What's Needed |
|---|---|---|
| Data formatting | Plain markdown tables | Rich cards, charts, color-coded metrics |
| Mobile experience | Responsive but basic | Dedicated mobile-optimized layout |
| Typing indicator | "Thinking..." text, sometimes invisible | Animated skeleton loader |
| Session search | No search | Search across all conversations |
| Dark/light theme | Dark-first, light untested | Proper dual-theme support |

### Enterprise/Commercial Missing

| Feature | What It Would Do |
|---|---|
| Usage billing dashboard | Show token costs per user/department/month |
| Role-based tool access | Admin can enable/disable specific tools per role |
| SSO integration | Login with company's Active Directory/LDAP |
| Audit export | Export audit logs for compliance |
| Multi-tenant | Separate AI configs per company in multi-company setup |
| Custom tools API | Let admins create custom tools without code |

---

## Deployment

### Installation

```bash
bench get-app erpnext_ai_bots <repo-url>
bench --site <site> install-app erpnext_ai_bots
bench --site <site> migrate
bench build --app erpnext_ai_bots
bench restart
```

### Configuration

1. Go to **AI Bot Settings**
2. Set Provider to "OpenAI (ChatGPT OAuth)"
3. Click **Connect ChatGPT Account** in the OAuth section
4. Optionally set accent color, DB credentials, rate limits
5. The chat bubble appears on all ERPNext pages

---

## Tech Stack

- **Backend:** Python 3.10+, Frappe 15, ERPNext 15
- **AI Providers:** OpenAI ChatGPT Codex API (OAuth PKCE), Anthropic Claude
- **Database:** MariaDB 11.3 (via Frappe ORM + optional direct SQL)
- **Realtime:** Frappe Socket.IO (Node.js)
- **Cache:** Redis (context caching, rate limiting, OAuth state)
- **Frontend:** Vanilla JS + jQuery (Frappe desk integration)
- **Queue:** Redis Queue (RQ) for background AI processing
- **Dependencies:** anthropic, pymysql, requests, PyJWT, cryptography
