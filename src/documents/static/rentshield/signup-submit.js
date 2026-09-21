// Shared loading-state behavior for the onboarding wizard's plain
// server-rendered <form method="post"> submits (signup_email.html,
// signup_verify.html) -- these are ordinary form posts, not fetch()
// calls, so there's no response to await here; the only job is to give
// immediate visual feedback and stop a double-click from firing two
// submits while the page navigates.
document.querySelectorAll(".rs-submit-form").forEach(function (form) {
  form.addEventListener("submit", function () {
    var btn = form.querySelector("button[type=submit]");
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    var label = btn.querySelector(".rs-btn-label");
    var text = label ? label.textContent : btn.textContent;
    btn.dataset.originalLabel = text;
    btn.innerHTML = '<span class="rs-spinner" aria-hidden="true"></span><span>' + text + "</span>";
  });
});
