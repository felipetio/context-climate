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

  // Run on first paint, then keep watching for SPA route changes / hydration.
  let observer;
  function start() {
    stageLoginPage();
    observer = new MutationObserver(() => {
      if (!document.body.hasAttribute(STAGED) && isLoginDom()) {
        stageLoginPage();
      } else if (document.body.hasAttribute(STAGED) && !isLoginDom()) {
        // Navigated away from login — drop the marker so we'd re-run on return.
        document.body.removeAttribute(STAGED);
      }
    });
    observer.observe(document.body, { subtree: true, childList: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
