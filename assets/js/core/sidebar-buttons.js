// Sidebar action buttons: back to top & jump to comments

document.addEventListener("DOMContentLoaded", function () {
  const backToTopBtn = document.getElementById("sidebarBackToTop");
  const jumpToCommentsBtn = document.getElementById("sidebarJumpToComments");

  // Back to top: show when scrolled past 300px, matching the TOC button behavior
  if (backToTopBtn) {
    document.addEventListener("scroll", function () {
      if (window.scrollY > 300) {
        backToTopBtn.classList.remove("hx:opacity-0");
        backToTopBtn.removeAttribute("tabindex");
      } else {
        backToTopBtn.classList.add("hx:opacity-0");
        backToTopBtn.setAttribute("tabindex", "-1");
      }
    });
  }

  // Jump to comments: hide button if no comments section on the page
  if (jumpToCommentsBtn) {
    const commentsEl = document.getElementById("twikoo-hextra");
    if (!commentsEl) {
      jumpToCommentsBtn.style.display = "none";
    }
  }
});

function sidebarScrollUp() {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scroll({
    top: 0,
    left: 0,
    behavior: prefersReducedMotion ? "auto" : "smooth",
  });
}

function sidebarJumpToComments() {
  const commentsEl = document.getElementById("twikoo-hextra");
  if (commentsEl) {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    commentsEl.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "start",
    });
  }
}
