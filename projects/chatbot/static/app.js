/* Groq Chat — client-side app. History and settings stay in localStorage. */
(() => {
  "use strict";

  const STORAGE_KEY = "groqchat.conversations.v1";
  const SETTINGS_KEY = "groqchat.settings.v1";
  const DEFAULT_SYSTEM_PROMPT = "";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const els = {
    app: $("#app"),
    sidebar: $("#sidebar"),
    list: $("#conversation-list"),
    messages: $("#messages"),
    empty: $("#empty-state"),
    title: $("#chat-title"),
    subtitle: $("#chat-subtitle"),
    input: $("#input"),
    composer: $("#composer"),
    send: $("#send"),
    stop: $("#stop"),
    newChat: $("#new-chat"),
    deleteChat: $("#delete-chat"),
    exportChat: $("#export-chat"),
    menu: $("#menu-toggle"),
    status: $("#api-status"),
    statusText: $("#api-status-text"),
    dialog: $("#settings-dialog"),
    systemPrompt: $("#system-prompt"),
    temperature: $("#temperature"),
    temperatureValue: $("#temperature-value"),
    resetSettings: $("#reset-settings"),
    toast: $("#toast"),
  };

  let state = {
    conversations: loadJSON(STORAGE_KEY, []),
    activeId: null,
    settings: Object.assign(
      { systemPrompt: DEFAULT_SYSTEM_PROMPT, temperature: 0.7 },
      loadJSON(SETTINGS_KEY, {})
    ),
  };
  let controller = null;
  let toastTimer = null;

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.conversations));
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
  }

  function uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function activeConversation() {
    return state.conversations.find((c) => c.id === state.activeId) || null;
  }

  function toast(message) {
    els.toast.textContent = message;
    els.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2400);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  /* ---------- Markdown (safe subset, input is escaped first) ---------- */
  function renderInline(text) {
    return text
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>")
      .replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
      )
      .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
  }

  function renderMarkdown(source) {
    const codeBlocks = [];
    let text = escapeHtml(source || "");
    text = text.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (_match, lang, code) => {
      const index = codeBlocks.length;
      const cls = lang ? ` class="language-${escapeHtml(lang)}"` : "";
      codeBlocks.push(`<pre><code${cls}>${code.replace(/\n$/, "")}</code></pre>`);
      return `\u0000CODE${index}\u0000`;
    });

    const lines = text.split(/\r?\n/);
    let html = "";
    let paragraph = [];
    let listType = null;
    let quote = [];

    const flushParagraph = () => {
      if (!paragraph.length) return;
      html += `<p>${renderInline(paragraph.join(" "))}</p>`;
      paragraph = [];
    };
    const closeList = () => {
      if (!listType) return;
      html += `</${listType}>`;
      listType = null;
    };
    const flushQuote = () => {
      if (!quote.length) return;
      html += `<blockquote>${renderInline(quote.join(" "))}</blockquote>`;
      quote = [];
    };
    const flushAll = () => {
      flushParagraph();
      closeList();
      flushQuote();
    };

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      const trimmed = line.trim();

      const codeMatch = trimmed.match(/^\u0000CODE(\d+)\u0000$/);
      if (codeMatch) {
        flushAll();
        html += codeBlocks[Number(codeMatch[1])] || "";
        continue;
      }

      if (!trimmed) {
        flushAll();
        continue;
      }

      const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
      if (heading) {
        flushAll();
        const level = heading[1].length;
        html += `<h${level}>${renderInline(heading[2])}</h${level}>`;
        continue;
      }

      if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
        flushAll();
        html += "<hr />";
        continue;
      }

      if (trimmed.startsWith("&gt;")) {
        flushParagraph();
        closeList();
        quote.push(trimmed.replace(/^&gt;\s?/, ""));
        continue;
      }
      flushQuote();

      const bullet = trimmed.match(/^[-*+]\s+(.*)$/);
      if (bullet) {
        flushParagraph();
        if (listType !== "ul") {
          closeList();
          html += "<ul>";
          listType = "ul";
        }
        html += `<li>${renderInline(bullet[1])}</li>`;
        continue;
      }

      const ordered = trimmed.match(/^\d+[.)]\s+(.*)$/);
      if (ordered) {
        flushParagraph();
        if (listType !== "ol") {
          closeList();
          html += "<ol>";
          listType = "ol";
        }
        html += `<li>${renderInline(ordered[1])}</li>`;
        continue;
      }

      closeList();
      paragraph.push(trimmed);
    }

    flushAll();
    return html || "<p></p>";
  }

  /* ---------- Rendering ---------- */
  function renderConversationList() {
    els.list.innerHTML = "";
    if (!state.conversations.length) {
      els.list.innerHTML = '<div class="convo-empty">No conversations yet.</div>';
      return;
    }
    const sorted = [...state.conversations].sort((a, b) => b.updatedAt - a.updatedAt);
    for (const convo of sorted) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "convo-item" + (convo.id === state.activeId ? " active" : "");
      button.dataset.id = convo.id;
      const icon = document.createElement("span");
      icon.className = "convo-icon";
      icon.textContent = "◈";
      const title = document.createElement("span");
      title.className = "convo-title";
      title.textContent = convo.title || "New conversation";
      button.append(icon, title);
      button.addEventListener("click", () => {
        state.activeId = convo.id;
        render();
        els.sidebar.classList.remove("open");
      });
      els.list.appendChild(button);
    }
  }

  function messageElement(message, index) {
    const wrap = document.createElement("article");
    wrap.className = `msg ${message.role}`;
    wrap.dataset.index = String(index);

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = message.role === "user" ? "You" : "AI";

    const body = document.createElement("div");
    body.className = "msg-body";

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const name = document.createElement("strong");
    name.textContent = message.role === "user" ? "You" : "Groq";
    meta.appendChild(name);
    if (message.ts) {
      const time = document.createElement("span");
      time.textContent = new Date(message.ts).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      meta.appendChild(time);
    }

    const content = document.createElement("div");
    content.className = "msg-content";
    if (message.pending && !message.content) {
      content.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
    } else {
      content.innerHTML = renderMarkdown(message.content);
    }

    const actions = document.createElement("div");
    actions.className = "msg-actions";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "Copy";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(message.content || "");
        toast("Copied to clipboard");
      } catch {
        toast("Copy failed — select the text manually");
      }
    });
    actions.appendChild(copy);

    if (message.role === "assistant" && !message.pending && message.content) {
      const regen = document.createElement("button");
      regen.type = "button";
      regen.textContent = "Regenerate";
      regen.addEventListener("click", () => regenerate(index));
      actions.appendChild(regen);
    }

    body.append(meta, content, actions);
    wrap.append(avatar, body);
    return wrap;
  }

  function renderMessages() {
    const convo = activeConversation();
    els.messages.innerHTML = "";
    if (!convo || !convo.messages.length) {
      els.messages.appendChild(els.empty);
      els.empty.hidden = false;
      return;
    }
    els.empty.hidden = true;
    const fragment = document.createDocumentFragment();
    convo.messages.forEach((message, index) => fragment.appendChild(messageElement(message, index)));
    els.messages.appendChild(fragment);
    scrollToBottom();
  }

  function render() {
    const convo = activeConversation();
    renderConversationList();
    renderMessages();
    els.title.textContent = convo ? convo.title : "New conversation";
    els.subtitle.textContent = convo
      ? `${convo.messages.filter((m) => m.role === "user").length} messages · ${els.subtitle.dataset.model || "Groq"}`
      : "Powered by Groq";
    els.deleteChat.disabled = !convo;
    els.exportChat.disabled = !convo || !convo.messages.length;
  }

  function scrollToBottom(force = false) {
    const nearBottom =
      els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight < 160;
    if (force || nearBottom) {
      els.messages.scrollTop = els.messages.scrollHeight;
    }
  }

  /* ---------- Conversation actions ---------- */
  function newChat() {
    const convo = {
      id: uid(),
      title: "New conversation",
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    state.conversations.push(convo);
    state.activeId = convo.id;
    save();
    render();
    els.input.value = "";
    autoResize();
    els.input.focus();
  }

  function ensureConversation() {
    if (!activeConversation()) newChat();
    return activeConversation();
  }

  async function deleteChat() {
    const convo = activeConversation();
    if (!convo) return;
    if (convo.messages.length && !confirm("Delete this conversation?")) return;
    state.conversations = state.conversations.filter((c) => c.id !== convo.id);
    state.activeId = state.conversations[0]?.id || null;
    save();
    render();
    toast("Conversation deleted");
  }

  function exportChat() {
    const convo = activeConversation();
    if (!convo || !convo.messages.length) return;
    const lines = [`# ${convo.title}`, "", `_Exported ${new Date().toLocaleString()}_`, ""];
    for (const message of convo.messages) {
      lines.push(`## ${message.role === "user" ? "You" : "Groq"}`, "", message.content, "");
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(convo.title || "conversation").replace(/[^\w\- ]+/g, "").trim() || "conversation"}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /* ---------- Streaming ---------- */
  function setBusy(busy) {
    els.send.hidden = busy;
    els.stop.hidden = !busy;
    els.input.disabled = busy;
  }

  function parseSSEChunk(chunk) {
    const line = chunk.split("\n").find((part) => part.startsWith("data: "));
    if (!line) return null;
    const payload = line.slice(6);
    if (payload === "[DONE]") return { done: true };
    try {
      return JSON.parse(payload);
    } catch {
      return null;
    }
  }

  async function streamReply(convo) {
    controller = new AbortController();
    const assistant = { role: "assistant", content: "", ts: Date.now(), pending: true };
    convo.messages.push(assistant);
    save();
    render();
    setBusy(true);

    const history = convo.messages
      .filter((m) => !m.pending && m.content)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          messages: history,
          system_prompt: state.settings.systemPrompt || undefined,
          temperature: Number(state.settings.temperature),
          stream: true,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Request failed (${response.status})`);
      }
      if (!response.body) throw new Error("Streaming is not supported by this browser.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const event = parseSSEChunk(raw);
          if (!event) continue;
          if (event.done) break;
          if (event.error) throw new Error(event.error);
          if (event.delta) {
            assistant.content += event.delta;
            updateAssistantNode(convo, assistant);
          }
        }
      }
    } catch (error) {
      if (error.name === "AbortError") {
        if (!assistant.content) assistant.content = "_Generation stopped._";
      } else {
        showError(error.message || "Something went wrong.");
        if (!assistant.content) convo.messages.pop();
        else assistant.content += `\n\n_Error: ${error.message}_`;
      }
    } finally {
      assistant.pending = false;
      controller = null;
      setBusy(false);
      convo.updatedAt = Date.now();
      save();
      render();
      els.input.focus();
    }
  }

  function updateAssistantNode(convo, assistant) {
    const index = convo.messages.indexOf(assistant);
    const node = els.messages.querySelector(`.msg[data-index="${index}"] .msg-content`);
    if (node) {
      node.innerHTML = renderMarkdown(assistant.content);
      scrollToBottom();
    }
  }

  async function sendMessage(text) {
    const content = text.trim();
    if (!content || controller) return;
    const convo = ensureConversation();
    convo.messages.push({ role: "user", content, ts: Date.now() });
    if (convo.messages.filter((m) => m.role === "user").length === 1) {
      convo.title = content.slice(0, 52) + (content.length > 52 ? "…" : "");
    }
    convo.updatedAt = Date.now();
    save();
    render();
    els.input.value = "";
    autoResize();
    await streamReply(convo);
  }

  async function regenerate(index) {
    const convo = activeConversation();
    if (!convo || controller) return;
    const target = convo.messages[index];
    if (!target || target.role !== "assistant") return;
    convo.messages.splice(index, 1);
    save();
    await streamReply(convo);
  }

  function showError(message) {
    const box = document.createElement("div");
    box.className = "error-box";
    box.textContent = message;
    els.messages.appendChild(box);
    scrollToBottom(true);
  }

  /* ---------- Composer ---------- */
  function autoResize() {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 190) + "px";
  }

  els.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(els.input.value);
  });

  els.input.addEventListener("input", autoResize);
  els.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      els.composer.requestSubmit();
    }
  });

  els.stop.addEventListener("click", () => {
    if (controller) controller.abort();
  });

  els.newChat.addEventListener("click", newChat);
  els.deleteChat.addEventListener("click", deleteChat);
  els.exportChat.addEventListener("click", exportChat);

  els.menu.addEventListener("click", () => els.sidebar.classList.toggle("open"));

  $$("#empty-state [data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      els.input.value = button.dataset.prompt;
      autoResize();
      els.input.focus();
    });
  });

  /* ---------- Settings ---------- */
  function openSettings() {
    els.systemPrompt.value = state.settings.systemPrompt || "";
    els.temperature.value = state.settings.temperature;
    els.temperatureValue.textContent = Number(state.settings.temperature).toFixed(1);
    els.dialog.showModal();
  }

  els.temperature.addEventListener("input", () => {
    els.temperatureValue.textContent = Number(els.temperature.value).toFixed(1);
  });

  $("#open-settings").addEventListener("click", openSettings);
  $("#save-settings").addEventListener("click", (event) => {
    event.preventDefault();
    state.settings.systemPrompt = els.systemPrompt.value.trim();
    state.settings.temperature = Number(els.temperature.value);
    save();
    els.dialog.close();
    toast("Settings saved");
  });
  els.resetSettings.addEventListener("click", () => {
    state.settings = { systemPrompt: DEFAULT_SYSTEM_PROMPT, temperature: 0.7 };
    save();
    openSettings();
    toast("Settings reset");
  });

  /* ---------- Health ---------- */
  async function checkHealth() {
    try {
      const response = await fetch("/api/health");
      const data = await response.json();
      const good = data.configured;
      els.status.classList.toggle("online", good);
      els.status.classList.toggle("offline", !good);
      els.statusText.textContent = good ? `Online · ${data.model}` : "GROQ_API_KEY missing";
      els.subtitle.dataset.model = data.model;
      if (!good) els.subtitle.textContent = "Add GROQ_API_KEY to .env";
    } catch {
      els.status.classList.remove("online");
      els.status.classList.add("offline");
      els.statusText.textContent = "Server unreachable";
    }
  }

  /* ---------- Boot ---------- */
  state.conversations = state.conversations.filter((c) => c && c.id && Array.isArray(c.messages));
  if (state.conversations.length) {
    state.conversations.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    state.activeId = state.conversations[0].id;
  }
  render();
  checkHealth();
  setInterval(checkHealth, 60000);
  els.input.focus();

  // Expose a couple of helpers for debugging without leaking state into globals.
  window.__groqchat = {
    newChat,
    clear: () => {
      state.conversations = [];
      state.activeId = null;
      save();
      render();
    },
  };
})();
