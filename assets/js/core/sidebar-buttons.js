// Sidebar action buttons: jump to comments

document.addEventListener("DOMContentLoaded", function () {
  const jumpToCommentsBtn = document.getElementById("sidebarJumpToComments");

  // Jump to comments: hide button if no comments section on the page
  if (jumpToCommentsBtn) {
    const commentsEl = document.getElementById("twikoo-hextra");
    if (!commentsEl) {
      jumpToCommentsBtn.style.display = "none";
    }
  }
});

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
