frappe.provide("erpnext_ai_bots.stream");

erpnext_ai_bots.stream.StreamHandler = class StreamHandler {
    /**
     * Subscribes to Socket.IO events for a chat session.
     *
     * Usage:
     *   const handler = new erpnext_ai_bots.stream.StreamHandler(session_id, {
     *       onChunk: (text) => {},
     *       onToolStart: (tool, input) => {},
     *       onToolResult: (tool, result) => {},
     *       onDone: () => {},
     *       onError: (error) => {},
     *   });
     */
    constructor(session_id, callbacks) {
        this.session_id = session_id;
        this.callbacks = callbacks;
        this._handlers = {};
        this._bind();
    }

    _bind() {
        const events = {
            ai_chunk: (data) => {
                if (data.session_id !== this.session_id) return;
                if (this.callbacks.onChunk) this.callbacks.onChunk(data.text);
            },
            ai_tool_start: (data) => {
                if (data.session_id !== this.session_id) return;
                if (this.callbacks.onToolStart) this.callbacks.onToolStart(data.tool, data.input);
            },
            ai_tool_result: (data) => {
                if (data.session_id !== this.session_id) return;
                if (this.callbacks.onToolResult) this.callbacks.onToolResult(data.tool, data.result);
            },
            ai_done: (data) => {
                if (data.session_id !== this.session_id) return;
                if (this.callbacks.onDone) this.callbacks.onDone();
            },
            ai_error: (data) => {
                if (data.session_id !== this.session_id) return;
                if (this.callbacks.onError) this.callbacks.onError(data.error);
            },
        };

        for (const [event, handler] of Object.entries(events)) {
            this._handlers[event] = handler;
            frappe.realtime.on(event, handler);
        }
    }

    destroy() {
        for (const [event, handler] of Object.entries(this._handlers)) {
            frappe.realtime.off(event, handler);
        }
        this._handlers = {};
    }
};
