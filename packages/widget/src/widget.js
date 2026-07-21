/*!
 * BotForge embeddable chat widget — vanilla, dependency-free, Shadow-DOM isolated.
 * Embed:
 *   <script src="https://YOUR_HOST/widget.js" data-agent="PUBLIC_KEY" data-api="https://API_HOST" defer></script>
 * SDK: window.BotForge = { open, close, toggle, sendMessage, on, setUser }
 *
 * All theming is applied via CSS custom properties set from the fetched config, so the
 * stylesheet is static and never needs a per-agent rebuild. In preview mode
 * (data-preview-mode="true") the parent page posts { type: "bf-preview-config", config }
 * to update the live widget instantly without saving.
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
  var PREVIEW = script && script.getAttribute("data-preview-mode") === "true";
  var API =
    (script && script.getAttribute("data-api")) ||
    (location.protocol + "//" + location.hostname + ":8000");
  API = API.replace(/\/$/, "");
  if (!PUBLIC_KEY && !PREVIEW) {
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
    hasConversation: false,
    ws: null,
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

  // ── Theme helpers ──────────────────────────────────────────────────────────
  // Pick a foreground (near-black or white) that meets WCAG contrast on the given bg color.
  function onColor(hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
    if (!m) return "#ffffff";
    var n = parseInt(m[1], 16);
    var srgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(function (c) {
      c /= 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    var lum = 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2];
    return 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05 ? "#ffffff" : "#111318";
  }

  var FONT_STACKS = {
    system: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif",
    inter: "Inter,-apple-system,'Segoe UI',Roboto,sans-serif",
    arial: "Arial,Helvetica,sans-serif",
    georgia: "Georgia,'Times New Roman',serif",
    courier: "'Courier New',Courier,monospace",
  };

  function logoUrl(theme) {
    var u = theme.logo_url;
    if (!u) return "";
    return u.charAt(0) === "/" ? API + u : u;
  }

  // Resolve the full palette from a theme, honoring mode defaults + explicit overrides.
  function palette(theme) {
    theme = theme || {};
    var dark = theme.mode !== "light";
    var accent = theme.primary_color || "#E8590C";
    var btn = theme.floating_button_color || accent;
    return {
      accent: accent,
      onAccent: onColor(accent),
      bg: theme.background_color || (dark ? "#16181D" : "#FFFFFF"),
      bg2: dark ? "#1E2127" : "#F4F5F7",
      text: theme.text_color || (dark ? "#E7E9EE" : "#14161A"),
      muted: dark ? "#9AA0AB" : "#5A616B",
      border: dark ? "#2A2E37" : "#E3E6EA",
      bubble: theme.bubble_color || accent,
      onBubble: onColor(theme.bubble_color || accent),
      input: theme.typing_area_color || (dark ? "#1E2127" : "#F4F5F7"),
      btn: btn,
      onBtn: onColor(btn),
      font: FONT_STACKS[theme.font_family] || FONT_STACKS.system,
      dark: dark,
    };
  }

  // Apply a theme to the (already built) widget via CSS custom properties + classes — no rebuild.
  function applyTheme(theme) {
    if (!host) return;
    var p = palette(theme);
    var vars = {
      "--bf-accent": p.accent,
      "--bf-on-accent": p.onAccent,
      "--bf-bg": p.bg,
      "--bf-bg2": p.bg2,
      "--bf-text": p.text,
      "--bf-muted": p.muted,
      "--bf-border": p.border,
      "--bf-bubble": p.bubble,
      "--bf-on-bubble": p.onBubble,
      "--bf-input": p.input,
      "--bf-btn": p.btn,
      "--bf-on-btn": p.onBtn,
      "--bf-font": p.font,
    };
    for (var k in vars) host.style.setProperty(k, vars[k]);
    root.host.classList.toggle("bf-transparent", theme.widget_style === "transparent");
    root.host.classList.toggle("bf-left", theme.position === "bottom-left");
  }

  // ── Static stylesheet (references CSS vars set by applyTheme) ───────────────
  function styles() {
    return (
      ":host{all:initial}" +
      "*{box-sizing:border-box;font-family:var(--bf-font)}" +
      // launcher (right by default; :host(.bf-left) flips to the left)
      ".bf-launcher{position:fixed;bottom:20px;right:20px;z-index:2147483000;" +
      "display:flex;align-items:center;justify-content:center;gap:10px;min-width:56px;height:56px;" +
      "padding:0;border:none;border-radius:50%;cursor:pointer;color:var(--bf-on-btn);background:var(--bf-btn);" +
      "box-shadow:0 8px 24px rgba(0,0,0,.28);font-size:15px;font-weight:600;transition:transform .15s;overflow:hidden}" +
      ".bf-launcher.bf-pill{border-radius:28px;padding:0 18px 0 16px}" +
      ".bf-launcher.bf-square{border-radius:18px}" +
      ".bf-launcher:hover{transform:translateY(-2px)}" +
      ".bf-launcher svg{width:24px;height:24px}" +
      ".bf-launcher img.bf-logo{width:34px;height:34px;border-radius:50%;object-fit:cover}" +
      ".bf-launcher .bf-lbl{white-space:nowrap}" +
      ".bf-launcher .bf-chip-logo{width:26px;height:26px;border-radius:50%;object-fit:cover}" +
      // pulse-ring animation
      ".bf-launcher.bf-pulse::after{content:'';position:absolute;inset:0;border-radius:50%;" +
      "box-shadow:0 0 0 0 var(--bf-btn);animation:bfpulse 1.8s cubic-bezier(.66,0,0,1) infinite;z-index:-1}" +
      "@keyframes bfpulse{to{box-shadow:0 0 0 16px rgba(0,0,0,0)}}" +
      "@media (prefers-reduced-motion:reduce){.bf-launcher.bf-pulse::after{animation:none}}" +
      // panel
      ".bf-panel{position:fixed;bottom:88px;right:20px;z-index:2147483000;width:380px;" +
      "max-width:calc(100vw - 32px);height:600px;max-height:calc(100vh - 120px);background:var(--bf-bg);" +
      "color:var(--bf-text);border:1px solid var(--bf-border);border-radius:16px;box-shadow:0 24px 60px rgba(0,0,0,.35);" +
      "display:none;flex-direction:column;overflow:hidden}" +
      ".bf-panel.bf-show{display:flex}" +
      ":host(.bf-left) .bf-launcher,:host(.bf-left) .bf-panel{right:auto;left:20px}" +
      // Transparent style = its own independent glass palette (not "theme + blur"): no solid
      // header bar, white-glass bot side with fixed near-black text (guaranteed contrast, not the
      // mode's text var), and a genuinely dark floating input pill. User bubbles keep the accent.
      ":host(.bf-transparent) .bf-panel{background:transparent;border-color:transparent;box-shadow:none}" +
      ":host(.bf-transparent) .bf-msgs{background:transparent}" +
      ":host(.bf-transparent) .bf-head{background:transparent;color:var(--bf-text-on-transparent,#171717)}" +
      ":host(.bf-transparent) .bf-head .bf-x{color:var(--bf-text-on-transparent,#171717)}" +
      ":host(.bf-transparent) .bf-bot .bf-bubble{background:rgba(255,255,255,.7);color:#171717;border-color:rgba(0,0,0,.06);backdrop-filter:blur(10px)}" +
      ":host(.bf-transparent) .bf-chip{background:rgba(255,255,255,.7);color:#171717;border-color:rgba(0,0,0,.06)}" +
      ":host(.bf-transparent) .bf-foot{background:rgba(23,23,23,.8);color:#fff;backdrop-filter:blur(10px);border-radius:14px;margin:8px;border:1px solid rgba(255,255,255,.12)}" +
      ":host(.bf-transparent) .bf-ta{background:rgba(255,255,255,.1);color:#fff;border-color:rgba(255,255,255,.16)}" +
      ":host(.bf-transparent) .bf-iconbtn{background:rgba(255,255,255,.1);color:#fff;border-color:rgba(255,255,255,.16)}" +
      ":host(.bf-transparent) .bf-brand,:host(.bf-transparent) .bf-brand a{color:rgba(255,255,255,.7)}" +
      ".bf-head{display:flex;align-items:center;gap:10px;padding:14px 16px;background:var(--bf-accent);color:var(--bf-on-accent)}" +
      ".bf-head .bf-avatar{width:26px;height:26px;border-radius:50%;object-fit:cover}" +
      ".bf-head .bf-title{font-weight:700;font-size:15px;flex:1}" +
      ".bf-x{background:transparent;border:none;color:var(--bf-on-accent);cursor:pointer;font-size:20px;line-height:1;opacity:.9}" +
      ".bf-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:var(--bf-bg)}" +
      ".bf-row{display:flex;gap:8px;max-width:100%}" +
      ".bf-row.bf-user{flex-direction:row-reverse}" +
      ".bf-avatar-sm{width:24px;height:24px;border-radius:50%;object-fit:cover;flex:0 0 auto;align-self:flex-end}" +
      ".bf-bubble{max-width:80%;padding:9px 12px;border-radius:12px;font-size:14px;line-height:1.5;white-space:normal;word-wrap:break-word}" +
      ".bf-bot .bf-bubble{background:var(--bf-bg2);color:var(--bf-text);border:1px solid var(--bf-border)}" +
      ".bf-user .bf-bubble{background:var(--bf-bubble);color:var(--bf-on-bubble)}" +
      ".bf-bubble pre{background:rgba(0,0,0,.25);padding:8px;border-radius:8px;overflow-x:auto;margin:6px 0}" +
      ".bf-bubble code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}" +
      ".bf-bubble a{color:var(--bf-accent)}" +
      ".bf-typing{display:inline-flex;gap:3px}.bf-typing i{width:6px;height:6px;border-radius:50%;background:var(--bf-muted);animation:bfb 1s infinite}" +
      ".bf-typing i:nth-child(2){animation-delay:.2s}.bf-typing i:nth-child(3){animation-delay:.4s}" +
      "@keyframes bfb{0%,60%,100%{opacity:.3}30%{opacity:1}}" +
      "@media (prefers-reduced-motion:reduce){.bf-typing i{animation:none;opacity:.6}}" +
      ".bf-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 16px 8px}" +
      ".bf-chip{border:1px solid var(--bf-border);background:var(--bf-bg2);color:var(--bf-text);border-radius:14px;padding:6px 10px;font-size:12.5px;cursor:pointer}" +
      ".bf-chip:hover{border-color:var(--bf-accent)}" +
      ".bf-foot{border-top:1px solid var(--bf-border);padding:10px;display:flex;flex-direction:column;gap:6px;background:var(--bf-bg)}" +
      ".bf-inrow{display:flex;align-items:flex-end;gap:8px;position:relative}" +
      ".bf-iconbtn{flex:0 0 auto;width:36px;height:36px;border-radius:9px;border:1px solid var(--bf-border);background:var(--bf-input);color:var(--bf-muted);cursor:pointer;font-size:17px}" +
      ".bf-emoji-pop{position:absolute;bottom:44px;left:0;display:flex;flex-wrap:wrap;gap:4px;width:220px;padding:8px;border:1px solid var(--bf-border);background:var(--bf-bg2);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.3)}" +
      ".bf-emoji-pop button{border:none;background:transparent;cursor:pointer;font-size:18px;line-height:1;padding:3px;border-radius:6px}" +
      ".bf-emoji-pop button:hover{background:var(--bf-input)}" +
      ".bf-ta{flex:1;resize:none;max-height:120px;min-height:38px;padding:9px 11px;border-radius:9px;border:1px solid var(--bf-border);" +
      "background:var(--bf-input);color:var(--bf-text);font-size:14px;outline:none;font-family:var(--bf-font)}" +
      ".bf-ta:focus{border-color:var(--bf-accent)}" +
      ".bf-send{flex:0 0 auto;width:38px;height:38px;border-radius:9px;border:none;cursor:pointer;background:var(--bf-accent);color:var(--bf-on-accent);font-size:16px}" +
      ".bf-send:disabled{opacity:.5;cursor:default}" +
      ".bf-attach{font-size:12px;color:var(--bf-muted);padding:0 2px}" +
      ".bf-brand{text-align:center;font-size:11px;color:var(--bf-muted);padding:2px}" +
      ".bf-brand a{color:var(--bf-muted);text-decoration:none}" +
      "@media (max-width:480px){.bf-panel,:host(.bf-left) .bf-panel{width:100vw;height:100vh;max-height:100vh;bottom:0;right:0;left:0;border-radius:0}}"
    );
  }

  // ── Icons (inline SVG, no icon library) ────────────────────────────────────
  var ICON_CHAT =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  var ICON_MESSAGE =
    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2z"/><rect x="6" y="8" width="12" height="1.8" rx=".9" fill="var(--bf-btn)"/><rect x="6" y="11.4" width="8" height="1.8" rx=".9" fill="var(--bf-btn)"/></svg>';
  var ICON_DOTS =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><circle cx="8" cy="10" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="10" r="1" fill="currentColor" stroke="none"/><circle cx="16" cy="10" r="1" fill="currentColor" stroke="none"/></svg>';

  var root, host, els = {};

  // Build the launcher's inner content + shape class for a given design (or the close button).
  function launcherContent(theme, open) {
    var l = els.launcher;
    l.className = "bf-launcher";
    if (open) {
      l.setAttribute("aria-label", "Close chat");
      l.innerHTML = "&times;";
      l.style.fontSize = "26px";
      return;
    }
    l.setAttribute("aria-label", "Open chat");
    l.style.fontSize = "";
    var style = theme.floating_button_style || null; // null → legacy pill
    var logo = logoUrl(theme);
    var logoImg = logo ? '<img class="bf-logo" src="' + logo + '" alt="" />' : "";
    var label = escapeHtml(theme.launcher_text || "Chat with us");
    if (style === "pill-text" || style === null) {
      l.classList.add("bf-pill");
      l.innerHTML = (logo ? '<img class="bf-chip-logo" src="' + logo + '" alt="" />' : ICON_CHAT) +
        '<span class="bf-lbl">' + label + "</span>";
    } else if (style === "rounded-square") {
      l.classList.add("bf-square");
      l.innerHTML = logoImg || ICON_CHAT;
    } else if (style === "circle-message") {
      l.innerHTML = logoImg || ICON_MESSAGE;
    } else if (style === "circle-dots") {
      l.innerHTML = logoImg || ICON_DOTS;
    } else if (style === "pulse-ring") {
      l.classList.add("bf-pulse");
      l.innerHTML = logoImg || ICON_CHAT;
    } else {
      // circle-chat (default design)
      l.innerHTML = logoImg || ICON_CHAT;
    }
  }

  var EMOJIS = ["😀", "😄", "😊", "👍", "🙏", "🎉", "❤️", "🔥", "😎", "🤔", "😅", "🙌", "👏", "✅", "⭐", "💡", "😍", "🚀"];

  function build() {
    var theme = state.config.theme || {};
    host = document.createElement("div");
    host.id = "botforge-widget";
    document.body.appendChild(host);
    root = host.attachShadow({ mode: "open" });

    var style = document.createElement("style");
    style.textContent = styles();
    root.appendChild(style);

    var launcher = document.createElement("button");
    launcher.className = "bf-launcher";
    root.appendChild(launcher);
    els.launcher = launcher;
    launcher.addEventListener("click", api.toggle);

    // Static structure — built once. Every config-driven detail (colors, logo, input buttons,
    // branding, chips, welcome, launcher design) is filled in by applyConfig() below, so a
    // config change never tears the widget down or changes whether the panel is open.
    var panel = document.createElement("div");
    panel.className = "bf-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Chat window");
    panel.innerHTML =
      '<div class="bf-head"><img class="bf-avatar" alt="" style="display:none" />' +
      '<div class="bf-title"></div><button class="bf-x" aria-label="Close chat">&times;</button></div>' +
      '<div class="bf-msgs"></div>' +
      '<div class="bf-chips"></div>' +
      '<div class="bf-foot"><div class="bf-attach" style="display:none"></div>' +
      '<div class="bf-inrow">' +
      '<button class="bf-iconbtn bf-file" aria-label="Attach file">📎</button>' +
      '<button class="bf-iconbtn bf-emoji" aria-label="Insert emoji">🙂</button>' +
      '<textarea class="bf-ta" rows="1" placeholder="Type a message…" aria-label="Message"></textarea>' +
      '<button class="bf-send" aria-label="Send">➤</button>' +
      "</div>" +
      '<div class="bf-brand">Powered by <a href="https://botforge.dev" target="_blank" rel="noopener">BotForge</a></div>' +
      '<input type="file" style="display:none" /></div>';
    root.appendChild(panel);
    els.panel = panel;
    els.avatar = panel.querySelector(".bf-avatar");
    els.title = panel.querySelector(".bf-title");
    els.msgs = panel.querySelector(".bf-msgs");
    els.chips = panel.querySelector(".bf-chips");
    els.ta = panel.querySelector(".bf-ta");
    els.send = panel.querySelector(".bf-send");
    els.attach = panel.querySelector(".bf-attach");
    els.fileBtn = panel.querySelector(".bf-file");
    els.emojiBtn = panel.querySelector(".bf-emoji");
    els.brand = panel.querySelector(".bf-brand");
    els.inrow = panel.querySelector(".bf-inrow");
    els.fileInput = panel.querySelector('input[type="file"]');

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
    els.emojiBtn.addEventListener("click", toggleEmoji);

    applyConfig(state.config);
    emit("ready", { config: state.config });
  }

  // Apply a (possibly changed) config in place — no teardown, no forced open/close. Preserves
  // whatever state.open currently is. Safe to call repeatedly (used by the builder live preview).
  function applyConfig(config) {
    if (!els.panel) return;
    state.config = config || state.config;
    var theme = state.config.theme || {};
    applyTheme(theme);
    els.title.textContent = state.config.name || "Chat";
    var logo = logoUrl(theme);
    if (logo) {
      els.avatar.src = logo;
      els.avatar.style.display = "";
    } else {
      els.avatar.removeAttribute("src");
      els.avatar.style.display = "none";
    }
    var buttons = theme.input_bar_buttons || ["attachment"];
    els.fileBtn.style.display = buttons.indexOf("attachment") !== -1 ? "" : "none";
    els.emojiBtn.style.display = buttons.indexOf("emoji") !== -1 ? "" : "none";
    els.brand.style.display = theme.branding === false ? "none" : "";
    renderChips();
    refreshWelcome(state.config.welcome_message);
    launcherContent(theme, state.open); // keep the current open/closed state
  }

  // Manage the welcome bubble in place while no real conversation has started (design preview).
  function refreshWelcome(text) {
    if (!els.msgs) return;
    if (state.hasConversation) return; // don't disturb an in-progress chat
    els.msgs.innerHTML = "";
    els.welcomeBubble = text ? addMessage("bot", text) : null;
  }

  function toggleEmoji() {
    var existing = els.inrow.querySelector(".bf-emoji-pop");
    if (existing) {
      existing.remove();
      return;
    }
    var pop = document.createElement("div");
    pop.className = "bf-emoji-pop";
    EMOJIS.forEach(function (e) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = e;
      b.addEventListener("click", function () {
        els.ta.value += e;
        els.ta.focus();
        pop.remove();
      });
      pop.appendChild(b);
    });
    els.inrow.appendChild(pop);
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
    if (who === "bot") {
      var logo = logoUrl(state.config.theme || {});
      if (logo) {
        var av = document.createElement("img");
        av.className = "bf-avatar-sm";
        av.src = logo;
        av.alt = "";
        row.appendChild(av);
      }
    }
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
    state.hasConversation = true;
    if (PREVIEW) {
      // In preview mode there's no live backend turn — just echo locally so the design shows.
      addMessage("user", text);
      addMessage("bot", "This is a preview. Your real agent will reply here.");
      return;
    }
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
            ensureSubscription(ev.conversation_id);
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

  // Listen socket: receive operator replies / handback pushes for this conversation.
  function ensureSubscription(cid) {
    if (state.ws || !cid) return;
    try {
      var wsBase = API.replace(/^http/, "ws");
      var ws = new WebSocket(wsBase + "/v1/public/agents/" + PUBLIC_KEY + "/subscribe?conversation_id=" + cid);
      state.ws = ws;
      ws.onmessage = function (e) {
        var ev;
        try {
          ev = JSON.parse(e.data);
        } catch (err) {
          return;
        }
        if (ev.type === "operator_message" && ev.content) {
          addMessage("bot", ev.content);
          emit("message", { role: "assistant", content: ev.content, operator: true });
        } else if (ev.type === "handback" && ev.content) {
          addMessage("bot", ev.content);
        }
      };
      ws.onclose = function () {
        state.ws = null;
      };
    } catch (err) {
      /* WS unavailable — degrade gracefully (operator replies still persist) */
    }
  }

  var api = {
    open: function () {
      if (!els.panel) return;
      state.open = true;
      els.panel.classList.add("bf-show");
      els.launcher.setAttribute("aria-expanded", "true");
      launcherContent(state.config.theme || {}, true);
      setTimeout(function () {
        els.ta && els.ta.focus();
      }, 50);
      emit("open");
    },
    close: function () {
      if (!els.panel) return;
      state.open = false;
      els.panel.classList.remove("bf-show");
      els.launcher.setAttribute("aria-expanded", "false");
      launcherContent(state.config.theme || {}, false);
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

  // ── Preview mode: apply live config overrides posted by the builder ─────────
  function previewListener(ev) {
    var d = ev && ev.data;
    if (!d || d.type !== "bf-preview-config" || !d.config) return;
    var incoming = d.config;
    var base = state.config || { theme: {} };
    // Optional builder-only backdrop for the preview *page* (never part of the widget/embed).
    if (typeof d.previewBackdrop === "string") {
      document.body.style.background = d.previewBackdrop;
    }
    // Merge posted config over the base (theme is replaced wholesale from the builder's full state).
    var merged = {
      agent_id: base.agent_id,
      name: incoming.name != null ? incoming.name : base.name,
      welcome_message: incoming.welcome_message != null ? incoming.welcome_message : base.welcome_message,
      suggested_prompts: incoming.suggested_prompts || base.suggested_prompts || [],
      theme: incoming.theme || base.theme || {},
    };
    // Apply in place — preserves whether the panel is currently open, and never force-opens it.
    applyConfig(merged);
  }

  async function init() {
    if (PREVIEW) {
      // Start from an empty/default config; the parent posts the real one immediately.
      // Preview starts CLOSED, exactly like a real embed does for a visitor — the panel only
      // opens when the launcher is clicked, never as a side effect of a config change.
      state.config = { agent_id: null, name: "Assistant", welcome_message: "Hi! How can I help you today?", suggested_prompts: [], theme: {} };
      build();
      window.addEventListener("message", previewListener);
      try {
        parent.postMessage({ type: "bf-preview-ready" }, "*");
      } catch (e) {}
      window.BotForge = api;
      return;
    }
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
