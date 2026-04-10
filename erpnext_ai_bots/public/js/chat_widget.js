// ── Chart helpers (standalone — must be before the class) ────────────────────

function _parseChartConfig(raw) {
    var config = { type: 'bar', title: '', labels: [], datasets: [], colors: [] };
    var lines = raw.split('\n');
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) continue;
        var colonIdx = line.indexOf(':');
        if (colonIdx === -1) continue;
        var key = line.substring(0, colonIdx).trim().toLowerCase();
        var val = line.substring(colonIdx + 1).trim();

        if (key === 'type') {
            config.type = val;
        } else if (key === 'title') {
            config.title = val;
        } else if (key === 'labels') {
            config.labels = val.split(',').map(function(s) { return s.trim(); });
        } else if (key === 'data') {
            config.datasets.push({
                label: config.title,
                data: val.split(',').map(function(s) { return parseFloat(s.trim()); }),
            });
        } else if (key === 'color') {
            config.colors.push(val);
        } else if (key === 'dataset') {
            // Format: "Label | 1,2,3 | #color"
            var parts = val.split('|').map(function(s) { return s.trim(); });
            config.datasets.push({
                label: parts[0] || '',
                data: (parts[1] || '').split(',').map(function(s) { return parseFloat(s.trim()); }),
            });
            if (parts[2]) config.colors.push(parts[2]);
        }
    }
    return config;
}

function _renderChart(canvas, raw) {
    var config = _parseChartConfig(raw);
    var rawAccent = getComputedStyle(document.documentElement)
        .getPropertyValue('--ai-accent');
    var accent = (rawAccent && rawAccent.trim()) ? rawAccent.trim() : '#8b5cf6';

    // Obsidian Console color palette
    var palette = [
        accent, '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#8b5cf6', '#f97316'
    ];

    // Assign custom colors from config.colors into each dataset
    for (var i = 0; i < config.colors.length && i < config.datasets.length; i++) {
        config.datasets[i]._color = config.colors[i];
    }

    var isPie = config.type === 'pie' || config.type === 'doughnut';
    var isHorizontal = config.type === 'horizontalBar';
    var chartType = isHorizontal ? 'bar' : config.type;

    var datasets = config.datasets.map(function(ds, idx) {
        var color = ds._color || palette[idx % palette.length];
        var result = {
            label: ds.label,
            data: ds.data,
            borderWidth: isPie ? 0 : 2,
        };
        if (isPie) {
            result.backgroundColor = ds.data.map(function(_, j) {
                return palette[j % palette.length] + 'cc';
            });
            result.borderColor = 'transparent';
        } else {
            result.backgroundColor = color + '33';
            result.borderColor = color;
            if (config.type === 'line') {
                result.tension = 0.3;
                result.fill = true;
                result.pointRadius = 4;
                result.pointBackgroundColor = color;
            }
        }
        return result;
    });

    // Destroy any existing chart on this canvas before creating a new one
    var existingChart = Chart.getChart(canvas);
    if (existingChart) existingChart.destroy();

    new Chart(canvas, {
        type: chartType,
        data: { labels: config.labels, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            indexAxis: isHorizontal ? 'y' : 'x',
            plugins: {
                title: {
                    display: !!config.title,
                    text: config.title,
                    color: '#e4e4e7',
                    font: { size: 14, weight: '600' },
                    padding: { bottom: 12 },
                },
                legend: {
                    display: config.datasets.length > 1 || isPie,
                    labels: {
                        color: '#a1a1aa',
                        font: { size: 11 },
                        boxWidth: 12,
                        padding: 12,
                    },
                },
                tooltip: {
                    backgroundColor: '#1e1e24',
                    titleColor: '#e4e4e7',
                    bodyColor: '#a1a1aa',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    cornerRadius: 6,
                    padding: 10,
                },
            },
            scales: isPie ? {} : {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                    ticks: { color: '#71717a', font: { size: 11 } },
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                    ticks: { color: '#71717a', font: { size: 11 } },
                },
            },
        },
    });
}

// ─────────────────────────────────────────────────────────────────────────────

frappe.provide("erpnext_ai_bots");

// ── Markdown table post-processor ───────────────────────────────────────────
// frappe.markdown() uses marked.js but may be configured without GFM tables.
// We detect raw markdown table syntax surviving in the HTML output and convert
// it to proper <table> elements.

erpnext_ai_bots.render_markdown = function (text) {
    if (!text) return "";

    // Step 0: Extract ```chart blocks BEFORE markdown processing so the
    // backtick fences are not mangled by marked.js.
    var charts = [];
    text = text.replace(/```chart\n([\s\S]*?)```/g, function(match, body) {
        charts.push(body.trim());
        return 'AICHART' + (charts.length - 1) + 'END';
    });

    // First pass: use Frappe's renderer
    let html = frappe.markdown(text) || "";

    // Second pass: convert any un-rendered markdown table blocks.
    // A markdown table is: one or more lines that start/end with | and contain
    // a separator row (|---|) somewhere in the block.
    html = html.replace(
        /(<p>)?((?:\|[^\n]+\|\n?)+)(<\/p>)?/g,
        function (match, open, block) {
            // Must contain a separator row to be a real table
            if (!/\|[\s\-:]+\|/.test(block)) return match;

            const raw_lines = block.trim().split("\n").map(l => l.trim()).filter(Boolean);
            if (raw_lines.length < 2) return match;

            const parse_row = (line) =>
                line.replace(/^\||\|$/g, "").split("|").map(c => c.trim());

            const header_cells = parse_row(raw_lines[0]);
            const is_sep = (line) => /^\|?[\s\-|:]+\|?$/.test(line);

            // Find separator row index
            let sep_idx = raw_lines.findIndex((l, i) => i > 0 && is_sep(l));
            if (sep_idx === -1) return match;

            const body_lines = raw_lines.slice(sep_idx + 1);

            const th_html = header_cells
                .map(c => `<th>${c}</th>`)
                .join("");
            const tr_html = body_lines
                .map(l => {
                    const cells = parse_row(l);
                    return `<tr>${cells.map(c => `<td>${c}</td>`).join("")}</tr>`;
                })
                .join("");

            return `<table><thead><tr>${th_html}</tr></thead><tbody>${tr_html}</tbody></table>`;
        }
    );

    // Third pass: Add code block headers with language label + copy button (ChatGPT style)
    html = html.replace(
        /<pre><code(?:\s+class="(?:language-)?(\w+)")?>([\s\S]*?)<\/code><\/pre>/g,
        function(match, lang, code) {
            var langLabel = lang || 'code';
            var uid = 'ai-cb-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
            var header = '<div class="ai-code-header">'
                + '<span class="ai-code-lang">' + langLabel + '</span>'
                + '<button class="ai-code-copy" data-code-id="' + uid + '" onclick="'
                + 'var el=document.getElementById(\'' + uid + '\');'
                + 'if(el){navigator.clipboard.writeText(el.textContent).then(function(){'
                + 'var b=document.querySelector(\'[data-code-id=&quot;' + uid + '&quot;]\');'
                + 'b.classList.add(\'copied\');b.innerHTML=\'&#10003; Copied\';'
                + 'setTimeout(function(){b.classList.remove(\'copied\');b.innerHTML=\'Copy\';},2000);'
                + '})}">'
                + 'Copy</button>'
                + '</div>';
            return '<pre>' + header + '<code id="' + uid + '">' + code + '</code></pre>';
        }
    );

    // Fourth pass: convert ERPNext document IDs into clickable links.
    // Maps document prefixes to their ERPNext URL route slugs.
    var _doctype_slugs = {
        "SAL-QTN": "quotation",
        "SI": "sales-invoice", "SINV": "sales-invoice",
        "PI": "purchase-invoice", "PINV": "purchase-invoice",
        "SO": "sales-order",
        "PO": "purchase-order",
        "DN": "delivery-note",
        "PR": "purchase-receipt",
        "JE": "journal-entry",
        "SE": "stock-entry",
        "PE": "payment-entry",
        "LC": "landed-cost-voucher",
        "QTN": "quotation",
        "ORD": "sales-order",
        "AI-CHAT": "ai-chat-session",
        "AI-TASK": "ai-scheduled-task",
    };

    html = html.replace(
        /\b((?:SAL-QTN|SI|PI|PO|SO|DN|PR|JE|SE|LC|PE|SINV|PINV|QTN|ORD|AI-CHAT|AI-TASK|IBMOL2?-\w+-\d+-\d+|LTH-\w+-\d+|IBKAN-\w+-\d+|IBTLK-\w+-\d+)-[\w-]*\d{3,})\b/g,
        function (match) {
            // Find the matching slug by checking prefixes (longest first)
            var slug = "";
            var prefixes = Object.keys(_doctype_slugs).sort(function(a, b) { return b.length - a.length; });
            for (var i = 0; i < prefixes.length; i++) {
                if (match.startsWith(prefixes[i])) {
                    slug = _doctype_slugs[prefixes[i]] + "/";
                    break;
                }
            }
            return (
                '<a href="/app/' + slug + encodeURIComponent(match) +
                '" class="ai-doc-link" target="_blank">' + match + "</a>"
            );
        }
    );

    // Final step: replace chart placeholders with canvas elements, then
    // schedule Chart.js initialisation after the bubble is in the DOM.
    if (charts.length) {
        var _timestamp = Date.now();
        for (var _ci = 0; _ci < charts.length; _ci++) {
            var chart_id = 'ai-chart-' + _timestamp + '-' + _ci;
            // Replace placeholder — may be wrapped in <p>, <strong>, or bare
            html = html.replace(
                new RegExp('<p>\\s*(?:<strong>)?\\s*AICHART' + _ci + 'END\\s*(?:</strong>)?\\s*</p>', 'g'),
                '<div class="ai-chart-container"><canvas id="' + chart_id + '"></canvas></div>'
            );
            html = html.replace(
                new RegExp('(?:<strong>)?AICHART' + _ci + 'END(?:</strong>)?', 'g'),
                '<div class="ai-chart-container"><canvas id="' + chart_id + '"></canvas></div>'
            );

            // Capture loop variables for the async callback
            (function(id, raw) {
                setTimeout(function() {
                    var canvas = document.getElementById(id);
                    if (canvas && typeof Chart !== 'undefined') {
                        _renderChart(canvas, raw);
                    }
                }, 100);
            })(chart_id, charts[_ci]);
        }
    }

    return html;
};

// ── Category helpers ─────────────────────────────────────────────────────────

erpnext_ai_bots.CATEGORIES = ["All", "Finance", "Sales", "Stock", "HR", "General"];

erpnext_ai_bots.CATEGORY_COLORS = {
    Finance: "green",
    Sales:   "blue",
    Stock:   "orange",
    HR:      "purple",
    General: "gray",
};

// ── ChatWidget ───────────────────────────────────────────────────────────────

erpnext_ai_bots.ChatWidget = class ChatWidget {
    constructor() {
        this.session_id = null;
        this.is_open = false;
        this.is_expanded = false;
        this.is_streaming = false;
        this.stream_handler = null;
        this.$current_message = null;
        this.current_message_text = "";
        this._active_category = "All";   // sidebar filter tab
        this._all_sessions = [];         // cached sessions array
        this._ctx_menu_target = null;    // session id under context menu
        this._last_message = null;       // last sent message text, for retry
        this._loading_session = false;   // guard against concurrent _load_session calls
        this._search_query = "";         // sidebar session search filter
        this._current_company = null;    // active company context
        this._all_companies = [];        // cached companies list
        // Feature 16: File attachments
        this._pending_attachment = null; // uploaded file waiting to be sent
        // Feature 17: Voice input
        this._is_recording = false;
        this._recognition = null;
        // Feature 17: ElevenLabs TTS
        this._elevenlabs_key = "";
        this._elevenlabs_voice_id = "21m00Tcm4TlvDq8ikWAM";
        // Feature: Reply, Forward, DM
        this._reply_to = null;          // { index, role, text } — message being replied to
        this._message_index = 0;        // running index for visible messages
        this._dm_mode = false;          // true when viewing DMs
        this._dm_user = null;           // currently open DM conversation partner
        this._dm_conversations = [];    // cached DM conversation list
        this._dm_unread_count = 0;      // total unread DMs
        this.render();
        this.bind_events();
        this._load_last_session();
        this._load_accent_color();
        this._load_companies();
        this._load_elevenlabs_config();
    }

    // ── Accent color ─────────────────────────────────────────────────

    async _load_accent_color() {
        // Fetch the accent_color setting from AI Bot Settings and apply it
        // as a CSS custom property so every --ai-accent reference updates.
        try {
            const r = await frappe.call({
                method: "frappe.client.get_value",
                args: { doctype: "AI Bot Settings", fieldname: "accent_color" },
                async: true,
            });
            const color = (r.message && r.message.accent_color) || "#6c5ce7";
            document.documentElement.style.setProperty("--ai-accent", color);
        } catch (e) {
            // Silently fall back to the CSS default (#6c5ce7)
        }
    }

    // ── Company selector ────────────────────────────────────────────

    async _load_companies() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.chat.get_companies",
                async: true,
            });
            this._all_companies = r.message || [];
            // Set default company from Frappe user defaults
            const default_co = frappe.defaults.get_default("company");
            if (!this._current_company && this._all_companies.length) {
                const found = this._all_companies.find(c => c.name === default_co);
                this._current_company = found ? found.name : this._all_companies[0].name;
            }
            this._render_company_badge();
        } catch (e) {
            // Silently fail — company context falls back to server-side default
        }
    }

    _render_company_badge() {
        const label = this._current_company || "...";
        this.$company_badge.text(label);
        this._render_company_dropdown();
    }

    _render_company_dropdown() {
        this.$company_dropdown.empty();
        for (const co of this._all_companies) {
            const is_active = co.name === this._current_company;
            const $opt = $(
                `<div class="ai-company-option${is_active ? " active" : ""}"
                      data-name="${frappe.utils.escape_html(co.name)}">
                    ${frappe.utils.escape_html(co.company_name || co.name)}
                </div>`
            );
            $opt.on("click", () => {
                this.$company_dropdown.hide();
                if (co.name === this._current_company) return;
                const old = this._current_company;
                this._current_company = co.name;
                this._render_company_badge();
                // System message so the user sees the switch in context
                const $sys = $(
                    `<div class="ai-msg ai-msg-bot ai-msg-system-note">
                        Switched to <strong>${frappe.utils.escape_html(co.company_name || co.name)}</strong>
                    </div>`
                );
                this.$messages.append($sys);
                this._scroll_bottom();
            });
            this.$company_dropdown.append($opt);
        }
    }

    // ── DOM ─────────────────────────────────────────────────────────

    render() {
        this.$btn = $(`
            <div class="ai-chat-btn" title="AI Assistant">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
            </div>
        `).appendTo("body");

        this.$panel = $(`
            <div class="ai-chat-panel" style="display:none">
                <div class="ai-chat-header">
                    <div class="ai-chat-header-left">
                        <span class="ai-chat-title">AI Assistant</span>
                        <span class="ai-company-badge" title="Click to switch company">...</span>
                    </div>
                    <div class="ai-chat-header-actions">
                        <button class="ai-chat-toggle-sidebar btn btn-xs" title="Toggle sidebar" style="display:none">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2">
                                <rect x="3" y="3" width="18" height="18" rx="2"/>
                                <line x1="9" y1="3" x2="9" y2="21"/>
                            </svg>
                        </button>
                        <button class="ai-chat-new-session btn btn-xs" title="New conversation">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2">
                                <line x1="12" y1="5" x2="12" y2="19"/>
                                <line x1="5" y1="12" x2="19" y2="12"/>
                            </svg>
                        </button>
                        <button class="ai-chat-help btn btn-xs" title="Help — see all commands">?</button>
                        <button class="ai-chat-export btn btn-xs" title="Export conversation">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                <polyline points="7 10 12 15 17 10"/>
                                <line x1="12" y1="15" x2="12" y2="3"/>
                            </svg>
                        </button>
                        <button class="ai-chat-expand btn btn-xs" title="Expand">
                            <svg class="expand-icon" width="14" height="14" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2">
                                <polyline points="15 3 21 3 21 9"/>
                                <polyline points="9 21 3 21 3 15"/>
                                <line x1="21" y1="3" x2="14" y2="10"/>
                                <line x1="3" y1="21" x2="10" y2="14"/>
                            </svg>
                            <svg class="shrink-icon" width="14" height="14" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2" style="display:none">
                                <polyline points="4 14 10 14 10 20"/>
                                <polyline points="20 10 14 10 14 4"/>
                                <line x1="14" y1="10" x2="21" y2="3"/>
                                <line x1="3" y1="21" x2="10" y2="14"/>
                            </svg>
                        </button>
                        <button class="ai-chat-close btn btn-xs">&times;</button>
                    </div>
                </div>

                <!-- Compact sessions bar (visible only in compact mode) -->
                <div class="ai-chat-sessions-bar" style="display:none">
                    <select class="ai-chat-session-select form-control form-control-sm"></select>
                </div>

                <!-- Main body: sidebar + messages -->
                <div class="ai-chat-body">
                    <!-- Sidebar (expanded mode only) -->
                    <div class="ai-chat-sidebar" style="display:none">
                        <div class="ai-sidebar-new-btn-wrap">
                            <button class="ai-sidebar-new-btn btn btn-sm btn-primary">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                                     stroke="currentColor" stroke-width="2.5">
                                    <line x1="12" y1="5" x2="12" y2="19"/>
                                    <line x1="5" y1="12" x2="19" y2="12"/>
                                </svg>
                                New Chat
                            </button>
                        </div>
                        <div class="ai-sidebar-search-wrap">
                            <input type="text" class="ai-sidebar-search form-control form-control-sm"
                                   placeholder="Search conversations..." />
                        </div>
                        <div class="ai-sidebar-mode-tabs">
                            <button class="ai-mode-tab active" data-mode="ai">AI Chats</button>
                            <button class="ai-mode-tab" data-mode="dm">DMs <span class="ai-dm-badge" style="display:none">0</span></button>
                        </div>
                        <div class="ai-sidebar-ai-section">
                            <div class="ai-sidebar-category-tabs">
                                ${erpnext_ai_bots.CATEGORIES.map(c =>
                                    `<button class="ai-cat-tab${c === "All" ? " active" : ""}" data-cat="${c}">${c}</button>`
                                ).join("")}
                            </div>
                            <div class="ai-sidebar-session-list"></div>
                        </div>
                        <div class="ai-sidebar-dm-section" style="display:none">
                            <div class="ai-dm-user-search-wrap">
                                <input type="text" class="ai-dm-user-search form-control form-control-sm"
                                       placeholder="Search users..." />
                            </div>
                            <div class="ai-dm-conversation-list"></div>
                            <button class="ai-dm-new-chat-btn btn btn-sm">+ New Message</button>
                        </div>
                    </div>

                    <!-- Chat area -->
                    <div class="ai-chat-main">
                        <div class="ai-chat-messages">
                            <div class="ai-templates-grid">
                                <div class="ai-template-card" data-prompt="Show me today's sales dashboard">
                                    <span class="ai-template-icon">📊</span>
                                    <span class="ai-template-text">Sales Dashboard</span>
                                </div>
                                <div class="ai-template-card" data-prompt="Rank all branches by sales this month with profit margins">
                                    <span class="ai-template-icon">🏢</span>
                                    <span class="ai-template-text">Branch Ranking</span>
                                </div>
                                <div class="ai-template-card" data-prompt="What is our gross profit margin this month by item group?">
                                    <span class="ai-template-icon">💰</span>
                                    <span class="ai-template-text">Gross Margin</span>
                                </div>
                                <div class="ai-template-card" data-prompt="Show me inventory days and slow movers">
                                    <span class="ai-template-icon">📦</span>
                                    <span class="ai-template-text">Inventory Health</span>
                                </div>
                                <div class="ai-template-card" data-prompt="What is our stock turnover rate this month vs last month?">
                                    <span class="ai-template-icon">🔄</span>
                                    <span class="ai-template-text">Stock Turnover</span>
                                </div>
                                <div class="ai-template-card" data-prompt="List all overdue invoices">
                                    <span class="ai-template-icon">⚠️</span>
                                    <span class="ai-template-text">Overdue Invoices</span>
                                </div>
                                <div class="ai-template-card" data-prompt="Email me a sales report for this month with charts">
                                    <span class="ai-template-icon">📧</span>
                                    <span class="ai-template-text">Email Report</span>
                                </div>
                                <div class="ai-template-card" data-prompt="What is our bank balance across all accounts?">
                                    <span class="ai-template-icon">🏦</span>
                                    <span class="ai-template-text">Bank Balances</span>
                                </div>
                            </div>
                        </div>
                        <div class="ai-chat-tool-indicator" style="display:none">
                            <div class="ai-tool-spinner"></div>
                            <span class="ai-tool-name"></span>
                        </div>
                        <!-- Reply preview bar -->
                        <div class="ai-reply-bar" style="display:none">
                            <div class="ai-reply-bar-content">
                                <span class="ai-reply-bar-label">Replying to</span>
                                <span class="ai-reply-bar-text"></span>
                            </div>
                            <button class="ai-reply-bar-close">&times;</button>
                        </div>
                        <div class="ai-chat-input-area">
                            <button class="ai-chat-attach btn btn-xs" title="Attach file">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                                     stroke="currentColor" stroke-width="2">
                                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                                </svg>
                            </button>
                            <input type="file" class="ai-chat-file-input" style="display:none"
                                   multiple accept="image/*,.pdf,.csv,.xlsx,.xls,.txt,.json,.docx,.doc,.tsv,.md,.log" />
                            <textarea class="ai-chat-input"
                                placeholder="Ask about your ERPNext data..."
                                rows="1"></textarea>
                            <button class="ai-chat-voice btn btn-xs" title="Voice input">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                                     stroke="currentColor" stroke-width="2">
                                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                                    <line x1="12" y1="19" x2="12" y2="23"/>
                                    <line x1="8" y1="23" x2="16" y2="23"/>
                                </svg>
                            </button>
                            <button class="ai-chat-send btn btn-primary btn-sm">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                                     stroke="currentColor" stroke-width="2">
                                    <line x1="22" y1="2" x2="11" y2="13"/>
                                    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `).appendTo("body");

        // Context menu (shared, appended to body)
        this.$ctx_menu = $(`
            <div class="ai-session-ctx-menu" style="display:none">
                <button class="ai-ctx-pin">Pin</button>
                <button class="ai-ctx-rename">Rename</button>
                <button class="ai-ctx-delete">Delete</button>
            </div>
        `).appendTo("body");

        // Message context menu (reply / forward)
        this.$msg_ctx_menu = $(`
            <div class="ai-msg-ctx-menu" style="display:none">
                <button class="ai-msg-ctx-reply">Reply</button>
                <button class="ai-msg-ctx-forward">Forward</button>
                <button class="ai-msg-ctx-copy">Copy</button>
            </div>
        `).appendTo("body");

        // Forward user picker modal
        this.$forward_modal = $(`
            <div class="ai-forward-modal" style="display:none">
                <div class="ai-forward-modal-inner">
                    <div class="ai-forward-header">
                        <span>Forward to...</span>
                        <button class="ai-forward-close">&times;</button>
                    </div>
                    <input type="text" class="ai-forward-search form-control form-control-sm"
                           placeholder="Search users..." />
                    <div class="ai-forward-user-list"></div>
                    <div class="ai-forward-note-wrap">
                        <input type="text" class="ai-forward-note form-control form-control-sm"
                               placeholder="Add a note (optional)..." />
                    </div>
                </div>
            </div>
        `).appendTo("body");

        // Export dropdown (shared, appended to body)
        this.$export_menu = $(`
            <div class="ai-export-menu" style="display:none">
                <button class="ai-export-html">Export as HTML (Print / PDF)</button>
                <button class="ai-export-csv">Export as CSV</button>
            </div>
        `).appendTo("body");

        this.$messages         = this.$panel.find(".ai-chat-messages");
        this.$input            = this.$panel.find(".ai-chat-input");
        this.$tool_indicator   = this.$panel.find(".ai-chat-tool-indicator");
        this.$sidebar          = this.$panel.find(".ai-chat-sidebar");
        this.$session_list     = this.$panel.find(".ai-sidebar-session-list");
        this.$company_badge    = this.$panel.find(".ai-company-badge");
        this.$company_dropdown = $('<div class="ai-company-dropdown"></div>').appendTo("body");
        // @ mention popup
        this.$mention_popup = $(`
            <div class="ai-mention-popup" style="display:none"></div>
        `).appendTo("body");

        this.$reply_bar        = this.$panel.find(".ai-reply-bar");
        this.$dm_section       = this.$panel.find(".ai-sidebar-dm-section");
        this.$dm_conv_list     = this.$panel.find(".ai-dm-conversation-list");
        this.$ai_section       = this.$panel.find(".ai-sidebar-ai-section");
    }

    // ── Events ──────────────────────────────────────────────────────

    bind_events() {
        this.$btn.on("click", () => this.toggle());
        this.$panel.find(".ai-chat-close").on("click", () => this.toggle());
        this.$panel.find(".ai-chat-new-session").on("click", () => this.new_session());
        this.$panel.find(".ai-sidebar-new-btn").on("click", () => this.new_session());
        this.$panel.find(".ai-chat-toggle-sidebar").on("click", () => this._toggle_sidebar());
        this.$panel.find(".ai-chat-expand").on("click", () => this.toggle_expand());
        this.$panel.find(".ai-chat-send").on("click", () => this.send());

        this.$input.on("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                // If mention popup is open, select it instead of sending
                if (this.$mention_popup.is(":visible")) {
                    this.$mention_popup.find(".ai-mention-item").first().trigger("click");
                    return;
                }
                this.send();
            }
        });

        // @ mention autocomplete in DM mode
        this.$input.on("input", () => {
            if (this._dm_mode && this._dm_user) {
                const val = this.$input.val();
                // Detect @mention pattern: @ at start or after space, with optional partial name
                const mention_match = val.match(/(?:^|\s)@(\w*)$/);
                if (mention_match) {
                    const partial = mention_match[1].toLowerCase();
                    const ai_name = (this._ai_name || "AI Oracle").toLowerCase();
                    // Show popup if partial matches the AI name or is empty (just @)
                    if (!partial || ai_name.startsWith(partial) || "ai".startsWith(partial)) {
                        this._show_mention_popup();
                    } else {
                        this._hide_mention_popup();
                    }
                } else {
                    this._hide_mention_popup();
                }
            }
        });

        // Auto-resize textarea
        this.$input.on("input", function () {
            this.style.height = "auto";
            this.style.height = Math.min(this.scrollHeight, 120) + "px";
        });

        // Auto-convert long pastes (>500 chars) to a file attachment
        this.$input.on("paste", () => {
            setTimeout(() => {
                const text = this.$input.val();
                if (text.length > 500) {
                    this._convert_paste_to_file(text);
                }
            }, 50);
        });

        // Compact mode session selector
        this.$panel.find(".ai-chat-session-select").on("change", (e) => {
            const sid = $(e.target).val();
            if (sid) this._load_session(sid);
        });

        // Category tabs (delegated)
        this.$panel.on("click", ".ai-cat-tab", (e) => {
            const cat = $(e.currentTarget).data("cat");
            this._set_category_tab(cat);
        });

        // Context menu actions
        this.$ctx_menu.find(".ai-ctx-rename").on("click", (e) => {
            e.stopPropagation();
            const sid = this._ctx_menu_target;
            this._hide_ctx_menu();
            if (!sid) return;
            const session = this._all_sessions.find(s => s.name === sid);
            const current_title = session ? (session.title || sid) : sid;
            const new_title = prompt(__("Rename conversation"), current_title);
            if (new_title && new_title.trim() && new_title.trim() !== current_title) {
                this._rename_session(sid, new_title.trim());
            }
        });

        this.$ctx_menu.find(".ai-ctx-delete").on("click", (e) => {
            e.stopPropagation();
            const sid = this._ctx_menu_target;
            this._hide_ctx_menu();
            if (!sid) return;
            this._delete_session(sid);
        });

        this.$ctx_menu.find(".ai-ctx-pin").on("click", (e) => {
            e.stopPropagation();
            const sid = this._ctx_menu_target;
            this._hide_ctx_menu();
            if (!sid) return;
            this._toggle_pin_session(sid);
        });

        // Close context menu on outside mousedown — using mousedown instead of
        // click so it fires before the menu button's own click handler, avoiding
        // the race condition where _ctx_menu_target gets nulled prematurely.
        $(document).on("mousedown.ai_ctx", (e) => {
            if (!$(e.target).closest(".ai-session-ctx-menu").length) {
                this._hide_ctx_menu();
            }
        });

        // Export button — toggles dropdown below the button
        this.$panel.find(".ai-chat-export").on("click", (e) => {
            e.stopPropagation();
            if (this.$export_menu.is(":visible")) {
                this.$export_menu.hide();
                return;
            }
            const btn_rect = e.currentTarget.getBoundingClientRect();
            const menu_w = 210;
            const left = Math.min(btn_rect.left, window.innerWidth - menu_w - 8);
            const top  = btn_rect.bottom + 4;
            this.$export_menu.css({ left: left, top: top }).show();
        });

        // Export menu actions
        this.$export_menu.find(".ai-export-html").on("click", () => {
            this.$export_menu.hide();
            this._export_html();
        });

        this.$export_menu.find(".ai-export-csv").on("click", () => {
            this.$export_menu.hide();
            this._export_csv();
        });

        // Close export menu on outside click
        $(document).on("mousedown.ai_export", (e) => {
            if (
                !$(e.target).closest(".ai-export-menu").length &&
                !$(e.target).closest(".ai-chat-export").length
            ) {
                this.$export_menu.hide();
            }
        });

        // Help panel
        this.$panel.find(".ai-chat-help").on("click", () => {
            this._show_help();
        });

        // Sidebar search — instant client-side filtering
        this.$panel.on("input", ".ai-sidebar-search", (e) => {
            this._search_query = e.target.value.trim().toLowerCase();
            this._render_sidebar_sessions();
        });

        // Company badge — toggle dropdown with fixed positioning
        this.$company_badge.on("click", (e) => {
            e.stopPropagation();
            const is_visible = this.$company_dropdown.is(":visible");
            if (!is_visible) {
                const rect = this.$company_badge[0].getBoundingClientRect();
                this.$company_dropdown.css({
                    top: rect.bottom + 6,
                    left: Math.max(rect.left, 10),
                }).show();
            } else {
                this.$company_dropdown.hide();
            }
        });

        // Close company dropdown on outside click
        $(document).on("mousedown.ai_company", (e) => {
            if (!$(e.target).closest(".ai-company-selector, .ai-company-dropdown").length) {
                this.$company_dropdown.hide();
            }
        });

        // Template cards — insert prompt and send
        this.$messages.on("click", ".ai-template-card", (e) => {
            const prompt = $(e.currentTarget).data("prompt");
            this.$input.val(prompt);
            this.send();
        });

        // ── Feature 16: File attachments ──────────────────────────────

        // Attach button clicks the hidden file input
        this.$panel.find(".ai-chat-attach").on("click", () => {
            this.$panel.find(".ai-chat-file-input").trigger("click");
        });

        // Hidden file input change handler
        this.$panel.find(".ai-chat-file-input").on("change", (e) => {
            const files = e.target.files;
            if (files && files.length) {
                this._upload_files(Array.from(files));
            }
            e.target.value = ""; // Reset so same file can be re-selected
        });

        // Drag & drop on the messages area
        this.$messages.on("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.$messages.addClass("ai-drag-over");
        });

        this.$messages.on("dragleave", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.$messages.removeClass("ai-drag-over");
        });

        this.$messages.on("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.$messages.removeClass("ai-drag-over");
            const files = e.originalEvent.dataTransfer.files;
            if (files && files.length) {
                this._upload_files(Array.from(files));
            }
        });

        // ── Feature 17: Voice input ────────────────────────────────────

        this.$panel.find(".ai-chat-voice").on("click", () => {
            this._toggle_voice_input();
        });

        // ── Reply bar close ──────────────────────────────────────────
        this.$reply_bar.find(".ai-reply-bar-close").on("click", () => {
            this._cancel_reply();
        });

        // ── Message context menu actions ─────────────────────────────
        this.$msg_ctx_menu.find(".ai-msg-ctx-reply").on("click", () => {
            const target = this._msg_ctx_target;
            this._hide_msg_ctx_menu();
            if (target) this._start_reply(target.index, target.role, target.text);
        });

        this.$msg_ctx_menu.find(".ai-msg-ctx-forward").on("click", () => {
            const target = this._msg_ctx_target;
            this._hide_msg_ctx_menu();
            if (target) this._show_forward_modal(target.index);
        });

        this.$msg_ctx_menu.find(".ai-msg-ctx-copy").on("click", () => {
            const target = this._msg_ctx_target;
            this._hide_msg_ctx_menu();
            if (target && target.text) {
                navigator.clipboard.writeText(target.text).then(() => {
                    frappe.show_alert({ message: __("Copied to clipboard"), indicator: "green" });
                });
            }
        });

        // Close message context menu on outside click
        $(document).on("mousedown.ai_msg_ctx", (e) => {
            if (!$(e.target).closest(".ai-msg-ctx-menu").length) {
                this._hide_msg_ctx_menu();
            }
        });

        // Forward modal events
        this.$forward_modal.find(".ai-forward-close").on("click", () => {
            this.$forward_modal.hide();
        });

        this.$forward_modal.find(".ai-forward-search").on("input", (e) => {
            this._filter_forward_users(e.target.value.trim().toLowerCase());
        });

        // ── DM mode toggle tabs ─────────────────────────────────────
        this.$panel.on("click", ".ai-mode-tab", (e) => {
            const mode = $(e.currentTarget).data("mode");
            this.$panel.find(".ai-mode-tab").removeClass("active");
            $(e.currentTarget).addClass("active");
            if (mode === "dm") {
                this._enter_dm_mode();
            } else {
                this._exit_dm_mode();
            }
        });

        // DM new chat button
        this.$panel.on("click", ".ai-dm-new-chat-btn", () => {
            this._show_dm_user_picker();
        });

        // DM user search
        this.$panel.on("input", ".ai-dm-user-search", (e) => {
            this._filter_dm_conversations(e.target.value.trim().toLowerCase());
        });

        // Listen for incoming DMs via Socket.IO
        frappe.realtime.on("ai_dm_new", (data) => {
            this._on_dm_received(data);
        });

        // Listen for AI responses in DMs
        frappe.realtime.on("ai_dm_ai_response", (data) => {
            this._on_ai_dm_response(data);
        });

        // Load unread DM count and AI name on init
        this._load_unread_dm_count();
        this._load_ai_name();
    }

    // ── Panel open/close ─────────────────────────────────────────────

    toggle() {
        this.is_open = !this.is_open;
        this.$panel.toggle(this.is_open);
        this.$btn.toggleClass("ai-chat-btn-active", this.is_open);
        if (this.is_open) {
            this.$input.focus();
            setTimeout(() => this._scroll_bottom(), 50);
        }
    }

    _scroll_top() {
        this.$messages.scrollTop(0);
    }

    _show_help() {
        const help_html = `
        <div class="ai-help-panel">
            <div class="ai-help-header">
                <h3>AI Oracle — Available Commands</h3>
                <button class="ai-help-close">&times;</button>
            </div>
            <div class="ai-help-content">
                <div class="ai-help-section">
                    <h4>Management Analytics (Manager roles only)</h4>
                    <div class="ai-help-cmd">"Show me today's sales dashboard"</div>
                    <div class="ai-help-cmd">"Rank all branches by sales this month"</div>
                    <div class="ai-help-cmd">"What is our gross profit margin this month?"</div>
                    <div class="ai-help-cmd">"Show margin by item group"</div>
                    <div class="ai-help-cmd">"Show me inventory days and slow movers"</div>
                    <div class="ai-help-cmd">"What is our stock turnover rate this quarter vs last quarter?"</div>
                    <div class="ai-help-cmd">"Email me a sales report with charts for this month"</div>
                    <div class="ai-help-cmd">"Email the branch performance report to admin@company.com"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Sales &amp; Customers</h4>
                    <div class="ai-help-cmd">"Create a customer John Smith, email john@email.com, phone 71234567"</div>
                    <div class="ai-help-cmd">"Look up customer Acme Corp"</div>
                    <div class="ai-help-cmd">"Create a quotation for Acme Corp: 10 units of Widget A"</div>
                    <div class="ai-help-cmd">"Show me today's sales summary"</div>
                    <div class="ai-help-cmd">"What are our top 10 customers?"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Purchasing &amp; Suppliers</h4>
                    <div class="ai-help-cmd">"Create a supplier ACME Corp, email acme@corp.com"</div>
                    <div class="ai-help-cmd">"Look up supplier Global Parts Ltd"</div>
                    <div class="ai-help-cmd">"Create a PO for Global Parts Ltd: 100x Widget A"</div>
                    <div class="ai-help-cmd">"Show me overdue purchase invoices"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Accounting &amp; Finance</h4>
                    <div class="ai-help-cmd">"Show me the trial balance"</div>
                    <div class="ai-help-cmd">"Record payment of 5000 from Acme Corp"</div>
                    <div class="ai-help-cmd">"Show me the P&amp;L for this quarter"</div>
                    <div class="ai-help-cmd">"What are our bank balances?"</div>
                    <div class="ai-help-cmd">"Show general ledger for Acme Corp"</div>
                    <div class="ai-help-cmd">"What is our gross margin by territory?"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Stock &amp; Inventory</h4>
                    <div class="ai-help-cmd">"Create item ABC-001, name Widget, rate 50"</div>
                    <div class="ai-help-cmd">"What is the stock level for Widget A?"</div>
                    <div class="ai-help-cmd">"Which items need reordering?"</div>
                    <div class="ai-help-cmd">"Transfer 5 units of Widget A between warehouses"</div>
                    <div class="ai-help-cmd">"Show stock turnover by warehouse"</div>
                    <div class="ai-help-cmd">"Which items are slow movers?"</div>
                </div>
                <div class="ai-help-section">
                    <h4>HR &amp; People</h4>
                    <div class="ai-help-cmd">"What is my leave balance?"</div>
                    <div class="ai-help-cmd">"Apply for 2 days leave from April 1"</div>
                    <div class="ai-help-cmd">"Show my salary slip"</div>
                </div>
                <div class="ai-help-section">
                    <h4>CRM</h4>
                    <div class="ai-help-cmd">"Create a lead: John, john@email.com, from website"</div>
                    <div class="ai-help-cmd">"List open opportunities"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Projects</h4>
                    <div class="ai-help-cmd">"List active projects"</div>
                    <div class="ai-help-cmd">"Create task: Review Q1 financials, high priority"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Support</h4>
                    <div class="ai-help-cmd">"Create ticket: POS not printing, priority High"</div>
                    <div class="ai-help-cmd">"List open support issues"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Assets</h4>
                    <div class="ai-help-cmd">"List all company assets"</div>
                    <div class="ai-help-cmd">"Show depreciation for asset ABC"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Saved Reports</h4>
                    <div class="ai-help-cmd">"Save a report called daily-sales: show today's sales by branch"</div>
                    <div class="ai-help-cmd">"Run the daily-sales report"</div>
                    <div class="ai-help-cmd">"List my saved reports"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Scheduling</h4>
                    <div class="ai-help-cmd">"Remind me to check overdue invoices in 15 minutes"</div>
                    <div class="ai-help-cmd">"Send me a sales summary every Monday at 8am"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Files &amp; Media</h4>
                    <div class="ai-help-cmd">[Upload CSV/Excel/PDF/Word] "Analyze this file"</div>
                    <div class="ai-help-cmd">[Upload image] "What is in this picture?"</div>
                    <div class="ai-help-cmd">"Email me the overdue invoices report"</div>
                </div>
                <div class="ai-help-section">
                    <h4>Data &amp; Charts</h4>
                    <div class="ai-help-cmd">"Show monthly sales as a line chart"</div>
                    <div class="ai-help-cmd">"Revenue by customer group as a pie chart"</div>
                    <div class="ai-help-cmd">[SQL] "Run: SELECT customer, SUM(grand_total)..."</div>
                </div>
            </div>
        </div>`;

        // Remove any existing help panel, then prepend the new one
        this.$messages.find(".ai-help-panel").remove();
        this.$messages.prepend(help_html);
        this._scroll_top();

        // Close button
        this.$messages.find(".ai-help-close").on("click", () => {
            this.$messages.find(".ai-help-panel").remove();
        });

        // Click a command to paste it into the input (strip surrounding quotes)
        this.$messages.on("click.ai_help", ".ai-help-cmd", (e) => {
            const raw = $(e.currentTarget).text().trim();
            // Skip file-upload placeholders that start with [
            if (raw.startsWith("[")) return;
            // Strip surrounding quotation marks added for readability
            const text = raw.replace(/^"/, "").replace(/"$/, "");
            this.$input.val(text);
            this.$input.focus();
            this.$messages.find(".ai-help-panel").remove();
            this.$messages.off("click.ai_help");
        });
    }

    toggle_expand() {
        this.is_expanded = !this.is_expanded;
        this.$panel.toggleClass("ai-chat-panel-expanded", this.is_expanded);
        this.$panel.find(".expand-icon").toggle(!this.is_expanded);
        this.$panel.find(".shrink-icon").toggle(this.is_expanded);
        // Show/hide sidebar toggle button
        this.$panel.find(".ai-chat-toggle-sidebar").toggle(this.is_expanded);

        if (this.is_expanded) {
            this.$sidebar.show();
            this.$panel.find(".ai-chat-sessions-bar").hide();
            this._load_sessions_list();
        } else {
            this.$sidebar.hide();
        }

        this._scroll_bottom();
    }

    _toggle_sidebar() {
        if (!this.is_expanded) return;
        const visible = this.$sidebar.is(":visible");
        this.$sidebar.toggle(!visible);
        this.$panel.toggleClass("ai-sidebar-hidden", visible);
    }

    // ── New session ──────────────────────────────────────────────────

    new_session() {
        this.session_id = null;
        this.$messages.empty();
        this._cleanup_stream();
        this._cancel_reply();
        this._message_index = 0;
        this._dm_mode = false;
        this._dm_user = null;
        this.$input.focus();
        // Update compact selector
        this.$panel.find(".ai-chat-session-select").val("");
        // Highlight no item in sidebar
        this.$session_list.find(".ai-session-item").removeClass("active");
        // Show quick-action templates for the fresh empty state
        this._show_templates();
    }

    // ── Message rendering ────────────────────────────────────────────

    add_message(role, content, opts) {
        opts = opts || {};
        const cls = role === "user" ? "ai-msg-user" : "ai-msg-bot";
        const idx = opts.index != null ? opts.index : this._message_index++;
        const $msg = $(`<div class="ai-msg ${cls}" data-msg-idx="${idx}"></div>`);

        // Reply quote bubble
        if (opts.reply_to_text) {
            const reply_label = opts.reply_to_role === "user" ? "You" : "AI Assistant";
            const $quote = $(`<div class="ai-reply-quote">
                <span class="ai-reply-quote-label">${frappe.utils.escape_html(reply_label)}</span>
                <span class="ai-reply-quote-text">${frappe.utils.escape_html(opts.reply_to_text.substring(0, 120))}</span>
            </div>`);
            $msg.append($quote);
        }

        if (role === "user") {
            $msg.append($('<span class="ai-msg-text"></span>').text(content));
        } else {
            $msg.append($(erpnext_ai_bots.render_markdown(content)));
        }

        // Right-click context menu for reply/forward (only on AI chat, not DM)
        if (!this._dm_mode) {
            $msg.on("contextmenu", (e) => {
                e.preventDefault();
                this._show_msg_ctx_menu(e.pageX, e.pageY, idx, role, content);
            });
        }

        this.$messages.append($msg);
        this._scroll_bottom();
        return $msg;
    }

    _scroll_bottom() {
        this.$messages.scrollTop(this.$messages[0].scrollHeight);
    }

    // ── Session persistence ──────────────────────────────────────────

    async _load_last_session() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.chat.get_sessions",
                args: { limit: 1, offset: 0 },
                async: true,
            });
            const sessions = r.message || [];
            if (sessions.length && sessions[0].status === "Active") {
                this.session_id = sessions[0].name;
                await this._load_session(this.session_id);
            }
        } catch (e) {
            // Silently fail — widget still works for new sessions
        }
    }

    async _load_session(session_id) {
        // Prevent concurrent load calls (race between init and user click)
        if (this._loading_session) return;
        this._loading_session = true;

        // If switching away from a streaming session, let the backend finish.
        // We just reset the UI state — the backend job saves to DB independently.
        if (this.is_streaming) {
            // Keep the old session ID to auto-refresh later
            const was_streaming_sid = this.session_id;
            this.is_streaming = false;
            this._cleanup_stream();
            this._remove_status_indicators();
            if (this._stream_timeout) {
                clearTimeout(this._stream_timeout);
                this._stream_timeout = null;
            }
            // Auto-refresh the old session after a delay (backend may still be processing)
            setTimeout(() => {
                if (this.is_expanded) this._load_sessions_list();
            }, 10000);
        }

        this._remove_status_indicators();

        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.chat.get_history",
                args: { session_id: session_id },
                async: true,
            });
            const data = r.message || {};
            this.session_id = session_id;
            this.$messages.empty();
            this._message_index = 0;
            this._dm_mode = false;
            this._dm_user = null;

            const messages = data.messages || [];
            const visible_messages = messages.filter(
                m => m.role !== "system" && (
                    typeof m.content === "string"
                        ? m.content
                        : (Array.isArray(m.content) && m.content.some(b => b.type === "text" && b.text))
                )
            );

            for (const msg of visible_messages) {
                let content = msg.content;
                if (Array.isArray(content)) {
                    const texts = content
                        .filter(b => b.type === "text" && b.text)
                        .map(b => b.text);
                    content = texts.join("\n");
                }
                if (content) {
                    this.add_message(msg.role, content);
                }
            }

            // Show templates only when the session has no visible messages
            if (visible_messages.length === 0) {
                this._show_templates();
            } else {
                this.$messages.find(".ai-templates-grid").hide();
            }

            // Highlight active item in sidebar
            this.$session_list.find(".ai-session-item").removeClass("active");
            this.$session_list
                .find(`.ai-session-item[data-sid="${session_id}"]`)
                .addClass("active");

            // Let the DOM finish rendering all message nodes before scrolling
            this._scroll_bottom();
            setTimeout(() => this._scroll_bottom(), 100);
        } catch (e) {
            // Silently fail
        } finally {
            this._loading_session = false;
        }
    }

    async _load_sessions_list() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.chat.get_sessions",
                args: { limit: 50, offset: 0 },
                async: true,
            });
            this._all_sessions = r.message || [];
            this._render_sidebar_sessions();
            // Also refresh compact select if it was open
            this._render_compact_select();
        } catch (e) {
            // Silently fail
        }
    }

    // ── Sidebar rendering ─────────────────────────────────────────────

    _set_category_tab(cat) {
        this._active_category = cat;
        this.$panel.find(".ai-cat-tab").removeClass("active");
        this.$panel.find(`.ai-cat-tab[data-cat="${cat}"]`).addClass("active");
        this._render_sidebar_sessions();
    }

    _render_sidebar_sessions() {
        let filtered = this._active_category === "All"
            ? this._all_sessions
            : this._all_sessions.filter(s =>
                (s.category || "General") === this._active_category
              );

        // Apply search query filter (instant, client-side)
        if (this._search_query) {
            filtered = filtered.filter(s =>
                (s.title || "").toLowerCase().includes(this._search_query)
            );
        }

        // Pinned sessions float to the top, order within each group preserved
        const sorted = [
            ...filtered.filter(s => s.pinned),
            ...filtered.filter(s => !s.pinned),
        ];

        this.$session_list.empty();

        if (!sorted.length) {
            this.$session_list.append(
                `<div class="ai-sidebar-empty">No conversations yet</div>`
            );
            return;
        }

        for (const s of sorted) {
            const title   = (s.title || s.name).substring(0, 40);
            const cat     = s.category || "General";
            const color   = erpnext_ai_bots.CATEGORY_COLORS[cat] || "gray";
            const count   = s.message_count || 0;
            const date    = s.last_message_at
                ? frappe.datetime.str_to_user(s.last_message_at.substring(0, 10))
                : frappe.datetime.str_to_user(s.creation.substring(0, 10));
            const is_active = s.name === this.session_id ? " active" : "";
            // Subtle pin icon shown only for pinned sessions
            const pin_icon  = s.pinned
                ? `<span class="ai-pin-icon" title="Pinned">
                       <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                           <path d="M16 1v6l2 4H6l2-4V1h8zM12 21v-6m-4-4h8"/>
                       </svg>
                   </span>`
                : "";

            const pin_btn_label = s.pinned ? "Unpin" : "Pin";
            const $item = $(`
                <div class="ai-session-item${is_active}" data-sid="${s.name}" title="${frappe.utils.escape_html(s.title || s.name)}">
                    <div class="ai-session-item-top">
                        <span class="ai-session-title">${pin_icon}${frappe.utils.escape_html(title)}</span>
                        <span class="ai-cat-badge ai-cat-${color}">${cat}</span>
                    </div>
                    <div class="ai-session-item-meta">
                        <span class="ai-session-date">${date}</span>
                        <span class="ai-session-count">${count} msg${count !== 1 ? "s" : ""}</span>
                    </div>
                    <div class="ai-session-actions">
                        <button class="ai-session-act-pin" title="${pin_btn_label}">${s.pinned ? "📌" : "📌"}</button>
                        <button class="ai-session-act-del" title="Delete">✕</button>
                    </div>
                </div>
            `);

            $item.find(".ai-session-act-pin").on("click", (e) => {
                e.stopPropagation();
                this._toggle_pin_session(s.name);
            });

            $item.find(".ai-session-act-del").on("click", (e) => {
                e.stopPropagation();
                this._delete_session(s.name);
            });

            $item.on("click", () => {
                this._load_session(s.name);
            });

            this.$session_list.append($item);
        }
    }

    _render_compact_select() {
        const $select = this.$panel.find(".ai-chat-session-select");
        $select.empty();
        $select.append('<option value="">-- Select a conversation --</option>');
        for (const s of this._all_sessions) {
            const label = (s.title || s.name).substring(0, 60);
            const selected = s.name === this.session_id ? " selected" : "";
            $select.append(
                `<option value="${s.name}"${selected}>${label} (${s.message_count || 0} msgs)</option>`
            );
        }
    }

    // ── Context menu ─────────────────────────────────────────────────

    _show_ctx_menu(x, y, session_id) {
        this._ctx_menu_target = session_id;
        // Update pin label to reflect current pinned state
        const session = this._all_sessions.find(s => s.name === session_id);
        const is_pinned = session && session.pinned;
        this.$ctx_menu.find(".ai-ctx-pin").text(is_pinned ? __("Unpin") : __("Pin"));
        // Keep menu within viewport
        const menu_w = 140;
        const menu_h = 96;
        const left = Math.min(x, window.innerWidth - menu_w - 8);
        const top  = Math.min(y, window.innerHeight - menu_h - 8);
        this.$ctx_menu.css({ left: left, top: top }).show();
    }

    _hide_ctx_menu() {
        this.$ctx_menu.hide();
        this._ctx_menu_target = null;
    }

    // ── Session CRUD ──────────────────────────────────────────────────

    async _rename_session(session_id, new_title) {
        try {
            await frappe.call({
                method: "erpnext_ai_bots.api.chat.rename_session",
                args: { session_id: session_id, title: new_title },
                async: true,
            });
            // Update local cache and re-render
            const s = this._all_sessions.find(x => x.name === session_id);
            if (s) s.title = new_title;
            this._render_sidebar_sessions();
            frappe.show_alert({ message: __("Conversation renamed"), indicator: "green" });
        } catch (e) {
            frappe.show_alert({ message: __("Could not rename conversation"), indicator: "red" });
        }
    }

    async _toggle_pin_session(session_id) {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.chat.toggle_pin",
                args: { session_id: session_id },
                async: true,
            });
            // Update local cache
            const s = this._all_sessions.find(x => x.name === session_id);
            if (s) s.pinned = r.message && r.message.pinned ? 1 : 0;
            this._render_sidebar_sessions();
            const label = s && s.pinned ? __("Conversation pinned") : __("Conversation unpinned");
            frappe.show_alert({ message: label, indicator: "green" });
        } catch (e) {
            frappe.show_alert({ message: __("Could not update pin"), indicator: "red" });
        }
    }

    async _delete_session(session_id) {
        try {
            await frappe.call({
                method: "erpnext_ai_bots.api.chat.delete_session",
                args: { session_id: session_id },
                async: true,
            });
            // Remove from cache
            this._all_sessions = this._all_sessions.filter(s => s.name !== session_id);
            this._render_sidebar_sessions();
            // If we deleted the active session, start fresh
            if (this.session_id === session_id) {
                this.new_session();
            }
            frappe.show_alert({ message: __("Conversation deleted"), indicator: "green" });
        } catch (e) {
            frappe.show_alert({ message: __("Could not delete conversation"), indicator: "red" });
        }
    }

    // ── Send message ─────────────────────────────────────────────────

    async send(retry_message) {
        const message = retry_message || this.$input.val().trim();
        if (!message) return;

        // Route to DM send if in DM mode
        if (this._dm_mode && this._dm_user) {
            this._send_dm(message);
            return;
        }

        // Build the actual message sent to the AI, prepending file context if available
        let actual_message = message;
        if (!retry_message && this._pending_attachment) {
            actual_message = `[File attached: ${this._pending_attachment.file_name} (${this._pending_attachment.file_type}), URL: ${this._pending_attachment.file_url}]\n\n${message}`;
            this._pending_attachment = null;
        }

        if (!retry_message) {
            this.$input.val("").trigger("input");
            // Include reply context if replying
            const reply_opts = this._reply_to ? {
                reply_to_text: this._reply_to.text,
                reply_to_role: this._reply_to.role,
            } : {};
            this.add_message("user", message, reply_opts);
            this._cancel_reply();
            // Hide templates on first real send
            this.$messages.find(".ai-templates-grid").hide();
        }
        this.is_streaming = true;
        this._last_message = actual_message;
        // Don't disable send — let user queue messages

        // Remove any leftover status indicators and show THINKING state
        this._remove_status_indicators();
        this.current_message_text = "";
        this._show_thinking();
        // The real bot message bubble will be created when first text chunk arrives
        this.$current_message = null;

        try {
            const args = {
                message: actual_message,
                session_id: this.session_id,
                company: this._current_company || null,
            };
            if (this._pending_image_url) {
                // Convert relative URL to absolute so the Codex API can fetch it
                args.image_url = window.location.origin + this._pending_image_url;
                this._pending_image_url = null;
            }

            const result = await frappe.call({
                method: "erpnext_ai_bots.api.chat.send_message",
                args,
                async: true,
            });

            // Handle missing OpenAI token
            if (result.message.status === "no_token") {
                this._finish_streaming();
                if (this.$current_message) this.$current_message.remove();
                this._show_connect_flow(message);
                return;
            }

            const is_new_session = !this.session_id;
            this.session_id = result.message.session_id;
            this._setup_stream();

            // After first message, refresh the sidebar/select in background
            if (is_new_session && this.is_expanded) {
                this._load_sessions_list();
            }

            // Safety timeout: 2 min
            this._stream_timeout = setTimeout(() => {
                if (this.is_streaming) {
                    this._finish_streaming();
                    if (!this.current_message_text) {
                        this._show_error("No response received — the server may be busy");
                    }
                }
            }, 120000);
        } catch (err) {
            console.error("AI Chat send_message error:", err);
            this._finish_streaming();
            this._show_error("Something went wrong — please try again");
        }
    }

    // ── OAuth connect flow ───────────────────────────────────────────

    _show_connect_flow(pending_message) {
        this.$messages.find(".ai-connect-flow").remove();

        const $flow = $(`
            <div class="ai-connect-flow">
                <div class="ai-connect-prompt">
                    <p><strong>Connect your ChatGPT account</strong></p>
                    <p class="text-muted">To use the AI Assistant, you need to connect your ChatGPT Plus, Pro, or Max account.</p>
                    <button class="btn btn-sm btn-primary ai-connect-start-btn">Connect ChatGPT Account</button>
                </div>
                <div class="ai-connect-paste" style="display:none;">
                    <p class="text-muted" style="font-size:12px;">
                        After signing in, you will be redirected to a page that <strong>won't load</strong>.
                        Copy the <strong>full URL</strong> from your browser's address bar and paste it below.
                    </p>
                    <input type="text" class="form-control ai-connect-url-input"
                           placeholder="Paste the callback URL here..." />
                    <div style="margin-top:8px; display:flex; gap:8px;">
                        <button class="btn btn-sm btn-primary ai-connect-complete-btn">Complete</button>
                        <button class="btn btn-sm btn-default ai-connect-cancel-btn">Cancel</button>
                    </div>
                </div>
            </div>
        `);

        this.$messages.append($flow);
        this._scroll_bottom();

        $flow.find(".ai-connect-start-btn").on("click", () => {
            frappe.call({
                method: "erpnext_ai_bots.api.openai_oauth.start_oauth",
                async: true,
                callback: (r) => {
                    const data = r.message || {};
                    if (data.auth_url) {
                        window.open(data.auth_url, "_blank");
                        $flow.find(".ai-connect-prompt").hide();
                        $flow.find(".ai-connect-paste").show();
                        $flow.find(".ai-connect-url-input").focus();
                    } else {
                        frappe.show_alert({ message: __("Failed to start OAuth flow"), indicator: "red" });
                    }
                },
                error: () => {
                    frappe.show_alert({ message: __("Failed to start OAuth flow"), indicator: "red" });
                },
            });
        });

        $flow.find(".ai-connect-complete-btn").on("click", () => {
            const pasted = $flow.find(".ai-connect-url-input").val().trim();
            if (!pasted) {
                frappe.show_alert({ message: __("Please paste the callback URL"), indicator: "orange" });
                return;
            }
            let code, state;
            try {
                const url = new URL(pasted);
                code  = url.searchParams.get("code");
                state = url.searchParams.get("state");
            } catch (e) {
                frappe.show_alert({ message: __("Invalid URL"), indicator: "red" });
                return;
            }
            if (!code) {
                frappe.show_alert({ message: __("No authorization code found in URL"), indicator: "red" });
                return;
            }

            $flow.find(".ai-connect-complete-btn").prop("disabled", true).text("Connecting...");

            frappe.call({
                method: "erpnext_ai_bots.api.openai_oauth.exchange_code",
                args: { code: code, state: state || "" },
                async: true,
                callback: (r) => {
                    const data = r.message || {};
                    if (data.success) {
                        frappe.show_alert({ message: __("ChatGPT account connected!"), indicator: "green" });
                        $flow.remove();
                        if (pending_message) {
                            this.send(pending_message);
                        }
                    } else {
                        frappe.show_alert({ message: __("Connection failed. Please try again."), indicator: "red" });
                        $flow.find(".ai-connect-complete-btn").prop("disabled", false).text("Complete");
                    }
                },
                error: () => {
                    frappe.show_alert({ message: __("Connection failed. Try starting the flow again."), indicator: "red" });
                    $flow.find(".ai-connect-complete-btn").prop("disabled", false).text("Complete");
                },
            });
        });

        $flow.find(".ai-connect-cancel-btn").on("click", () => {
            $flow.remove();
        });
    }

    // ── Streaming ────────────────────────────────────────────────────

    _setup_stream() {
        this._cleanup_stream();

        this.stream_handler = new erpnext_ai_bots.stream.StreamHandler(
            this.session_id,
            {
                onChunk: (text) => {
                    // Create bot bubble on first chunk if it doesn't exist yet
                    if (!this.$current_message) {
                        // Remove thinking indicator — response has started
                        this._remove_status_indicators();
                        this.$current_message = this.add_message("assistant", "");
                    }
                    this.current_message_text += text;
                    this.$current_message.html(
                        erpnext_ai_bots.render_markdown(this.current_message_text)
                    );
                    this._scroll_bottom();
                },
                onToolStart: (tool) => {
                    // Update status text to show which tool is running
                    this._update_status_text(tool);
                },
                onToolResult: () => {
                    // no-op
                },
                onDone: () => {
                    this._finish_streaming();
                    // Add delivered tick and optional TTS button to the bot message
                    if (this.$current_message) {
                        this._add_delivered_tick(this.$current_message);
                        this._add_tts_button(this.$current_message);
                    }
                    // Refresh sidebar after response so message counts update
                    if (this.is_expanded) {
                        this._load_sessions_list();
                    }
                },
                onError: (error) => {
                    this._finish_streaming();
                    this._show_error(error || "Something went wrong — please try again");
                },
            }
        );
    }

    _finish_streaming() {
        this.is_streaming = false;
        // Remove any status indicators still showing
        this._remove_status_indicators();
        // Cancel any pending tool-hide delay and hide tool indicator bar
        clearTimeout(this._tool_hide_timeout);
        this._tool_hide_timeout = null;
        this.$tool_indicator.hide();
        if (this._stream_timeout) {
            clearTimeout(this._stream_timeout);
            this._stream_timeout = null;
        }
        if (this.$current_message) {
            // Apply data-result class if the message contains a table
            if (this.$current_message.find("table").length) {
                this.$current_message.addClass("ai-msg-data");
            }
        }
        this._cleanup_stream();
    }

    // ── Status indicators ─────────────────────────────────────────────

    /** Show the animated 3-dot THINKING indicator below the user's message. */
    _show_thinking() {
        this.$status_indicator = $(`
            <div class="ai-status-indicator ai-status-thinking">
                <div class="ai-bounce-loader">
                    <span></span><span></span><span></span>
                </div>
                <span class="ai-status-text">Processing...</span>
            </div>
        `);
        this.$messages.append(this.$status_indicator);
        this._scroll_bottom();
    }

    /** Update the status text while a tool is running. */
    _update_status_text(tool_name) {
        if (this.$status_indicator && this.$status_indicator.hasClass("ai-status-thinking")) {
            this.$status_indicator.find(".ai-status-text").text(tool_name + "...");
            this._scroll_bottom();
        }
    }

    /** Remove all status indicators (thinking + error) from the message list. */
    _remove_status_indicators() {
        this.$messages.find(".ai-status-indicator").remove();
        this.$status_indicator = null;
    }

    /**
     * Show the ERROR indicator with a Retry button.
     * @param {string} msg - User-friendly error message (no technical jargon).
     */
    _show_error(msg) {
        // Remove any thinking indicator first
        this._remove_status_indicators();

        this.$status_indicator = $(`
            <div class="ai-status-indicator ai-status-error">
                <span class="ai-error-icon">!</span>
                <span class="ai-status-text">${frappe.utils.escape_html(msg)}</span>
                <button class="ai-retry-btn">Retry</button>
            </div>
        `);

        this.$status_indicator.find(".ai-retry-btn").on("click", () => {
            this._remove_status_indicators();
            if (this._last_message) {
                this.send(this._last_message);
            }
        });

        this.$messages.append(this.$status_indicator);
        this._scroll_bottom();
    }

    /** Show or re-show the quick-action templates grid in the messages area. */
    _show_templates() {
        // If the grid already exists in the DOM just make it visible
        const $existing = this.$messages.find(".ai-templates-grid");
        if ($existing.length) {
            $existing.show();
            return;
        }
        // Otherwise inject a fresh grid (e.g. after $messages.empty())
        const $grid = $(`
            <div class="ai-templates-grid">
                <div class="ai-template-card" data-prompt="Show me today's sales dashboard">
                    <span class="ai-template-icon">📊</span>
                    <span class="ai-template-text">Sales Dashboard</span>
                </div>
                <div class="ai-template-card" data-prompt="Rank all branches by sales this month with profit margins">
                    <span class="ai-template-icon">🏢</span>
                    <span class="ai-template-text">Branch Ranking</span>
                </div>
                <div class="ai-template-card" data-prompt="What is our gross profit margin this month by item group?">
                    <span class="ai-template-icon">💰</span>
                    <span class="ai-template-text">Gross Margin</span>
                </div>
                <div class="ai-template-card" data-prompt="Show me inventory days and slow movers">
                    <span class="ai-template-icon">📦</span>
                    <span class="ai-template-text">Inventory Health</span>
                </div>
                <div class="ai-template-card" data-prompt="What is our stock turnover rate this month vs last month?">
                    <span class="ai-template-icon">🔄</span>
                    <span class="ai-template-text">Stock Turnover</span>
                </div>
                <div class="ai-template-card" data-prompt="List all overdue invoices">
                    <span class="ai-template-icon">⚠️</span>
                    <span class="ai-template-text">Overdue Invoices</span>
                </div>
                <div class="ai-template-card" data-prompt="Email me a sales report for this month with charts">
                    <span class="ai-template-icon">📧</span>
                    <span class="ai-template-text">Email Report</span>
                </div>
                <div class="ai-template-card" data-prompt="What is our bank balance across all accounts?">
                    <span class="ai-template-icon">🏦</span>
                    <span class="ai-template-text">Bank Balances</span>
                </div>
            </div>
        `);
        this.$messages.prepend($grid);
    }

    /**
     * Append a green delivered tick to the given bot message element.
     * @param {jQuery} $msg
     */
    _add_delivered_tick($msg) {
        $msg.append('<span class="ai-delivered-tick" title="Delivered">&#10003;</span>');
    }

    // ── Feature 17: TTS button ────────────────────────────────────────

    /**
     * Append a speaker button to a bot message bubble.
     * Only shown when an ElevenLabs API key is configured.
     * @param {jQuery} $msg
     */
    _add_tts_button($msg) {
        if (!this._elevenlabs_key) return;
        const $btn = $('<button class="ai-tts-btn" title="Listen">&#128266;</button>');
        $msg.append($btn);
        $btn.on("click", async (e) => {
            e.stopPropagation();
            // Extract plain text — strip HTML tags
            const text = $msg.clone().find(".ai-delivered-tick, .ai-tts-btn").remove().end().text().trim();
            if (!text) return;
            $btn.text("⏳");
            try {
                const resp = await fetch(
                    "https://api.elevenlabs.io/v1/text-to-speech/" + this._elevenlabs_voice_id,
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "xi-api-key": this._elevenlabs_key,
                        },
                        body: JSON.stringify({
                            text: text.substring(0, 5000),
                            model_id: "eleven_multilingual_v2",
                        }),
                    }
                );
                if (!resp.ok) {
                    throw new Error("TTS API error: " + resp.status);
                }
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const audio = new Audio(url);
                audio.play();
                $btn.html("&#128266;");
                audio.onended = () => URL.revokeObjectURL(url);
            } catch (err) {
                $btn.html("&#128266;");
                frappe.show_alert({ message: __("Text-to-speech failed"), indicator: "red" });
            }
        });
    }

    /**
     * Load ElevenLabs TTS configuration from AI Bot Settings.
     * Silently does nothing if the key is not set.
     */
    async _load_elevenlabs_config() {
        try {
            const r = await frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "AI Bot Settings",
                    fieldname: ["elevenlabs_api_key", "elevenlabs_voice_id"],
                },
                async: true,
            });
            if (r.message) {
                this._elevenlabs_key = r.message.elevenlabs_api_key || "";
                this._elevenlabs_voice_id = r.message.elevenlabs_voice_id || "21m00Tcm4TlvDq8ikWAM";
            }
        } catch (e) {
            // Silently fall back — TTS is optional
        }
    }

    // ── Feature 16: File upload ───────────────────────────────────────

    /**
     * Upload an array of File objects one by one, showing a preview bubble
     * for each. The last successfully uploaded file is stored as
     * this._pending_attachment so it gets prepended to the next sent message.
     * @param {File[]} files
     */
    async _upload_files(files) {
        for (const file of files) {
            const $preview = this._create_file_preview(file);
            this.$messages.append($preview);
            this._scroll_bottom();

            try {
                const formData = new FormData();
                formData.append("file", file);
                formData.append("session_id", this.session_id || "");

                const response = await fetch(
                    "/api/method/erpnext_ai_bots.api.chat.upload_file",
                    {
                        method: "POST",
                        body: formData,
                        headers: {
                            "X-Frappe-CSRF-Token": frappe.csrf_token,
                        },
                    }
                );
                const data = await response.json();

                if (data.message) {
                    this._pending_attachment = data.message;
                    $preview.find(".ai-file-status").text("Attached").addClass("ai-file-success");

                    // Store image URL for vision and show an inline thumbnail
                    if (data.message.file_type && data.message.file_type.startsWith("image/")) {
                        this._pending_image_url = data.message.file_url;
                        const reader = new FileReader();
                        reader.onload = (e) => {
                            const $img = $(`<div class="ai-msg ai-msg-user ai-img-preview">
                                <img src="${e.target.result}" alt="${frappe.utils.escape_html(file.name)}" />
                            </div>`);
                            this.$messages.append($img);
                            this._scroll_bottom();
                        };
                        reader.readAsDataURL(file);
                    }

                    // Pre-fill the input so the user knows a file is queued
                    const current = this.$input.val();
                    if (!current.startsWith("[Attached:")) {
                        this.$input.val(`[Attached: ${data.message.file_name}] `);
                    }
                    this.$input.focus();
                } else {
                    $preview.find(".ai-file-status").text("Failed").addClass("ai-file-error");
                }
            } catch (err) {
                $preview.find(".ai-file-status").text("Failed").addClass("ai-file-error");
            }
        }
    }

    /**
     * Build a file-preview bubble shown inline while uploading.
     * @param {File} file
     * @returns {jQuery}
     */
    _create_file_preview(file) {
        let icon;
        if (file.type.startsWith("image/")) {
            icon = "&#128444;"; // 🖼
        } else if (file.type.includes("pdf")) {
            icon = "&#128196;"; // 📄
        } else if (file.type.includes("csv") || file.type.includes("excel") || file.type.includes("spreadsheet")) {
            icon = "&#128202;"; // 📊
        } else {
            icon = "&#128206;"; // 📎
        }
        const size = (file.size / 1024).toFixed(1) + " KB";
        return $(`
            <div class="ai-msg ai-msg-user ai-file-preview">
                <span class="ai-file-icon">${icon}</span>
                <div class="ai-file-info">
                    <span class="ai-file-name">${frappe.utils.escape_html(file.name)}</span>
                    <span class="ai-file-size">${size}</span>
                </div>
                <span class="ai-file-status">Uploading...</span>
            </div>
        `);
    }

    // ── Long-paste to file conversion ────────────────────────────────

    /**
     * Convert a long pasted text block into a .txt file attachment,
     * mirroring the UX of Claude and ChatGPT.
     * @param {string} text  The full pasted text (already in the textarea)
     */
    _convert_paste_to_file(text) {
        const blob = new Blob([text], { type: "text/plain" });
        const file = new File([blob], "pasted_content.txt", { type: "text/plain" });

        // Clear the textarea immediately
        this.$input.val("").trigger("input");

        // Upload as a regular file attachment
        this._upload_files([file]);

        // After the upload starts, pre-fill a prompt referencing the content
        setTimeout(() => {
            const preview = text.substring(0, 100).replace(/\n/g, " ");
            this.$input.val(`Analyze the pasted content: "${preview}..."`);
            this.$input.focus();
        }, 500);

        frappe.show_alert({
            message: __("Long text converted to file attachment"),
            indicator: "blue",
        });
    }

    // ── Feature 17: Voice input ───────────────────────────────────────

    /**
     * Toggle the Web Speech API microphone recording. Starts recording on the
     * first call and stops on the second. Automatically sends the transcript
     * when recording ends if the input has text.
     */
    _toggle_voice_input() {
        if (this._is_recording) {
            this._stop_voice();
            return;
        }

        if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
            frappe.show_alert({
                message: __("Voice input not supported in this browser. Use Chrome or Edge."),
                indicator: "orange",
            });
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this._recognition = new SpeechRecognition();
        this._recognition.continuous = false;
        this._recognition.interimResults = true;
        this._recognition.lang = "en-US";

        this._recognition.onstart = () => {
            this._is_recording = true;
            this.$panel.find(".ai-chat-voice").addClass("ai-voice-active");
            this.$input.attr("placeholder", "Listening...");
        };

        this._recognition.onresult = (event) => {
            let transcript = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
                transcript += event.results[i][0].transcript;
            }
            this.$input.val(transcript).trigger("input");
        };

        this._recognition.onend = () => {
            this._is_recording = false;
            this.$panel.find(".ai-chat-voice").removeClass("ai-voice-active");
            this.$input.attr("placeholder", "Ask about your ERPNext data...");
            // Auto-send if the input has text
            const text = this.$input.val().trim();
            if (text) {
                this.send();
            }
        };

        this._recognition.onerror = (event) => {
            this._is_recording = false;
            this.$panel.find(".ai-chat-voice").removeClass("ai-voice-active");
            this.$input.attr("placeholder", "Ask about your ERPNext data...");
            if (event.error !== "no-speech") {
                frappe.show_alert({
                    message: __("Voice error: " + event.error),
                    indicator: "red",
                });
            }
        };

        this._recognition.start();
    }

    /** Stop an in-progress voice recording. */
    _stop_voice() {
        if (this._recognition) {
            this._recognition.stop();
        }
        this._is_recording = false;
        this.$panel.find(".ai-chat-voice").removeClass("ai-voice-active");
        this.$input.attr("placeholder", "Ask about your ERPNext data...");
    }

    _cleanup_stream() {
        if (this.stream_handler) {
            this.stream_handler.destroy();
            this.stream_handler = null;
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // REPLY FEATURE
    // ═══════════════════════════════════════════════════════════════════

    _show_msg_ctx_menu(x, y, index, role, text) {
        this._msg_ctx_target = { index, role, text };
        const menu_w = 140;
        const menu_h = 100;
        const left = Math.min(x, window.innerWidth - menu_w - 8);
        const top  = Math.min(y, window.innerHeight - menu_h - 8);
        this.$msg_ctx_menu.css({ left, top }).show();
    }

    _hide_msg_ctx_menu() {
        this.$msg_ctx_menu.hide();
        this._msg_ctx_target = null;
    }

    _start_reply(index, role, text) {
        this._reply_to = { index, role, text };
        const label = role === "user" ? "You" : "AI Assistant";
        this.$reply_bar.find(".ai-reply-bar-label").text("Replying to " + label);
        this.$reply_bar.find(".ai-reply-bar-text").text(text.substring(0, 80) + (text.length > 80 ? "..." : ""));
        this.$reply_bar.show();
        this.$input.focus();
    }

    _cancel_reply() {
        this._reply_to = null;
        this.$reply_bar.hide();
    }

    // ═══════════════════════════════════════════════════════════════════
    // FORWARD FEATURE
    // ═══════════════════════════════════════════════════════════════════

    async _show_forward_modal(message_index) {
        this._forward_target_index = message_index;
        this._user_picker_mode = "forward";  // "forward" or "dm"
        this.$forward_modal.show();
        this.$forward_modal.find(".ai-forward-header span").text("Forward to...");
        this.$forward_modal.find(".ai-forward-note-wrap").show();
        this.$forward_modal.find(".ai-forward-search").val("").focus();
        this.$forward_modal.find(".ai-forward-note").val("");
        this._load_user_picker_list();
    }

    async _load_user_picker_list() {
        this.$forward_modal.find(".ai-forward-user-list").html(
            '<div class="ai-forward-loading">Loading users...</div>'
        );
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.messaging.get_company_users",
                args: { company: this._current_company || "" },
                async: true,
            });
            this._forward_users = r.message || [];
            this._render_user_picker(this._forward_users);
        } catch (e) {
            this.$forward_modal.find(".ai-forward-user-list").html(
                '<div class="ai-forward-loading">Could not load users</div>'
            );
        }
    }

    _render_user_picker(users) {
        const $list = this.$forward_modal.find(".ai-forward-user-list");
        $list.empty();
        if (!users.length) {
            $list.html('<div class="ai-forward-loading">No users found</div>');
            return;
        }
        const mode = this._user_picker_mode;
        for (const u of users) {
            const avatar = u.user_image
                ? `<img src="${u.user_image}" class="ai-forward-avatar" />`
                : `<span class="ai-forward-avatar-placeholder">${(u.full_name || u.name).charAt(0).toUpperCase()}</span>`;
            const online_dot = u.is_online
                ? '<span class="ai-online-dot" title="Online"></span>'
                : '<span class="ai-offline-dot" title="Offline"></span>';
            const $item = $(`
                <div class="ai-forward-user-item" data-user="${frappe.utils.escape_html(u.name)}">
                    <div class="ai-user-avatar-wrap">
                        ${avatar}
                        ${online_dot}
                    </div>
                    <div class="ai-forward-user-info">
                        <span class="ai-forward-user-name">${frappe.utils.escape_html(u.full_name || u.name)}</span>
                        <span class="ai-forward-user-email">${frappe.utils.escape_html(u.name)}</span>
                    </div>
                </div>
            `);
            if (mode === "forward") {
                $item.on("click", () => this._do_forward(u.name, u.full_name || u.name));
            } else {
                $item.on("click", () => {
                    this.$forward_modal.hide();
                    this._open_dm_conversation(u.name, u.full_name || u.name);
                });
            }
            $list.append($item);
        }
    }

    _filter_forward_users(query) {
        if (!this._forward_users) return;
        const filtered = query
            ? this._forward_users.filter(u =>
                (u.full_name || "").toLowerCase().includes(query) ||
                u.name.toLowerCase().includes(query)
            )
            : this._forward_users;
        this._render_user_picker(filtered);
    }

    async _do_forward(to_user, to_name) {
        const note = this.$forward_modal.find(".ai-forward-note").val().trim();
        this.$forward_modal.hide();

        if (this._forward_target_index == null) {
            frappe.show_alert({ message: __("No message selected to forward"), indicator: "orange" });
            return;
        }

        try {
            await frappe.call({
                method: "erpnext_ai_bots.api.messaging.forward_message",
                args: {
                    session_id: this.session_id,
                    message_index: this._forward_target_index,
                    to_user: to_user,
                    note: note,
                },
                async: true,
            });
            frappe.show_alert({
                message: __("Message forwarded to {0}", [to_name]),
                indicator: "green",
            });
        } catch (e) {
            frappe.show_alert({
                message: __("Could not forward message"),
                indicator: "red",
            });
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // DIRECT MESSAGE (DM) FEATURE
    // ═══════════════════════════════════════════════════════════════════

    _show_mention_popup() {
        const ai_name = this._ai_name || "AI Oracle";
        const $popup = this.$mention_popup;
        $popup.empty();

        const $item = $(`
            <div class="ai-mention-item">
                <span class="ai-mention-avatar">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2">
                        <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"/>
                        <path d="M12 8v4l3 3"/>
                    </svg>
                </span>
                <div class="ai-mention-info">
                    <span class="ai-mention-name">${frappe.utils.escape_html(ai_name)}</span>
                    <span class="ai-mention-hint">Ask ${frappe.utils.escape_html(ai_name)} a question</span>
                </div>
            </div>
        `);

        $item.on("click", () => {
            // Replace the @partial with @<ai_name>
            const val = this.$input.val();
            const newVal = val.replace(/(^|\s)@\w*$/, "$1@" + ai_name + " ");
            this.$input.val(newVal).focus();
            this._hide_mention_popup();
        });

        $popup.append($item);

        // Position above the input
        const input_rect = this.$input[0].getBoundingClientRect();
        $popup.css({
            left: input_rect.left,
            bottom: window.innerHeight - input_rect.top + 4,
            width: Math.min(input_rect.width, 250),
        }).show();

        // Close on outside click
        setTimeout(() => {
            $(document).one("mousedown.ai_mention", (e) => {
                if (!$(e.target).closest(".ai-mention-popup").length) {
                    this._hide_mention_popup();
                }
            });
        }, 50);
    }

    _hide_mention_popup() {
        this.$mention_popup.hide();
        $(document).off("mousedown.ai_mention");
    }

    async _load_ai_name() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.messaging.get_ai_name",
                async: true,
            });
            this._ai_name = (r.message && r.message.ai_name) || "AI Oracle";
        } catch (e) {
            this._ai_name = "AI Oracle";
        }
    }

    _on_ai_dm_response(data) {
        // If we're viewing this DM conversation, show the AI response
        const other = data.from_user === frappe.session.user ? data.to_user : data.from_user;
        if (this._dm_mode && this._dm_user === other) {
            this._remove_status_indicators();
            this._append_dm_bubble("received", `**${data.ai_name}:**\n${data.message}`, data.ai_name);
        }
        // Refresh DM list
        if (this._dm_mode && this.is_expanded) {
            this._load_dm_conversations();
        }
    }

    async _load_unread_dm_count() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.messaging.get_unread_dm_count",
                async: true,
            });
            this._dm_unread_count = (r.message && r.message.count) || 0;
            this._update_dm_badge();
        } catch (e) {
            // Silently fail
        }
    }

    _update_dm_badge() {
        const $badge = this.$panel.find(".ai-dm-badge");
        if (this._dm_unread_count > 0) {
            $badge.text(this._dm_unread_count).show();
        } else {
            $badge.hide();
        }
    }

    _on_dm_received(data) {
        this._dm_unread_count++;
        this._update_dm_badge();

        // If we're viewing DMs with this sender, append the message live
        if (this._dm_mode && this._dm_user === data.from_user) {
            this._append_dm_bubble("received", data.message, data.from_name);
            // Auto-mark as read
            frappe.call({
                method: "erpnext_ai_bots.api.messaging.mark_dm_read",
                args: { other_user: data.from_user },
                async: true,
            });
        } else {
            // Show a toast notification
            frappe.show_alert({
                message: `<strong>${frappe.utils.escape_html(data.from_name)}</strong>: ${frappe.utils.escape_html(data.message.substring(0, 60))}`,
                indicator: "blue",
            });
        }

        // Refresh DM conversation list if sidebar is showing DMs
        if (this._dm_mode && this.is_expanded) {
            this._load_dm_conversations();
        }
    }

    _enter_dm_mode() {
        this._dm_mode = true;
        this.$ai_section.hide();
        this.$dm_section.show();
        this._load_dm_conversations();
        // Update header title
        this.$panel.find(".ai-chat-title").text("Direct Messages");
    }

    _exit_dm_mode() {
        this._dm_mode = false;
        this._dm_user = null;
        this.$dm_section.hide();
        this.$ai_section.show();
        this.$panel.find(".ai-chat-title").text("AI Assistant");
        // If we were viewing a DM conversation, reload the AI session
        if (this.session_id) {
            this._load_session(this.session_id);
        } else {
            this.$messages.empty();
            this._show_templates();
        }
    }

    async _load_dm_conversations() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.messaging.get_dm_conversations",
                args: { company: this._current_company || "" },
                async: true,
            });
            this._dm_conversations = r.message || [];
            this._render_dm_conversations(this._dm_conversations);
        } catch (e) {
            this.$dm_conv_list.html('<div class="ai-sidebar-empty">Could not load conversations</div>');
        }
    }

    _render_dm_conversations(conversations) {
        this.$dm_conv_list.empty();
        if (!conversations.length) {
            this.$dm_conv_list.html('<div class="ai-sidebar-empty">No conversations yet</div>');
            return;
        }
        for (const conv of conversations) {
            const avatar = conv.user_image
                ? `<img src="${conv.user_image}" class="ai-dm-avatar" />`
                : `<span class="ai-dm-avatar-placeholder">${(conv.full_name || conv.user).charAt(0).toUpperCase()}</span>`;
            const online_dot = conv.is_online
                ? '<span class="ai-online-dot" title="Online"></span>'
                : '<span class="ai-offline-dot" title="Offline"></span>';
            const unread = conv.unread_count > 0
                ? `<span class="ai-dm-unread">${conv.unread_count}</span>`
                : "";
            const preview = conv.is_from_me ? `You: ${conv.last_message}` : conv.last_message;
            const is_active = conv.user === this._dm_user ? " active" : "";

            const $item = $(`
                <div class="ai-dm-conv-item${is_active}" data-user="${frappe.utils.escape_html(conv.user)}">
                    <div class="ai-user-avatar-wrap">
                        ${avatar}
                        ${online_dot}
                    </div>
                    <div class="ai-dm-conv-info">
                        <div class="ai-dm-conv-top">
                            <span class="ai-dm-conv-name">${frappe.utils.escape_html(conv.full_name || conv.user)}</span>
                            ${unread}
                        </div>
                        <span class="ai-dm-conv-preview">${frappe.utils.escape_html(preview.substring(0, 40))}</span>
                    </div>
                </div>
            `);
            $item.on("click", () => this._open_dm_conversation(conv.user, conv.full_name || conv.user));
            this.$dm_conv_list.append($item);
        }
    }

    _filter_dm_conversations(query) {
        if (!this._dm_conversations) return;
        const filtered = query
            ? this._dm_conversations.filter(c =>
                (c.full_name || "").toLowerCase().includes(query) ||
                c.user.toLowerCase().includes(query)
            )
            : this._dm_conversations;
        this._render_dm_conversations(filtered);
    }

    async _open_dm_conversation(other_user, other_name) {
        this._dm_user = other_user;
        this._dm_mode = true;
        this.$messages.empty();
        this.$panel.find(".ai-chat-title").text(other_name);

        // Highlight active conversation in sidebar
        this.$dm_conv_list.find(".ai-dm-conv-item").removeClass("active");
        this.$dm_conv_list.find(`.ai-dm-conv-item[data-user="${other_user}"]`).addClass("active");

        // Mark messages as read
        frappe.call({
            method: "erpnext_ai_bots.api.messaging.mark_dm_read",
            args: { other_user },
            async: true,
        });

        // Load message history
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.messaging.get_dm_history",
                args: { other_user, limit: 50, offset: 0 },
                async: true,
            });
            const messages = r.message || [];
            for (const msg of messages) {
                const is_mine = msg.from_user === frappe.session.user;
                const role = is_mine ? "sent" : "received";
                const opts = {};
                if (msg.reply_preview) {
                    opts.reply_to_text = msg.reply_preview;
                    opts.reply_to_role = msg.reply_from === frappe.session.user ? "user" : "other";
                }
                this._append_dm_bubble(role, msg.message, is_mine ? "You" : other_name, opts, msg.name);
            }
            this._scroll_bottom();
        } catch (e) {
            this.$messages.html('<div class="ai-msg ai-msg-bot">Could not load messages</div>');
        }

        // Update input placeholder with AI name hint
        const ai_hint = this._ai_name || "AI Oracle";
        this.$input.attr("placeholder", `Message ${other_name}... (type @${ai_hint} to ask AI)`);

        // Refresh unread count
        this._load_unread_dm_count();
        this._load_dm_conversations();
    }

    _append_dm_bubble(role, text, sender_name, opts, dm_id) {
        opts = opts || {};
        const cls = role === "sent" ? "ai-msg-user" : "ai-msg-bot ai-msg-dm";
        const $msg = $(`<div class="ai-msg ${cls}" data-dm-id="${dm_id || ''}"></div>`);

        if (role === "received") {
            $msg.prepend(`<span class="ai-dm-sender-label">${frappe.utils.escape_html(sender_name)}</span>`);
        }

        // Reply quote
        if (opts.reply_to_text) {
            const $quote = $(`<div class="ai-reply-quote">
                <span class="ai-reply-quote-text">${frappe.utils.escape_html(opts.reply_to_text.substring(0, 100))}</span>
            </div>`);
            $msg.append($quote);
        }

        // Forward detection and rich rendering
        const fwd_match = text.match(/^(?:([\s\S]*?)\n\n)?--- Forwarded from (You|AI Assistant) ---\n\n?([\s\S]*)$/);
        if (fwd_match) {
            $msg.addClass("ai-msg-forwarded");
            const fwd_note = (fwd_match[1] || "").trim();
            const fwd_from = fwd_match[2];
            const fwd_body = (fwd_match[3] || "").trim();

            // Optional note above
            if (fwd_note) {
                $msg.append($('<div class="ai-fwd-note"></div>').text(fwd_note));
            }

            // Forwarded card
            const $card = $(`<div class="ai-fwd-card">
                <div class="ai-fwd-card-header">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="15 17 20 12 15 7"/>
                        <path d="M4 18v-2a4 4 0 0 1 4-4h12"/>
                    </svg>
                    <span>Forwarded from <strong>${frappe.utils.escape_html(fwd_from)}</strong></span>
                </div>
                <div class="ai-fwd-card-body"></div>
            </div>`);
            $card.find(".ai-fwd-card-body").html(erpnext_ai_bots.render_markdown(fwd_body));
            $msg.append($card);
        } else if (role === "received") {
            // Regular received message — render markdown
            $msg.append($('<div class="ai-dm-content"></div>').html(
                erpnext_ai_bots.render_markdown(text)
            ));
        } else {
            // Sent message — plain text
            $msg.append($('<span class="ai-msg-text"></span>').text(text));
        }

        // DM context menu (reply within DM)
        $msg.on("contextmenu", (e) => {
            e.preventDefault();
            this._show_dm_msg_ctx(e.pageX, e.pageY, dm_id, text);
        });

        this.$messages.append($msg);
        this._scroll_bottom();
        return $msg;
    }

    _show_dm_msg_ctx(x, y, dm_id, text) {
        this._dm_reply_target = { dm_id, text };
        // Reuse the message context menu but only show Reply + Copy
        this.$msg_ctx_menu.find(".ai-msg-ctx-forward").hide();
        this.$msg_ctx_menu.find(".ai-msg-ctx-reply").off("click").on("click", () => {
            this._hide_msg_ctx_menu();
            if (this._dm_reply_target) {
                this._start_dm_reply(this._dm_reply_target.dm_id, this._dm_reply_target.text);
            }
        });
        this.$msg_ctx_menu.find(".ai-msg-ctx-copy").off("click").on("click", () => {
            this._hide_msg_ctx_menu();
            if (text) {
                navigator.clipboard.writeText(text).then(() => {
                    frappe.show_alert({ message: __("Copied"), indicator: "green" });
                });
            }
        });
        const left = Math.min(x, window.innerWidth - 140);
        const top  = Math.min(y, window.innerHeight - 80);
        this.$msg_ctx_menu.css({ left, top }).show();
    }

    _start_dm_reply(dm_id, text) {
        this._dm_reply_to = dm_id;
        this.$reply_bar.find(".ai-reply-bar-label").text("Reply");
        this.$reply_bar.find(".ai-reply-bar-text").text(text.substring(0, 80));
        this.$reply_bar.show();
        this.$input.focus();
    }

    async _show_dm_user_picker() {
        this._user_picker_mode = "dm";
        this.$forward_modal.show();
        this.$forward_modal.find(".ai-forward-header span").text("New message to...");
        this.$forward_modal.find(".ai-forward-note-wrap").hide();
        this.$forward_modal.find(".ai-forward-search").val("").focus();
        this._load_user_picker_list();
    }

    // ── Send DM ──────────────────────────────────────────────────────

    async _send_dm(message) {
        this.$input.val("").trigger("input");

        const reply_to = this._dm_reply_to || null;
        const reply_opts = {};
        if (reply_to) {
            reply_opts.reply_to_text = this.$reply_bar.find(".ai-reply-bar-text").text();
        }
        this._cancel_reply();
        this._dm_reply_to = null;

        // Check for @ai mention (case-insensitive, match configured AI name)
        const ai_name = this._ai_name || "AI Oracle";
        const ai_pattern = new RegExp("^@" + ai_name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s+", "i");
        const ai_generic = /^@ai\s+/i;

        if (ai_pattern.test(message) || ai_generic.test(message)) {
            // Extract the question after the @mention
            const question = message.replace(ai_pattern, "").replace(ai_generic, "").trim();
            if (!question) {
                frappe.show_alert({ message: __("Please type a question after @" + ai_name), indicator: "orange" });
                return;
            }

            // Show the message immediately
            this._append_dm_bubble("sent", message, "You", reply_opts);

            // Show thinking indicator
            this._show_thinking();

            try {
                await frappe.call({
                    method: "erpnext_ai_bots.api.messaging.ask_ai_in_dm",
                    args: {
                        question: question,
                        to_user: this._dm_user,
                        company: this._current_company || "",
                    },
                    async: true,
                });
            } catch (e) {
                this._remove_status_indicators();
                frappe.show_alert({ message: __("Could not invoke AI"), indicator: "red" });
            }
            return;
        }

        // Regular DM — optimistic UI
        this._append_dm_bubble("sent", message, "You", reply_opts);

        try {
            await frappe.call({
                method: "erpnext_ai_bots.api.messaging.send_dm",
                args: {
                    to_user: this._dm_user,
                    message: message,
                    reply_to: reply_to,
                    company: this._current_company || "",
                },
                async: true,
            });
        } catch (e) {
            frappe.show_alert({ message: __("Could not send message"), indicator: "red" });
        }
    }

    // ── Export ───────────────────────────────────────────────────────

    async _export_html() {
        if (!this.session_id) {
            frappe.show_alert({ message: __("No active conversation to export"), indicator: "orange" });
            return;
        }
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.chat.export_session_html",
                args: { session_id: this.session_id },
                async: true,
            });
            const data = r.message || {};
            if (!data.html) {
                frappe.show_alert({ message: __("Export failed"), indicator: "red" });
                return;
            }
            // Open in a new tab via Blob URL so the user can print to PDF
            const blob = new Blob([data.html], { type: "text/html;charset=utf-8" });
            const url  = URL.createObjectURL(blob);
            const win  = window.open(url, "_blank");
            // Revoke the object URL after the window has a chance to load it
            if (win) {
                win.addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
            }
        } catch (e) {
            frappe.show_alert({ message: __("Could not export conversation"), indicator: "red" });
        }
    }

    async _export_csv() {
        if (!this.session_id) {
            frappe.show_alert({ message: __("No active conversation to export"), indicator: "orange" });
            return;
        }
        try {
            // Use a form POST so the browser triggers the file download
            // that the server sets up via frappe.response["type"] = "download".
            const base = frappe.request.url || "/api/method/";
            const url  = `/api/method/erpnext_ai_bots.api.chat.export_session_csv`
                       + `?session_id=${encodeURIComponent(this.session_id)}`
                       + `&cmd=erpnext_ai_bots.api.chat.export_session_csv`;
            // The simplest cross-browser way is a temporary <a> click
            const a = document.createElement("a");
            a.href = url;
            a.download = `${this.session_id}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        } catch (e) {
            frappe.show_alert({ message: __("Could not export conversation"), indicator: "red" });
        }
    }
};

// Auto-initialize when desk loads
$(document).on("app_ready", () => {
    if (frappe.session.user !== "Guest") {
        erpnext_ai_bots.chat = new erpnext_ai_bots.ChatWidget();
    }
});
