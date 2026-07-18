/*!
 * BotForge embeddable chat widget — vanilla, dependency-free, Shadow-DOM isolated.
 * Embed:
 *   <script src="https://YOUR_HOST/widget.js" data-agent="PUBLIC_KEY" data-api="https://API_HOST" defer></script>
 * SDK: window.BotForge = { open, close, toggle, sendMessage, on, setUser }
 */
(function () {
  "use strict";
  if (window.__botforgeWidgetLoaded) return;
  window.__botforgeWidgetLoaded = true;

  var script =
    document.currentScript ||
    (function () {
      var s = document.getElementsByTagName("script");
      return s[s.length - 1];
    })();
  var PUBLIC_KEY = script && script.getAttribute("data-agent");
  var API =
    (script && script.getAttribute("data-api")) ||
    (location.protocol + "//" + location.hostname + ":8000");
  API = API.replace(/\/$/, "");
  if (!PUBLIC_KEY) {
    console.error("[BotForge] missing data-agent (public key) on the widget script tag");
    return;
  }

  var STORE_KEY = "botforge:conv:" + PUBLIC_KEY;
  var listeners = {};
  var state = {
    open: false,
    config: null,
    conversationId: (function () {
      try {
        return localStorage.getItem(STORE_KEY) || null;
      } catch (e) {
        return null;
      }
    })(),
    visitor: {},
    sending: false,
  };

  function emit(event, payload) {
    (listeners[event] || []).forEach(function (cb) {
      try {
        cb(payload);
      } catch (e) {
        /* ignore listener errors */
      }
    });
  }

  // ── Minimal, safe markdown (escape first, then a tiny subset) ──────────────
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function renderMarkdown(text) {
    var html = escapeHtml(text);
    html = html.replace(/```([\s\S]*?)```/g, function (_m, code) {
      return "<pre><code>" + code.replace(/\n$/, "") + "</code></pre>";
    });
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, function (_m, t, u) {
      return '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + t + "</a>";
    });
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  // ── Styles (injected into the shadow root) ─────────────────────────────────
  function styles(theme) {
    var accent = theme.primary_color || "#E8590C";
    var dark = theme.mode !== "light";
    var bg = dark ? "#16181D" : "#FFFFFF";
    var bg2 = dark ? "#1E2127" : "#F4F5F7";
    var text = dark ? "#E7E9EE" : "#14161A";
    var muted = dark ? "#9AA0AB" : "#5A616B";
    var border = dark ? "#2A2E37" : "#E3E6EA";
    var side = theme.position === "bottom-left" ? "left" : "right";
    return (
      ":host{all:initial}" +
      "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}" +
      ".bf-launcher{position:fixed;bottom:20px;" + side + ":20px;z-index:2147483000;display:flex;align-items:center;gap:10px;" +
      "height:56px;padding:0 18px 0 16px;border:none;border-radius:28px;cursor:pointer;color:#fff;background:" + accent + ";" +
      "box-shadow:0 8px 24px rgba(0,0,0,.28);font-size:15px;font-weight:600;transition:transform .15s}" +
      ".bf-launcher:hover{transform:translateY(-2px)}" +
      ".bf-launcher svg{width:22px;height:22px}" +
      ".bf-panel{position:fixed;bottom:88px;" + side + ":20px;z-index:2147483000;width:380px;max-width:calc(100vw - 32px);" +
      "height:600px;max-height:calc(100vh - 120px);background:" + bg + ";color:" + text + ";border:1px solid " + border + ";" +
      "border-radius:16px;box-shadow:0 24px 60px rgba(0,0,0,.35);display:none;flex-direction:column;overflow:hidden}" +
      ".bf-panel.bf-show{display:flex}" +
      ".bf-head{display:flex;align-items:center;gap:10px;padding:14px 16px;background:" + accent + ";color:#fff}" +
      ".bf-head .bf-title{font-weight:700;font-size:15px;flex:1}" +
      ".bf-x{background:transparent;border:none;color:#fff;cursor:pointer;font-size:20px;line-height:1;opacity:.9}" +
      ".bf-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:" + bg + "}" +
      ".bf-row{display:flex;gap:8px;max-width:100%}" +
      ".bf-row.bf-user{flex-direction:row-reverse}" +
      ".bf-bubble{max-width:80%;padding:9px 12px;border-radius:12px;font-size:14px;line-height:1.5;white-space:normal;word-wrap:break-word}" +
      ".bf-bot .bf-bubble{background:" + bg2 + ";color:" + text + ";border:1px solid " + border + "}" +
      ".bf-user .bf-bubble{background:" + accent + ";color:#fff}" +
      ".bf-bubble pre{background:rgba(0,0,0,.25);padding:8px;border-radius:8px;overflow-x:auto;margin:6px 0}" +
      ".bf-bubble code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}" +
      ".bf-bubble a{color:" + accent + "}" +
      ".bf-typing{display:inline-flex;gap:3px}.bf-typing i{width:6px;height:6px;border-radius:50%;background:" + muted + ";animation:bfb 1s infinite}" +
      ".bf-typing i:nth-child(2){animation-delay:.2s}.bf-typing i:nth-child(3){animation-delay:.4s}" +
      "@keyframes bfb{0%,60%,100%{opacity:.3}30%{opacity:1}}" +
      ".bf-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 16px 8px}" +
      ".bf-chip{border:1px solid " + border + ";background:" + bg2 + ";color:" + text + ";border-radius:14px;padding:6px 10px;" +
      "font-size:12.5px;cursor:pointer}" +
      ".bf-chip:hover{border-color:" + accent + "}" +
      ".bf-foot{border-top:1px solid " + border + ";padding:10px;display:flex;flex-direction:column;gap:6px;background:" + bg + "}" +
      ".bf-inrow{display:flex;align-items:flex-end;gap:8px}" +
      ".bf-file{flex:0 0 auto;width:36px;height:36px;border-radius:9px;border:1px solid " + border + ";background:" + bg2 + ";" +
      "color:" + muted + ";cursor:pointer;font-size:17px}" +
      ".bf-ta{flex:1;resize:none;max-height:120px;min-height:38px;padding:9px 11px;border-radius:9px;border:1px solid " + border + ";" +
      "background:" + bg2 + ";color:" + text + ";font-size:14px;outline:none}" +
      ".bf-ta:focus{border-color:" + accent + "}" +
      ".bf-send{flex:0 0 auto;width:38px;height:38px;border-radius:9px;border:none;cursor:pointer;background:" + accent + ";color:#fff;font-size:16px}" +
      ".bf-send:disabled{opacity:.5;cursor:default}" +
      ".bf-attach{font-size:12px;color:" + muted + ";padding:0 2px}" +
      ".bf-brand{text-align:center;font-size:11px;color:" + muted + ";padding:2px}" +
      ".bf-brand a{color:" + muted + ";text-decoration:none}" +
      "@media (max-width:480px){.bf-panel{width:100vw;height:100vh;max-height:100vh;bottom:0;" + side + ":0;border-radius:0}}"
    );
  }

  var ICON_CHAT =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

  var root, host, els = {};

  function build() {
    var theme = state.config.theme || {};
    host = document.createElement("div");
    host.id = "botforge-widget";
    document.body.appendChild(host);
    root = host.attachShadow({ mode: "open" });

    var style = document.createElement("style");
    style.textContent = styles(theme);
    root.appendChild(style);

    var launcher = document.createElement("button");
    launcher.className = "bf-launcher";
    launcher.setAttribute("aria-label", "Open chat");
    launcher.innerHTML = ICON_CHAT + "<span>" + escapeHtml(theme.launcher_text || "Chat") + "</span>";
    launcher.addEventListener("click", api.toggle);
    root.appendChild(launcher);
    els.launcher = launcher;

    var panel = document.createElement("div");
    panel.className = "bf-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Chat window");
    panel.innerHTML =
      '<div class="bf-head"><div class="bf-title"></div><button class="bf-x" aria-label="Close chat">&times;</button></div>' +
      '<div class="bf-msgs"></div>' +
      '<div class="bf-chips"></div>' +
      '<div class="bf-foot"><div class="bf-attach" style="display:none"></div>' +
      '<div class="bf-inrow">' +
      '<button class="bf-file" aria-label="Attach file">📎</button>' +
      '<textarea class="bf-ta" rows="1" placeholder="Type a message…" aria-label="Message"></textarea>' +
      '<button class="bf-send" aria-label="Send">➤</button>' +
      "</div>" +
      (theme.branding === false
        ? ""
        : '<div class="bf-brand">Powered by <a href="https://botforge.dev" target="_blank" rel="noopener">BotForge</a></div>') +
      '<input type="file" style="display:none" />';
    root.appendChild(panel);
    els.panel = panel;
    els.title = panel.querySelector(".bf-title");
    els.msgs = panel.querySelector(".bf-msgs");
    els.chips = panel.querySelector(".bf-chips");
    els.ta = panel.querySelector(".bf-ta");
    els.send = panel.querySelector(".bf-send");
    els.attach = panel.querySelector(".bf-attach");
    els.fileBtn = panel.querySelector(".bf-file");
    els.fileInput = panel.querySelector('input[type="file"]');
    els.title.textContent = state.config.name || "Chat";

    panel.querySelector(".bf-x").addEventListener("click", api.close);
    els.send.addEventListener("click", function () {
      submit();
    });
    els.ta.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      } else if (e.key === "Escape") {
        api.close();
      }
    });
    els.ta.addEventListener("input", autoGrow);
    els.fileBtn.addEventListener("click", function () {
      els.fileInput.click();
    });
    els.fileInput.addEventListener("change", onFile);

    renderChips();
    if (state.config.welcome_message) {
      addMessage("bot", state.config.welcome_message);
    }
    emit("ready", { config: state.config });
  }

  function autoGrow() {
    els.ta.style.height = "auto";
    els.ta.style.height = Math.min(els.ta.scrollHeight, 120) + "px";
  }

  var pendingFile = null;
  function onFile() {
    var f = els.fileInput.files && els.fileInput.files[0];
    if (!f) return;
    pendingFile = f;
    els.attach.style.display = "block";
    els.attach.textContent = "📎 " + f.name + " (sent as context)";
  }

  function renderChips() {
    els.chips.innerHTML = "";
    (state.config.suggested_prompts || []).forEach(function (p) {
      var text = typeof p === "string" ? p : p && p.label ? p.label : "";
      if (!text) return;
      var chip = document.createElement("button");
      chip.className = "bf-chip";
      chip.textContent = text;
      chip.addEventListener("click", function () {
        api.sendMessage(text);
      });
      els.chips.appendChild(chip);
    });
  }

  function addMessage(who, text) {
    var row = document.createElement("div");
    row.className = "bf-row " + (who === "user" ? "bf-user" : "bf-bot");
    var bubble = document.createElement("div");
    bubble.className = "bf-bubble";
    if (who === "bot") bubble.innerHTML = text ? renderMarkdown(text) : "";
    else bubble.textContent = text;
    row.appendChild(bubble);
    els.msgs.appendChild(row);
    els.msgs.scrollTop = els.msgs.scrollHeight;
    return bubble;
  }

  function typingBubble() {
    var row = document.createElement("div");
    row.className = "bf-row bf-bot";
    var bubble = document.createElement("div");
    bubble.className = "bf-bubble";
    bubble.innerHTML = '<span class="bf-typing"><i></i><i></i><i></i></span>';
    row.appendChild(bubble);
    els.msgs.appendChild(row);
    els.msgs.scrollTop = els.msgs.scrollHeight;
    return bubble;
  }

  function submit() {
    var text = els.ta.value.trim();
    if (!text || state.sending) return;
    els.ta.value = "";
    autoGrow();
    api.sendMessage(text);
  }

  async function sendMessage(text) {
    if (!text || state.sending) return;
    if (!state.open) api.open();
    state.sending = true;
    els.send.disabled = true;
    var full = text;
    if (pendingFile) {
      full += "\n\n[Attached file: " + pendingFile.name + "]";
      try {
        if (pendingFile.type.indexOf("text") === 0 || /\.(txt|md|csv|json)$/i.test(pendingFile.name)) {
          full += "\n" + (await pendingFile.text()).slice(0, 4000);
        }
      } catch (e) {
        /* ignore */
      }
      pendingFile = null;
      els.attach.style.display = "none";
    }
    addMessage("user", text);
    var bubble = typingBubble();
    var acc = "";
    emit("message", { role: "user", content: text });

    try {
      var resp = await fetch(API + "/v1/public/agents/" + PUBLIC_KEY + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: full,
          conversation_id: state.conversationId,
          stream: true,
          visitor: Object.keys(state.visitor).length ? state.visitor : undefined,
        }),
      });
      if (!resp.ok || !resp.body) throw new Error("chat request failed (" + resp.status + ")");
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        var parts = buffer.split("\n\n");
        buffer = parts.pop();
        for (var i = 0; i < parts.length; i++) {
          var line = parts[i].trim();
          if (line.indexOf("data:") !== 0) continue;
          var payload = line.slice(5).trim();
          if (!payload) continue;
          var ev;
          try {
            ev = JSON.parse(payload);
          } catch (e) {
            continue;
          }
          if (ev.type === "conversation" && ev.conversation_id) {
            state.conversationId = ev.conversation_id;
            try {
              localStorage.setItem(STORE_KEY, ev.conversation_id);
            } catch (e2) {}
          } else if (ev.type === "token" && ev.delta) {
            acc += ev.delta;
            bubble.innerHTML = renderMarkdown(acc);
            els.msgs.scrollTop = els.msgs.scrollHeight;
          } else if (ev.type === "error") {
            acc += (acc ? "\n\n" : "") + "⚠ " + (ev.error || "something went wrong");
            bubble.innerHTML = renderMarkdown(acc);
          }
        }
      }
      if (!acc) bubble.textContent = "…";
      emit("response", { content: acc });
      emit("message", { role: "assistant", content: acc });
    } catch (err) {
      bubble.textContent = "⚠ " + (err && err.message ? err.message : "connection error");
    } finally {
      state.sending = false;
      els.send.disabled = false;
    }
  }

  var api = {
    open: function () {
      if (!els.panel) return;
      state.open = true;
      els.panel.classList.add("bf-show");
      els.launcher.setAttribute("aria-expanded", "true");
      setTimeout(function () {
        els.ta && els.ta.focus();
      }, 50);
      emit("open");
    },
    close: function () {
      if (!els.panel) return;
      state.open = false;
      els.panel.classList.remove("bf-show");
      emit("close");
    },
    toggle: function () {
      state.open ? api.close() : api.open();
    },
    sendMessage: function (text) {
      sendMessage(String(text || ""));
    },
    setUser: function (u) {
      state.visitor = u || {};
    },
    on: function (event, cb) {
      (listeners[event] = listeners[event] || []).push(cb);
    },
  };

  async function init() {
    try {
      var r = await fetch(API + "/v1/public/agents/" + PUBLIC_KEY + "/config");
      if (!r.ok) throw new Error("config " + r.status);
      state.config = await r.json();
    } catch (e) {
      console.error("[BotForge] could not load widget config:", e);
      return;
    }
    build();
    window.BotForge = api;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
