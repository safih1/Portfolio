(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  // Mobile sidebar
  const sidebar = $("#sidebar");
  const menu = $("#menu-toggle");
  if (menu && sidebar) {
    menu.addEventListener("click", () => sidebar.classList.toggle("open"));
    document.addEventListener("click", (event) => {
      if (!sidebar.classList.contains("open")) return;
      if (sidebar.contains(event.target) || menu.contains(event.target)) return;
      sidebar.classList.remove("open");
    });
  }

  // Confirm destructive forms
  $$("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm || "Are you sure?")) {
        event.preventDefault();
      }
    });
  });

  // Copy buttons
  $$("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const text = target.textContent || "";
      try {
        await navigator.clipboard.writeText(text);
        const original = button.textContent;
        button.textContent = "Copied";
        setTimeout(() => (button.textContent = original), 1600);
      } catch {
        window.prompt("Copy this text:", text);
      }
    });
  });

  // Lead assistant (compact Groq chat)
  const chat = $("#lead-chat");
  if (chat) {
    const log = $("#chat-log", chat);
    const form = $("#chat-form", chat);
    const input = $("#chat-input", chat);
    const send = $("#chat-send", chat);
    const history = [];
    let chatBusy = false;

    const scrollLog = () => {
      log.scrollTop = log.scrollHeight;
    };

    const addBubble = (role, text) => {
      const bubble = document.createElement("div");
      bubble.className = `chat-bubble ${role}`;
      bubble.textContent = text;
      log.appendChild(bubble);
      scrollLog();
      return bubble;
    };

    const setChatBusy = (state) => {
      chatBusy = state;
      if (send) send.disabled = state;
      if (input) input.disabled = state;
      $$("[data-chat-prompt]", chat).forEach((chip) => {
        chip.disabled = state;
      });
    };

    async function askLead(text) {
      const question = (text || "").trim();
      if (!question || chatBusy) return;

      setChatBusy(true);
      addBubble("user", question);
      history.push({ role: "user", content: question });
      if (input) {
        input.value = "";
        input.style.height = "auto";
      }

      const pending = addBubble("assistant", "Thinking…");
      pending.classList.add("pending");
      try {
        const response = await fetch(`/leads/${chat.dataset.leadId}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: history.slice(-20) }),
        });
        const data = await response.json().catch(() => ({}));
        pending.remove();
        if (!response.ok) {
          throw new Error(data.error || "The assistant is unavailable.");
        }
        addBubble("assistant", data.reply);
        history.push({ role: "assistant", content: data.reply });
      } catch (error) {
        pending.remove();
        addBubble("assistant", error.message || "The assistant is unavailable.");
      } finally {
        setChatBusy(false);
        if (input) input.focus();
      }
    }

    if (form) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        askLead(input.value);
      });
    }

    if (input) {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (form) form.requestSubmit();
        }
      });
    }

    $$("[data-chat-prompt]", chat).forEach((chip) => {
      chip.addEventListener("click", () => askLead(chip.dataset.chatPrompt));
    });
  }

  // Dismiss flash messages
  $$(".flash").forEach((flash) => {
    setTimeout(() => {
      flash.style.transition = "opacity 220ms ease, transform 220ms ease";
      flash.style.opacity = "0";
      flash.style.transform = "translateY(-4px)";
      setTimeout(() => flash.remove(), 240);
    }, 6500);
  });

  // Highlight the selected CSV file
  const fileInput = $('.dropzone input[type="file"]');
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const title = $(".dropzone-title", fileInput.closest(".dropzone"));
      if (title && fileInput.files.length) {
        title.textContent = fileInput.files[0].name;
      }
    });
  }

  // API health indicator
  const status = $("#health-status");
  async function checkHealth() {
    if (!status) return;
    try {
      const response = await fetch("/api/health");
      const data = await response.json();
      status.classList.toggle("online", data.status === "ok");
      status.classList.toggle("offline", data.status !== "ok");
      status.title = `Leads: ${data.leads} · Groq: ${data.groq ? "on" : "off"} · Google: ${data.google_places ? "on" : "off"} · Facebook: ${data.facebook ? "on" : "off"}`;
    } catch {
      status.classList.remove("online");
      status.classList.add("offline");
      status.title = "Server unreachable";
    }
  }
  checkHealth();
  setInterval(checkHealth, 60000);

  // Grow textareas as the user types (but keep manual resize available).
  $$("textarea").forEach((area) => {
    area.addEventListener("input", () => {
      if (area.dataset.fixedHeight) return;
      area.style.height = "auto";
      area.style.height = Math.min(area.scrollHeight, 320) + "px";
    });
  });
})();
