(function () {
  const lightbox = document.querySelector("[data-lightbox]");
  if (!lightbox) return;

  const imageEl = lightbox.querySelector("[data-lightbox-image]");
  const captionEl = lightbox.querySelector("[data-lightbox-caption]");
  const closeBtn = lightbox.querySelector("[data-lightbox-close]");
  const prevBtn = lightbox.querySelector("[data-lightbox-prev]");
  const nextBtn = lightbox.querySelector("[data-lightbox-next]");
  const buttons = Array.from(document.querySelectorAll("[data-lightbox-src]"));
  let index = 0;

  function show(i) {
    if (!buttons.length) return;
    index = (i + buttons.length) % buttons.length;
    const btn = buttons[index];
    imageEl.src = btn.getAttribute("data-lightbox-src") || "";
    const alt = btn.getAttribute("data-lightbox-alt") || "";
    imageEl.alt = alt;
    if (captionEl) captionEl.textContent = alt;
    lightbox.hidden = false;
    document.body.classList.add("lightbox-open");
    closeBtn && closeBtn.focus();
    const many = buttons.length > 1;
    if (prevBtn) prevBtn.hidden = !many;
    if (nextBtn) nextBtn.hidden = !many;
  }

  function hide() {
    lightbox.hidden = true;
    document.body.classList.remove("lightbox-open");
    imageEl.src = "";
  }

  buttons.forEach((btn, i) => {
    btn.addEventListener("click", () => show(i));
  });
  closeBtn && closeBtn.addEventListener("click", hide);
  prevBtn && prevBtn.addEventListener("click", () => show(index - 1));
  nextBtn && nextBtn.addEventListener("click", () => show(index + 1));
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) hide();
  });
  document.addEventListener("keydown", (event) => {
    if (lightbox.hidden) return;
    if (event.key === "Escape") hide();
    if (event.key === "ArrowLeft") show(index - 1);
    if (event.key === "ArrowRight") show(index + 1);
  });
})();
