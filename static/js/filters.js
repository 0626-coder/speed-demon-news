(function () {
  const shell = document.querySelector("[data-news-shell]");
  const root = document.querySelector("[data-headline-list]");
  const cards = root ? Array.from(root.querySelectorAll("[data-card]")) : [];
  const catLinks = Array.from(document.querySelectorAll("[data-filter]"));
  const classButtons = Array.from(document.querySelectorAll("[data-class-filter]"));
  const typeButtons = Array.from(document.querySelectorAll("[data-type-filter]"));
  const dateButtons = Array.from(document.querySelectorAll("[data-date-filter]"));
  const sourceSelect = document.querySelector("[data-source-filter]");
  const searchInput = document.querySelector("[data-search-filter]");
  const enginesInput = document.querySelector("[data-engines-filter]");
  const resetBtn = document.querySelector("[data-filter-reset]");
  const countEl = document.querySelector("[data-result-count]");
  const emptyEl = document.querySelector("[data-filter-empty]");
  const featured = Array.from(document.querySelectorAll("[data-featured-block]"));
  const dirtGroup = document.querySelector("[data-dirt-group]");
  const catPageLink = document.querySelector("[data-category-page-link]");
  const catPageName = document.querySelector("[data-category-page-name]");
  const pageKind = shell ? shell.getAttribute("data-page-kind") || "" : "";
  const pageCategory = shell ? shell.getAttribute("data-page-category") || "all" : "all";
  const inPageCategories = pageKind === "home";

  let category = pageCategory || "all";
  let source = "all";
  let dirtClass = "all";
  let type = "all";
  let dateRange = "all";
  let engines = false;
  let query = "";

  function todayCT() {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Chicago",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  }

  function cardDateCT(iso) {
    if (!iso) return null;
    if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Chicago",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(d);
  }

  function daysBetween(fromStr, toStr) {
    const [fy, fm, fd] = fromStr.split("-").map(Number);
    const [ty, tm, td] = toStr.split("-").map(Number);
    const from = Date.UTC(fy, fm - 1, fd);
    const to = Date.UTC(ty, tm - 1, td);
    return Math.round((to - from) / 86400000);
  }

  function dateOk(iso) {
    if (dateRange === "all") return true;
    const day = cardDateCT(iso);
    if (!day) return false;
    const today = todayCT();
    if (dateRange === "today") return day === today;
    if (dateRange === "week") {
      const delta = daysBetween(day, today);
      return delta >= 0 && delta <= 6;
    }
    return true;
  }

  function typeOk(card) {
    if (type === "all") return true;
    const cardType = card.getAttribute("data-type") || "article";
    const isOriginal = card.getAttribute("data-original") === "true";
    if (type === "video") return cardType === "video";
    if (type === "article") return cardType !== "video";
    if (type === "original") return isOriginal;
    return true;
  }

  function setPressed(buttons, current, attr) {
    buttons.forEach(function (b) {
      const on = (b.getAttribute(attr) || "all") === current;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function setActiveCat(next) {
    category = next || "all";
    catLinks.forEach(function (link) {
      const on = (link.getAttribute("data-filter") || "all") === category;
      link.classList.toggle("is-active", on);
      if (on) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    if (dirtGroup) {
      const showDirt = category === "dirt" || pageCategory === "dirt";
      dirtGroup.classList.toggle("is-hidden", !showDirt);
      if (!showDirt) {
        dirtClass = "all";
        setPressed(classButtons, "all", "data-class-filter");
      }
    }
  }

  function filtersActive() {
    return (
      (inPageCategories && category !== "all") ||
      source !== "all" ||
      dirtClass !== "all" ||
      type !== "all" ||
      dateRange !== "all" ||
      engines ||
      query !== ""
    );
  }

  function apply() {
    if (!cards.length) {
      updateChrome(0);
      return;
    }
    let shown = 0;
    cards.forEach(function (card) {
      const cat = card.getAttribute("data-category") || "";
      const src = card.getAttribute("data-source") || "";
      const tags = (card.getAttribute("data-tags") || "").split(/\s+/);
      const catOk = category === "all" || cat === category;
      const srcOk = source === "all" || src === source;
      const classOk = dirtClass === "all" || tags.indexOf(dirtClass) !== -1;
      const enginesOk = !engines || tags.indexOf("engines") !== -1;
      const queryOk =
        !query ||
        (card.textContent || "").toLowerCase().indexOf(query) !== -1;
      const on = catOk && srcOk && classOk && enginesOk && typeOk(card) && dateOk(card.getAttribute("data-date")) && queryOk;
      card.classList.toggle("is-hidden", !on);
      if (on) shown += 1;
    });
    updateChrome(shown);
  }

  function updateChrome(shown) {
    if (countEl) {
      countEl.textContent = shown + " headline" + (shown === 1 ? "" : "s");
    }
    if (emptyEl) {
      emptyEl.classList.toggle("is-hidden", shown !== 0);
    }
    const active = filtersActive();
    featured.forEach(function (block) {
      block.classList.toggle("is-hidden", active);
    });
    if (resetBtn) resetBtn.classList.toggle("is-hidden", !active);
    const countBadge = document.querySelector("[data-active-filter-count]");
    if (countBadge) {
      let n = 0;
      if (inPageCategories && category !== "all") n += 1;
      if (source !== "all") n += 1;
      if (dirtClass !== "all") n += 1;
      if (type !== "all") n += 1;
      if (dateRange !== "all") n += 1;
      if (engines) n += 1;
      if (query) n += 1;
      countBadge.textContent = n ? String(n) : "";
      countBadge.classList.toggle("is-hidden", n === 0);
    }
    if (catPageLink && inPageCategories) {
      const activeLink = catLinks.find(function (l) {
        return (l.getAttribute("data-filter") || "all") === category && category !== "all";
      });
      if (activeLink) {
        const name = (activeLink.textContent || "").trim();
        const href = activeLink.getAttribute("href") || "";
        const anchor = catPageLink.querySelector("a");
        if (catPageName) catPageName.textContent = name;
        if (anchor) anchor.setAttribute("href", href);
        catPageLink.classList.remove("is-hidden");
      } else {
        catPageLink.classList.add("is-hidden");
      }
    }
  }

  function resetFilters() {
    if (inPageCategories) setActiveCat("all");
    source = "all";
    dirtClass = "all";
    type = "all";
    dateRange = "all";
    engines = false;
    query = "";
    if (sourceSelect) sourceSelect.value = "all";
    if (searchInput) searchInput.value = "";
    if (enginesInput) enginesInput.checked = false;
    setPressed(classButtons, "all", "data-class-filter");
    setPressed(typeButtons, "all", "data-type-filter");
    setPressed(dateButtons, "all", "data-date-filter");
    apply();
  }

  catLinks.forEach(function (link) {
    link.addEventListener("click", function (event) {
      if (!inPageCategories) return;
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (event.button !== 0) return;
      event.preventDefault();
      setActiveCat(link.getAttribute("data-filter") || "all");
      apply();
      closeDrawer();
    });
  });

  classButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      dirtClass = btn.getAttribute("data-class-filter") || "all";
      setPressed(classButtons, dirtClass, "data-class-filter");
      apply();
    });
  });

  typeButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      type = btn.getAttribute("data-type-filter") || "all";
      setPressed(typeButtons, type, "data-type-filter");
      apply();
    });
  });

  dateButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      dateRange = btn.getAttribute("data-date-filter") || "all";
      setPressed(dateButtons, dateRange, "data-date-filter");
      apply();
    });
  });

  if (sourceSelect) {
    sourceSelect.addEventListener("change", function () {
      source = sourceSelect.value || "all";
      apply();
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      query = (searchInput.value || "").trim().toLowerCase();
      apply();
    });
  }

  if (enginesInput) {
    enginesInput.addEventListener("change", function () {
      engines = !!enginesInput.checked;
      apply();
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener("click", resetFilters);
  }

  // Mobile filter drawer
  const toggle = document.querySelector("[data-filters-toggle]");
  const sidebar = document.getElementById("news-filters");
  const backdrop = document.querySelector("[data-filters-backdrop]");
  const closeBtn = document.querySelector("[data-filters-close]");
  let lastFocus = null;

  function openDrawer() {
    if (!sidebar || !toggle) return;
    lastFocus = document.activeElement;
    sidebar.classList.add("is-open");
    if (backdrop) backdrop.hidden = false;
    document.body.classList.add("filters-open");
    toggle.setAttribute("aria-expanded", "true");
    if (closeBtn) closeBtn.focus();
  }

  function closeDrawer() {
    if (!sidebar || !toggle) return;
    if (!sidebar.classList.contains("is-open") && !document.body.classList.contains("filters-open")) return;
    sidebar.classList.remove("is-open");
    if (backdrop) backdrop.hidden = true;
    document.body.classList.remove("filters-open");
    toggle.setAttribute("aria-expanded", "false");
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }

  if (toggle) toggle.addEventListener("click", function () {
    if (sidebar && sidebar.classList.contains("is-open")) closeDrawer();
    else openDrawer();
  });
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeDrawer();
  });

  if (shell) {
    setActiveCat(category);
    apply();
  }

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
