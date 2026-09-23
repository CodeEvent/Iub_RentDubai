// Drives the signer identity-capture flow (signer_verify.html) against
// documents/rentshield_identity/signer_views.py's token-gated JSON API.
// Plain fetch(), not Angular -- this page is deliberately served
// OUTSIDE the Angular SPA (see paperless/urls.py's catch-all comment:
// the whole SPA shell is behind login_required, but the signer here
// has no RentShield account at all).
(function () {
  var root = document.getElementById("rs-signer-app");
  if (!root) return;

  var token = root.dataset.token;
  var apiBase = "/api/documents/notice-signer/" + encodeURIComponent(token) + "/";

  var phases = ["intro", "front", "selfie", "verified", "manual_review"];
  var busyEl = document.getElementById("rs-signer-busy");
  var errorEl = document.getElementById("rs-signer-error");

  function showPhase(name) {
    phases.forEach(function (phase) {
      var el = document.getElementById("rs-signer-" + phase.replace("_", "-"));
      if (el) el.style.display = phase === name ? "" : "none";
    });
  }

  function setBusy(isBusy) {
    busyEl.style.display = isBusy ? "" : "none";
  }

  function setError(message) {
    if (message) {
      errorEl.textContent = message;
      errorEl.style.display = "";
    } else {
      errorEl.style.display = "none";
    }
  }

  async function postJson(path) {
    var res = await fetch(apiBase + path, { method: "POST" });
    var body = await res.json();
    if (!res.ok) throw new Error(body.error || "Something went wrong -- try again.");
    return body;
  }

  async function postFile(path, fieldName, file) {
    var formData = new FormData();
    formData.append(fieldName, file);
    var res = await fetch(apiBase + path, { method: "POST", body: formData });
    var body = await res.json();
    if (!res.ok) throw new Error(body.error || "Something went wrong -- try again.");
    return body;
  }

  document.getElementById("rs-signer-start-btn").addEventListener("click", async function () {
    setError(null);
    setBusy(true);
    try {
      var result = await postJson("start/");
      setBusy(false);
      showPhase(result.status === "verified" ? "verified" : "front");
    } catch (err) {
      setBusy(false);
      setError(err.message);
    }
  });

  document.getElementById("rs-signer-front-input").addEventListener("change", async function (event) {
    var file = event.target.files[0];
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      var result = await postFile("front-document/", "document", file);
      setBusy(false);
      if (result.status === "failed") {
        setError(result.detail || "That photo could not be verified -- try again with a clear, well-lit shot.");
      } else {
        showPhase("selfie");
      }
    } catch (err) {
      setBusy(false);
      setError(err.message);
    }
  });

  document.getElementById("rs-signer-selfie-input").addEventListener("change", async function (event) {
    var file = event.target.files[0];
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      var result = await postFile("live-capture/", "selfie", file);
      setBusy(false);
      if (result.status === "verified") {
        showPhase("verified");
      } else if (result.status === "manual_review") {
        showPhase("manual_review");
      } else {
        setError(result.detail || "That selfie could not be verified -- try again.");
        showPhase("front");
      }
    } catch (err) {
      setBusy(false);
      setError(err.message);
    }
  });
})();
