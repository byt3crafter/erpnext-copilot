frappe.provide("erpnext_ai_bots");

erpnext_ai_bots.OpenAIOAuth = class OpenAIOAuth {
    constructor(opts) {
        this.wrapper = opts.wrapper || null;
        this.on_connected = opts.on_connected || function () {};
        this.on_disconnected = opts.on_disconnected || function () {};
    }

    render(wrapper) {
        if (wrapper) this.wrapper = wrapper;
        if (!this.wrapper) return;

        this.$el = $(`
            <div class="openai-oauth-widget">
                <div class="openai-oauth-status">
                    <div class="openai-status-icon"></div>
                    <div class="openai-status-text">Checking...</div>
                </div>
                <div class="openai-oauth-actions"></div>
                <div class="openai-paste-section" style="display:none">
                    <p class="text-muted small">
                        After signing in to OpenAI, you'll be redirected to a page that won't load.
                        <strong>Copy the full URL</strong> from your browser's address bar and paste it below.
                    </p>
                    <div class="openai-paste-row">
                        <input type="text" class="form-control openai-callback-url"
                               placeholder="Paste the callback URL here..." />
                        <button class="btn btn-primary btn-sm openai-complete-btn">
                            Complete
                        </button>
                    </div>
                </div>
            </div>
        `).appendTo(this.wrapper);

        this._bind();
        this.check_status();
    }

    _bind() {
        this.$el.on("click", ".openai-connect-btn", () => this.start_oauth());
        this.$el.on("click", ".openai-disconnect-btn", () => this.disconnect());
        this.$el.on("click", ".openai-complete-btn", () => this.complete_oauth());
        this.$el.on("click", ".openai-refresh-btn", () => this.refresh_token());
    }

    async check_status() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.openai_oauth.oauth_status",
                async: true,
            });
            const data = r.message;
            this._render_status(data);
        } catch (e) {
            this._render_status({ connected: false });
        }
    }

    _render_status(data) {
        const $status = this.$el.find(".openai-status-icon");
        const $text = this.$el.find(".openai-status-text");
        const $actions = this.$el.find(".openai-oauth-actions");

        $actions.empty();

        if (data.connected) {
            $status.html('<span class="indicator-pill green">Connected</span>');
            $text.html(
                `Account: <strong>${data.account_id || "Unknown"}</strong>` +
                (data.token_expiry ? `<br><small class="text-muted">Expires: ${frappe.datetime.str_to_user(data.token_expiry)}</small>` : "")
            );
            $actions.html(`
                <button class="btn btn-xs btn-default openai-refresh-btn">Refresh Token</button>
                <button class="btn btn-xs btn-danger openai-disconnect-btn">Disconnect</button>
            `);
        } else if (data.status === "Expired") {
            $status.html('<span class="indicator-pill orange">Expired</span>');
            $text.text("Your OpenAI connection has expired.");
            $actions.html(`
                <button class="btn btn-sm btn-primary openai-connect-btn">Reconnect ChatGPT</button>
            `);
        } else {
            $status.html('<span class="indicator-pill grey">Not Connected</span>');
            $text.text("Connect your ChatGPT account to use OpenAI models.");
            $actions.html(`
                <button class="btn btn-sm btn-primary openai-connect-btn">Connect ChatGPT Account</button>
            `);
        }
    }

    async start_oauth() {
        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.openai_oauth.start_oauth",
                async: true,
            });
            const data = r.message;
            if (data && data.auth_url) {
                window.open(data.auth_url, "_blank");
                this.$el.find(".openai-paste-section").show();
                this.$el.find(".openai-callback-url").val("").focus();
            } else {
                frappe.msgprint(__("Failed to start OAuth flow"));
            }
        } catch (e) {
            frappe.msgprint(__("Failed to start OAuth flow: ") + (e.message || e));
        }
    }

    async complete_oauth() {
        const pasted_url = this.$el.find(".openai-callback-url").val().trim();
        if (!pasted_url) {
            frappe.show_alert({ message: __("Please paste the callback URL"), indicator: "orange" });
            return;
        }

        let code, state;
        try {
            const url = new URL(pasted_url);
            code = url.searchParams.get("code");
            state = url.searchParams.get("state");
        } catch (e) {
            frappe.show_alert({ message: __("Invalid URL"), indicator: "red" });
            return;
        }

        if (!code) {
            frappe.show_alert({ message: __("No authorization code found in URL"), indicator: "red" });
            return;
        }

        try {
            const r = await frappe.call({
                method: "erpnext_ai_bots.api.openai_oauth.exchange_code",
                args: { code, state },
                async: true,
            });
            const data = r.message;
            if (data && data.success) {
                frappe.show_alert({ message: __("ChatGPT account connected!"), indicator: "green" });
                this.$el.find(".openai-paste-section").hide();
                this.check_status();
                this.on_connected(data);
            } else {
                frappe.show_alert({ message: __("Connection failed"), indicator: "red" });
            }
        } catch (e) {
            frappe.msgprint(__("Connection failed: ") + (e.message || e));
        }
    }

    async disconnect() {
        frappe.confirm(
            __("Disconnect your ChatGPT account? You can reconnect later."),
            async () => {
                try {
                    await frappe.call({
                        method: "erpnext_ai_bots.api.openai_oauth.disconnect",
                        async: true,
                    });
                    frappe.show_alert({ message: __("Disconnected"), indicator: "green" });
                    this.check_status();
                    this.on_disconnected();
                } catch (e) {
                    frappe.msgprint(__("Disconnect failed"));
                }
            }
        );
    }

    async refresh_token() {
        try {
            await frappe.call({
                method: "erpnext_ai_bots.api.openai_oauth.refresh_access_token",
                async: true,
            });
            frappe.show_alert({ message: __("Token refreshed!"), indicator: "green" });
            this.check_status();
        } catch (e) {
            frappe.msgprint(__("Token refresh failed. You may need to reconnect."));
            this.check_status();
        }
    }
};
