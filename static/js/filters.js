(function () {
  const root = document.querySelector("[data-headline-list]");
  const cards = root ? Array.from(root.querySelectorAll("[data-card]")) : [];
  const buttons = Array.from(document.querySelectorAll("[data-filter]"));
  const classButtons = Array.from(document.querySelectorAll("[data-class-filter]"));
  const sourceSelect = document.querySelector("[data-source-filter]");
  const countEl = document.querySelector("[data-result-count]");
  let category = "all";
  let source = "all";
  let dirtClass = "all";

  function apply() {
    if (!cards.length) return;
    let shown = 0;
    cards.forEach(function (card) {
      const cat = card.getAttribute("data-category") || "";
      const src = card.getAttribute("data-source") || "";
      const tags = (card.getAttribute("data-tags") || "").split(/\s+/);
      const catOk =
        category === "all" ||
        cat === category ||
        (category === "engines" && tags.indexOf("engines") !== -1);
      const srcOk = source === "all" || src === source;
      const classOk = dirtClass === "all" || tags.indexOf(dirtClass) !== -1;
      const on = catOk && srcOk && classOk;
      card.classList.toggle("is-hidden", !on);
      if (on) shown += 1;
    });
    if (countEl) {
      countEl.textContent = shown + " headline" + (shown === 1 ? "" : "s");
    }
  }

  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      category = btn.getAttribute("data-filter") || "all";
      buttons.forEach(function (b) {
        const on = b === btn;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      apply();
    });
  });

  classButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      dirtClass = btn.getAttribute("data-class-filter") || "all";
      classButtons.forEach(function (b) {
        const on = b === btn;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      apply();
    });
  });

  if (sourceSelect) {
    sourceSelect.addEventListener("change", function () {
      source = sourceSelect.value || "all";
      apply();
    });
  }

  apply();

  // Lazy YouTube embed — nothing loads from YouTube until a thumbnail is clicked.
  document.addEventListener("click", function (event) {
    const liveBtn = event.target.closest("[data-live-channel]");
    if (liveBtn) {
      event.preventDefault();
      const channelId = liveBtn.getAttribute("data-live-channel") || "";
      // Standard YouTube channel IDs are 24 characters starting with UC.
      if (!/^UC[A-Za-z0-9_-]{22}$/.test(channelId)) return;
      const wrap = liveBtn.closest(".thumb-wrap") || liveBtn.parentElement;
      const iframe = document.createElement("iframe");
      iframe.src =
        "https://www.youtube-nocookie.com/embed/live_stream?channel=" +
        encodeURIComponent(channelId);
      iframe.title = "YouTube live stream";
      iframe.allow =
        "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
      iframe.allowFullscreen = true;
      iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      wrap.innerHTML = "";
      wrap.appendChild(iframe);
      return;
    }
    const btn = event.target.closest("[data-video]");
    if (!btn) return;
    event.preventDefault();
    const id = btn.getAttribute("data-video");
    if (!id || !/^[A-Za-z0-9_-]{6,}$/.test(id)) return;
    const wrap = btn.closest(".thumb-wrap") || btn.parentElement;
    const iframe = document.createElement("iframe");
    iframe.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) + "?autoplay=1";
    iframe.title = "YouTube video";
    iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
    iframe.allowFullscreen = true;
    iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    wrap.innerHTML = "";
    wrap.appendChild(iframe);
  });
})();
