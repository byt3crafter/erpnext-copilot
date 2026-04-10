frappe.ui.form.on("AI Bot Settings", {
    refresh(frm) {
        // Remove ALL previous instances first
        frm.$wrapper.find(".openai-oauth-container").remove();

        let $section = (frm.fields_dict.oauth_section && frm.fields_dict.oauth_section.$wrapper)
            || frm.$wrapper.find('[data-fieldname="oauth_section"]');

        if (!$section || !$section.length) return;

        let $container = $('<div class="openai-oauth-container" style="padding: 15px;"></div>');
        $section.after($container);

        // Check connection status and render appropriate UI
        frappe.call({
            method: "erpnext_ai_bots.api.openai_oauth.oauth_status",
            async: true,
            callback: function (r) {
                let data = r.message || {};
                $container.empty();

                if (data.connected) {
                    $container.html(`
                        <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
                            <span class="indicator-pill green">Connected</span>
                            <span>Account: <strong>${data.account_id || "Unknown"}</strong></span>
                        </div>
                        ${data.token_expiry ? '<p class="text-muted" style="margin:0 0 10px;">Expires: ' + data.token_expiry + '</p>' : ''}
                        <button class="btn btn-xs btn-default openai-refresh-btn" style="margin-right:8px;">Refresh Token</button>
                        <button class="btn btn-xs btn-danger openai-disconnect-btn">Disconnect</button>
                    `);
                } else {
                    let status_label = data.status === "Expired"
                        ? '<span class="indicator-pill orange">Expired</span>'
                        : '<span class="indicator-pill grey">Not Connected</span>';
                    $container.html(`
                        <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
                            ${status_label}
                            <span class="text-muted">Connect your ChatGPT Plus/Pro/Max account</span>
                        </div>
                        <button class="btn btn-sm btn-primary openai-connect-btn">Connect ChatGPT Account</button>
                        <div class="openai-paste-section" style="display:none; margin-top:15px; padding:12px; border:1px dashed var(--border-color, #d1d8dd); border-radius:6px;">
                            <p class="text-muted" style="font-size:12px;">
                                After signing in, you'll be redirected to a page that <strong>won't load</strong>.
                                Copy the <strong>full URL</strong> from your browser's address bar and paste it below.
                            </p>
                            <div style="display:flex; gap:8px;">
                                <input type="text" class="form-control openai-callback-url"
                                       placeholder="Paste the callback URL here (http://localhost:1455/auth/callback?code=...)" />
                                <button class="btn btn-primary btn-sm openai-complete-btn">Complete</button>
                            </div>
                        </div>
                    `);
                }

                // Bind events
                $container.find(".openai-connect-btn").on("click", function () {
                    frappe.call({
                        method: "erpnext_ai_bots.api.openai_oauth.start_oauth",
                        async: true,
                        callback: function (r) {
                            let d = r.message || {};
                            if (d.auth_url) {
                                window.open(d.auth_url, "_blank");
                                $container.find(".openai-paste-section").show();
                                $container.find(".openai-callback-url").focus();
                            } else {
                                frappe.msgprint(__("Failed to start OAuth flow"));
                            }
                        },
                        error: function () {
                            frappe.msgprint(__("Failed to start OAuth flow"));
                        }
                    });
                });

                $container.find(".openai-complete-btn").on("click", function () {
                    let pasted = $container.find(".openai-callback-url").val().trim();
                    if (!pasted) {
                        frappe.show_alert({ message: __("Please paste the callback URL"), indicator: "orange" });
                        return;
                    }
                    let code, state;
                    try {
                        let url = new URL(pasted);
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
                    frappe.call({
                        method: "erpnext_ai_bots.api.openai_oauth.exchange_code",
                        args: { code: code, state: state || "" },
                        async: true,
                        callback: function (r) {
                            let d = r.message || {};
                            if (d.success) {
                                frappe.show_alert({ message: __("ChatGPT account connected!"), indicator: "green" });
                                frm.refresh();
                            } else {
                                frappe.msgprint(__("Connection failed"));
                            }
                        },
                        error: function () {
                            frappe.msgprint(__("Connection failed. Try starting the flow again."));
                        }
                    });
                });

                $container.find(".openai-refresh-btn").on("click", function () {
                    frappe.call({
                        method: "erpnext_ai_bots.api.openai_oauth.refresh_access_token",
                        async: true,
                        callback: function () {
                            frappe.show_alert({ message: __("Token refreshed!"), indicator: "green" });
                            frm.refresh();
                        },
                        error: function () {
                            frappe.msgprint(__("Refresh failed. You may need to reconnect."));
                            frm.refresh();
                        }
                    });
                });

                $container.find(".openai-disconnect-btn").on("click", function () {
                    frappe.confirm(__("Disconnect your ChatGPT account?"), function () {
                        frappe.call({
                            method: "erpnext_ai_bots.api.openai_oauth.disconnect",
                            async: true,
                            callback: function () {
                                frappe.show_alert({ message: __("Disconnected"), indicator: "green" });
                                frm.refresh();
                            }
                        });
                    });
                });
            },
            error: function () {
                $container.html('<p class="text-muted">Could not check OAuth status.</p>');
            }
        });
    },
});
