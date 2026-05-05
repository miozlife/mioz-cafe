// Sidebar action buttons: back to top & jump to comments

document.addEventListener("DOMContentLoaded", function () {
  // Always show backToTop button, override the theme's scroll-based toggle
  const backToTopBtn = document.getElementById("backToTop");
  if (backToTopBtn) {
    backToTopBtn.classList.remove("hx:opacity-0");
    backToTopBtn.removeAttribute("tabindex");
    document.addEventListener("scroll", function () {
      backToTopBtn.classList.remove("hx:opacity-0");
      backToTopBtn.removeAttribute("tabindex");
    });
  }

  // Hide jump-to-comments buttons if page has no comment section.
  // Delay check to let Twikoo fully initialize its container.
  var buttons = ["sidebarJumpToComments", "tocJumpToComments"];
  setTimeout(function () {
    var hasComments = !!document.getElementById("twikoo-hextra");
    buttons.forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn && !hasComments) btn.style.display = "none";
    });
  }, 500);
});

function sidebarJumpToComments() {
  var commentsEl = document.getElementById("twikoo-hextra") || document.querySelector("[id^='twikoo']");
  if (commentsEl) {
    var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    commentsEl.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "start",
    });
  }
}
