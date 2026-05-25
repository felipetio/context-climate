/* =====================================================================
   Context Climate — login page customizer
   Loaded via .chainlit/config.toml → custom_js = "/public/login-customize.js"
   ---------------------------------------------------------------------
   Chainlit's login layout is rendered by its React bundle and doesn't
   expose hooks for our copy. This script watches for the login DOM,
   injects our Context Climate brand elements, and tags the route so
   custom.css can style only the login screen.
   ===================================================================== */
(function () {
  "use strict";

  const STAGED = "data-cc-login-staged";
  const PULL_QUOTE_HTML =
    'Climate<br>data,<br><em>in plain</em><br>language.';
  const PULL_SUB_HTML =
    'With <strong>verified data</strong> — every claim grounded in the World Bank Data360, every figure citable.';
  const HEAD_TITLE   = "An investigation starts with a question.";
  const HEAD_SUB     = "Sign in to query World Bank Data360 in plain language. Every figure ships with a verifiable source.";
  const SUBMIT_LABEL = "Open the dossier";
  const BYLINE_HTML  =
    'A research tool by <strong>InfoAmazonia</strong> <span class="dot">·</span> World Bank Data360';

  function isLoginDom(root = document) {
    return !!root.querySelector('input[type="password"]');
  }

  function buildBrandLockup() {
    const wrap = document.createElement("div");
    wrap.className = "cc-brand-lockup";
    wrap.innerHTML =
      '<svg class="cc-brand-mark" viewBox="0 0 100 100" aria-hidden="true">' +
      '<path d="M50 8 C 72 18, 80 38, 78 56 C 76 76, 60 90, 50 90 C 40 90, 24 76, 22 56 C 20 38, 28 18, 50 8 Z" fill="#80BC36"/>' +
      '<path d="M62 18 C 84 28, 92 48, 90 66 C 88 86, 72 96, 62 92 C 58 88, 62 84, 70 78 C 78 70, 80 56, 76 44 C 72 32, 60 24, 62 18 Z" fill="#1A3A33"/>' +
      "</svg>" +
      '<span class="cc-brand-name">Context Climate</span>';
    return wrap;
  }

  function buildHeroOverlay() {
    const overlay = document.createElement("div");
    overlay.className = "cc-hero-overlay";
    overlay.innerHTML =
      '<div class="cc-hero-tag">Investigative research · climate &amp; development data</div>' +
      '<div class="cc-pull">' + PULL_QUOTE_HTML + "</div>" +
      '<div class="cc-pull-sub">' + PULL_SUB_HTML + "</div>" +
      '<div class="cc-hero-foot">' +
        '<div class="cc-credit">Context Climate <span class="b">v0.4</span></div>' +
        '<div class="cc-credit">Floresta Amazônica · BR</div>' +
      "</div>";
    return overlay;
  }

  function buildBottomByline() {
    const el = document.createElement("div");
    el.className = "cc-form-foot";
    el.innerHTML = '<div class="cc-by">' + BYLINE_HTML + "</div>";
    return el;
  }

  function stageLoginPage() {
    if (!isLoginDom()) return false;
    if (document.body.hasAttribute(STAGED)) return true;

    const passwordInput = document.querySelector('input[type="password"]');
    if (!passwordInput) return false;

    // Mark body so custom.css can scope login-only rules without :has().
    document.body.setAttribute(STAGED, "true");

    // Find the 2-col grid + its two children (Chainlit's login layout).
    const grid =
      document.querySelector(".grid.min-h-svh") ||
      passwordInput.closest(".grid");
    if (!grid) return true;

    const cols = Array.from(grid.children).filter(
      (n) => n.nodeType === 1 && n.tagName === "DIV"
    );
    if (cols.length < 1) return true;

    const formCol = cols[0];
    const heroCol = cols[1] || null;
    formCol.classList.add("cc-form-col");
    if (heroCol) heroCol.classList.add("cc-hero-col");

    // ---- LEFT: replace wordmark + headline + subhead + submit label ----
    // 1) Wordmark — hide the original logo img and inject ours.
    const wordmarkImg = formCol.querySelector('img.logo, img[alt="logo"], img[src*="/logo"]');
    if (wordmarkImg) {
      const wrap = wordmarkImg.closest("div");
      if (wrap) {
        wordmarkImg.style.display = "none";
        if (!wrap.querySelector(".cc-brand-lockup")) {
          wrap.prepend(buildBrandLockup());
        }
      }
    }

    // 2) Headline — replace the H1 text + add subhead under it.
    const h1 = formCol.querySelector("h1");
    if (h1) {
      const span = h1.querySelector("span") || h1;
      span.textContent = HEAD_TITLE;
      h1.classList.add("cc-head");
      // Subhead sibling — only insert once.
      if (!h1.parentElement.querySelector(".cc-sub")) {
        const sub = document.createElement("p");
        sub.className = "cc-sub";
        sub.textContent = HEAD_SUB;
        h1.parentElement.appendChild(sub);
      }
      // Eyebrow above the H1.
      if (!h1.parentElement.querySelector(".cc-eyebrow")) {
        const eyebrow = document.createElement("div");
        eyebrow.className = "cc-eyebrow";
        eyebrow.textContent = "Sign in";
        h1.parentElement.insertBefore(eyebrow, h1);
      }
    }

    // 3) Submit button — relabel "Sign In" → "Open the dossier".
    const submit = formCol.querySelector('button[type="submit"]');
    if (submit) {
      const submitSpan = submit.querySelector("span") || submit;
      submitSpan.textContent = SUBMIT_LABEL;
    }

    // 4) Bottom byline — append once.
    if (!formCol.querySelector(".cc-form-foot")) {
      formCol.appendChild(buildBottomByline());
    }

    // ---- RIGHT: remove the favicon-as-hero + inject the pull quote ----
    if (heroCol) {
      // Hide whatever <img> Chainlit placed in there (it serves /favicon).
      heroCol.querySelectorAll("img").forEach((i) => (i.style.display = "none"));
      if (!heroCol.querySelector(".cc-hero-overlay")) {
        heroCol.appendChild(buildHeroOverlay());
      }
    }

    return true;
  }

  // Bust the cache for Chainlit-served images (avatar + splash logo) so users
  // who hit the app before /avatars/{name} and /logo were customised get the
  // current responses instead of the cached Chainlit defaults.
  const CHAINLIT_IMG_BUST = "data-cc-img-bust";
  const IMG_VERSION = "v2";
  const BUST_SELECTOR = 'img[alt^="Avatar for "], img[alt="logo"]';
  function bustChainlitImages(root) {
    const imgs = root.querySelectorAll
      ? root.querySelectorAll(BUST_SELECTOR)
      : [];
    imgs.forEach((img) => {
      if (img.hasAttribute(CHAINLIT_IMG_BUST)) return;
      const u = new URL(img.src, location.href);
      if (u.searchParams.get("ccv") === IMG_VERSION) return;
      u.searchParams.set("ccv", IMG_VERSION);
      img.setAttribute(CHAINLIT_IMG_BUST, "1");
      img.src = u.toString();
    });
  }

  // Run on first paint, then keep watching for SPA route changes / hydration.
  let observer;
  function start() {
    stageLoginPage();
    bustChainlitImages(document);
    observer = new MutationObserver(() => {
      if (!document.body.hasAttribute(STAGED) && isLoginDom()) {
        stageLoginPage();
      } else if (document.body.hasAttribute(STAGED) && !isLoginDom()) {
        // Navigated away from login — drop the marker so we'd re-run on return.
        document.body.removeAttribute(STAGED);
      }
      bustChainlitImages(document);
    });
    observer.observe(document.body, { subtree: true, childList: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();

/* =====================================================================
   Dossier panel toggle button
   ---------------------------------------------------------------------
   Injected into the header when Document.jsx fires "cc:dossier-active".
   Calls window.__cc_toggle_dossier() (set by Document.jsx) to route
   through Chainlit's callAction → @cl.action_callback("toggle_dossier").
   The button persists once injected; React's virtual DOM diffing does
   not remove injected nodes outside its own tree.
   ===================================================================== */
(function () {
  "use strict";

  var DOSSIER_BTN_ID = "cc-dossier-toggle";

  // PanelRight (sidebar-right) from Lucide — signals a right-side panel.
  var PANEL_RIGHT_SVG =
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"' +
    ' fill="none" stroke="currentColor" stroke-width="1.5"' +
    ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect width="18" height="18" x="3" y="3" rx="2"/>' +
    '<path d="M15 3v18"/>' +
    "</svg>";

  function buildToggleBtn() {
    var btn = document.createElement("button");
    btn.id = DOSSIER_BTN_ID;
    btn.className = "cc-dossier-toggle";
    btn.setAttribute("aria-label", "Toggle dossier panel");
    btn.setAttribute("title", "Toggle dossier");
    btn.innerHTML = PANEL_RIGHT_SVG;
    btn.addEventListener("click", function () {
      if (typeof window.__cc_toggle_dossier === "function") {
        window.__cc_toggle_dossier();
      }
    });
    return btn;
  }

  function injectDossierToggle() {
    if (document.getElementById(DOSSIER_BTN_ID)) return;
    var header = document.querySelector("header") || document.getElementById("header");
    if (!header) return;
    // Chainlit's header buttons have IDs: theme-toggle, user-nav-button.
    // Insert just before the user avatar so the dossier toggle sits at the
    // far-right edge — symmetric to the ☰ sidebar toggle on the far left.
    var anchor =
      header.querySelector("#user-nav-button") ||
      header.querySelector("#theme-toggle") ||
      header.querySelector('button[aria-label*="theme" i]') ||
      header.querySelector('button[aria-label*="dark" i]') ||
      header.querySelector('button[aria-label*="light" i]');
    if (anchor && anchor.parentElement) {
      anchor.parentElement.insertBefore(buildToggleBtn(), anchor);
    } else {
      // Fallback: append to the last direct-child div of the header.
      var divs = header.querySelectorAll(":scope > div");
      var target = divs.length ? divs[divs.length - 1] : header;
      target.appendChild(buildToggleBtn());
    }
  }

  document.addEventListener("cc:dossier-active", injectDossierToggle);
})();
