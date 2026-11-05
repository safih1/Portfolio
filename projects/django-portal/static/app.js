(() => {
  "use strict";

  const sidebar = document.getElementById("sidebar");
  const toggle = document.getElementById("menu-toggle");

  if (sidebar && toggle) {
    toggle.addEventListener("click", () => {
      const open = sidebar.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });

    document.addEventListener("click", (event) => {
      if (
        window.innerWidth <= 860 &&
        sidebar.classList.contains("open") &&
        !sidebar.contains(event.target) &&
        !toggle.contains(event.target)
      ) {
        sidebar.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && sidebar.classList.contains("open")) {
        sidebar.classList.remove("open");
        toggle.focus();
      }
    });
  }

  const range = document.getElementById("progress-range");
  const output = document.getElementById("progress-value");

  if (range && output) {
    const sync = () => {
      output.textContent = `${range.value}%`;
    };
    range.addEventListener("input", sync);
    sync();
  }

  const flashes = document.querySelectorAll(".flash");
  if (flashes.length) {
    window.setTimeout(() => {
      flashes.forEach((flash) => {
        flash.classList.add("is-hiding");
        window.setTimeout(() => flash.remove(), 320);
      });
    }, 4200);
  }
})();
