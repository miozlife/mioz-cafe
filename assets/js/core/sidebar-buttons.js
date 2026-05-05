// Sidebar action buttons: back to top & jump to comments

document.addEventListener("DOMContentLoaded", function () {
  // Always show backToTop button, override the theme's scroll-based toggle
  var backToTopBtn = document.getElementById("backToTop");
  if (backToTopBtn) {
    backToTopBtn.classList.remove("hx:opacity-0");
    backToTopBtn.removeAttribute("tabindex");
    document.addEventListener("scroll", function () {
      backToTopBtn.classList.remove("hx:opacity-0");
      backToTopBtn.removeAttribute("tabindex");
    });
  }
});

// Scrolled from right-side TOC: jump to comments or page bottom
function sidebarJumpToComments() {
  var commentsEl = document.getElementById("twikoo-hextra");
  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (commentsEl) {
    commentsEl.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "start" });
  } else {
    window.scroll({ top: document.body.scrollHeight, behavior: prefersReducedMotion ? "auto" : "smooth" });
  }
}
