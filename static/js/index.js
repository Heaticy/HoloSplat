document.documentElement.classList.add("js");

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Copy buttons: data-copy names the element whose text is copied.
for (const button of document.querySelectorAll("button[data-copy]")) {
  button.addEventListener("click", async () => {
    const text = document.getElementById(button.dataset.copy).textContent;
    await navigator.clipboard.writeText(text);
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy"; }, 1500);
  });
}

// Looping clips play only while on screen. The slider's hidden source video is driven by the slider instead.
function isShown(video) {
  return !video.closest("[hidden]");
}
const onScreen = new Set();
// Preloaded loops (the first screen) start only once the browser expects to play through without stalling, so a slow
// connection shows the poster instead of a stuttering first pass; lazily loaded clips start loading by playing.
function start(video) {
  if (video.preload !== "auto" || video.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA) {
    video.play().catch(() => {});
    return;
  }
  video.addEventListener("canplaythrough", () => {
    if (onScreen.has(video) && isShown(video)) video.play().catch(() => {});
  }, { once: true });
}
const playObserver = new IntersectionObserver((entries) => {
  for (const { target, isIntersecting } of entries) {
    if (isIntersecting) onScreen.add(target); else onScreen.delete(target);
    if (isIntersecting && isShown(target)) start(target);
    else target.pause();
  }
}, { threshold: 0.25 });
for (const video of document.querySelectorAll("video[loop]:not(.slider-source)")) {
  video.removeAttribute("autoplay");
  playObserver.observe(video);
}

// Tabs: [data-tabs] holds role=tab buttons whose data-panel names a role=tabpanel.
for (const group of document.querySelectorAll("[data-tabs]")) {
  const tabs = [...group.querySelectorAll(":scope [role=tab]")];
  tabs.forEach((tab) => tab.addEventListener("click", () => {
    for (const other of tabs) {
      const selected = other === tab;
      other.setAttribute("aria-selected", String(selected));
      const panel = document.getElementById(other.dataset.panel);
      panel.hidden = !selected;
      for (const video of panel.querySelectorAll("video")) {
        if (selected) {
          video.preload = "auto";
          video.currentTime = 0;
          if (onScreen.has(video)) video.play().catch(() => {});
        } else {
          video.pause();
        }
      }
    }
  }));
}

// Scene switches swap the source of the panel's video.
for (const row of document.querySelectorAll("[data-scenes]")) {
  const video = row.parentElement.querySelector("video");
  const buttons = [...row.querySelectorAll("button")];
  buttons.forEach((button) => button.addEventListener("click", () => {
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    video.poster = button.dataset.poster;
    video.querySelector("source").src = button.dataset.src;
    video.load();
    // the slider's video is driven by the slider, which is on screen when its buttons are clicked
    if (onScreen.has(video) || video.classList.contains("slider-source")) video.play().catch(() => {});
  }));
}

// Before/after slider: the source video is the two halves side by side; the canvas shows the left half
// left of the divider and the right half right of it.
for (const figure of document.querySelectorAll("[data-slider]")) {
  const video = figure.querySelector("video");
  const canvas = figure.querySelector("canvas");
  const range = figure.querySelector("input[type=range]");
  const context = canvas.getContext("2d");
  let split = 0.5;
  let running = false;

  function draw() {
    const w = video.videoWidth / 2;
    const h = video.videoHeight;
    if (w && h) {
      if (canvas.width !== w) { canvas.width = w; canvas.height = h; }
      const x = Math.round(w * split);
      if (x > 0) context.drawImage(video, 0, 0, x, h, 0, 0, x, h);
      if (x < w) context.drawImage(video, w + x, 0, w - x, h, x, 0, w - x, h);
      context.fillStyle = "#fff";
      context.fillRect(x - 1.5, 0, 3, h);
      context.beginPath();
      context.arc(x, h / 2, 16, 0, 2 * Math.PI);
      context.fillStyle = "rgba(219, 39, 119, .95)";
      context.fill();
      context.fillStyle = "#fff";
      context.font = "bold 16px sans-serif";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText("\u2039 \u203a", x, h / 2 + 1);
    }
    if (running) requestAnimationFrame(draw);
  }
  function setFromPointer(event) {
    const box = canvas.getBoundingClientRect();
    split = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    range.value = String(Math.round(split * 100));
    if (!running) draw();
  }
  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    setFromPointer(event);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (canvas.hasPointerCapture(event.pointerId)) setFromPointer(event);
  });
  range.addEventListener("input", () => { split = range.value / 100; if (!running) draw(); });
  video.addEventListener("loadeddata", draw);

  new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      video.play().catch(() => {});
      if (!running) { running = true; requestAnimationFrame(draw); }
    } else {
      video.pause();
      running = false;
    }
  }, { threshold: 0.2 }).observe(canvas);
}

// Reveal on scroll, and count the key numbers up once.
const revealObserver = new IntersectionObserver((entries) => {
  for (const { target, isIntersecting } of entries) {
    if (!isIntersecting) continue;
    target.classList.add("is-visible");
    revealObserver.unobserve(target);
    for (const count of target.querySelectorAll(".count")) countUp(count);
  }
}, { threshold: 0.12 });
document.querySelectorAll(".reveal").forEach((el) => revealObserver.observe(el));

function countUp(el) {
  const to = Number(el.dataset.to);
  const digits = Number(el.dataset.digits);
  if (reduceMotion) return;
  const start = performance.now();
  const duration = 1100;
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    el.textContent = (to * (1 - (1 - t) ** 3)).toFixed(digits);
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// Top bar appears below the title and marks the section in view.
const topbar = document.querySelector(".topbar");
const links = new Map([...topbar.querySelectorAll(".topbar-links a")].map((a) => [a.getAttribute("href").slice(1), a]));
new IntersectionObserver(([entry]) => {
  topbar.classList.toggle("is-shown", !entry.isIntersecting);
}).observe(document.querySelector(".hero .title"));
const sectionObserver = new IntersectionObserver((entries) => {
  for (const { target, isIntersecting } of entries) {
    if (isIntersecting) links.forEach((a, id) => a.classList.toggle("is-active", id === target.id));
  }
}, { rootMargin: "-45% 0px -50% 0px" });
links.forEach((_, id) => { const s = document.getElementById(id); if (s) sectionObserver.observe(s); });
