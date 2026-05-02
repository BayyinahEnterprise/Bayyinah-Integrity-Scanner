/* Bayyinah demo controller. Vanilla JS, no framework.
 *
 * Posts a PDF to /demo/summarize, parses the JSON envelope, and renders
 * one of: pass / block / mughlaq / error / scan-error. The server-side
 * handler in bayyinah/demo.py runs the full scan plus optional Claude
 * summarization in a single round trip; the frontend never calls /scan
 * separately for the demo path.
 */
(function () {
  "use strict";

  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("fileInput");
  var output = document.getElementById("output");
  var counterScans = document.getElementById("counter-scans");
  var counterVisitors = document.getElementById("counter-visitors");

  // -----------------------------------------------------------------------
  // Scan counter strip: fetch /demo/stats on load and after each scan.
  // -----------------------------------------------------------------------
  function formatCount(n) {
    if (typeof n !== "number" || !isFinite(n)) return "-";
    return n.toLocaleString("en-US");
  }

  async function refreshStats() {
    if (!counterScans || !counterVisitors) return;
    try {
      var resp = await fetch("/demo/stats", { cache: "no-store" });
      if (!resp.ok) return;
      var s = await resp.json();
      counterScans.textContent = formatCount(s.scans);
      counterVisitors.textContent = formatCount(s.unique_visitors_total);
    } catch (e) {
      // Counter is informational only; failures are silent.
    }
  }

  // -----------------------------------------------------------------------
  // Post-scan waitlist CTA: appended below the result, calm, not a popup.
  // -----------------------------------------------------------------------
  function appendWaitlistCta() {
    if (!output) return;
    // Don't stack duplicates if a result re-renders.
    var existing = output.querySelector(".waitlist-cta-card");
    if (existing) existing.parentNode.removeChild(existing);

    var card = document.createElement("div");
    card.className = "waitlist-cta-card";
    card.innerHTML =
      "<p class='waitlist-cta-text'>" +
      "<strong>Want API access?</strong> Join the waitlist for release " +
      "reports, integration notes, and early access." +
      "</p>" +
      "<a class='waitlist-cta-button' href='/#waitlist'>Join the waitlist</a>";
    output.appendChild(card);
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function tierCounts(findings) {
    var counts = { 1: 0, 2: 0, 3: 0 };
    (findings || []).forEach(function (f) {
      if (f.tier === 1 || f.tier === 2 || f.tier === 3) counts[f.tier]++;
    });
    return counts;
  }

  function whatJustHappened(scan, scanMs, blocked, llmTokens) {
    var n = (scan && scan.findings) ? scan.findings.length : 0;
    var tc = tierCounts(scan && scan.findings);
    var forwarded = blocked ? "<strong>NOT</strong> forwarded" : "forwarded";
    var tokens = blocked ? 0 : (llmTokens || 0);
    return (
      "<div class='what-happened'>" +
      "<p>Scanner ran 159 mechanisms in <strong>" + scanMs + "ms</strong>.</p>" +
      "<p>Found <strong>" + tc[1] + "</strong> Tier 1, " +
        "<strong>" + tc[2] + "</strong> Tier 2, " +
        "<strong>" + tc[3] + "</strong> Tier 3 findings.</p>" +
      "<p>Document was " + forwarded + " to Claude.</p>" +
      "<p><strong>" + tokens + "</strong> LLM tokens consumed on this document.</p>" +
      "</div>"
    );
  }

  function renderFindings(findings) {
    if (!findings || findings.length === 0) {
      return "<p style='color: var(--muted); margin: 0.5rem 0 0;'>No findings recorded.</p>";
    }
    var items = findings.map(function (f) {
      var concealed =
        (f.inversion_recovery && f.inversion_recovery.concealed) || null;
      return (
        "<li>" +
        "<span class='mech'>" + escapeHtml(f.mechanism) + "</span> " +
        "<span class='tier'>(Tier " + escapeHtml(f.tier) + ")</span><br>" +
        "<span style='font-size: 0.85rem;'>" + escapeHtml(f.location || "") + "</span>" +
        (f.description ? "<br><span style='font-size: 0.85rem;'>" + escapeHtml(f.description) + "</span>" : "") +
        (concealed ? "<span class='concealed'>" + escapeHtml(concealed) + "</span>" : "") +
        "</li>"
      );
    });
    return "<ul class='findings'>" + items.join("") + "</ul>";
  }

  function render(envelope) {
    var scan = envelope.scan;
    var scanMs = envelope.scan_duration_ms || 0;
    var blocked = !!envelope.blocked;
    var verdict = (scan && scan.verdict) || "";
    var summaryError = envelope.summary_error;

    var html = "";

    if (envelope.block_reason === "scan_failed") {
      html =
        "<div class='panel error'>" +
        "<strong>Scanner error.</strong> Document was not analyzed and was not forwarded to Claude." +
        "<p style='color: var(--muted); margin-top: 0.4rem; font-size: 0.85rem;'>" +
        escapeHtml(summaryError || "") + "</p>" +
        "</div>";
      output.innerHTML = html;
      return;
    }

    if (verdict === "mughlaq") {
      html =
        "<div class='panel mughlaq'>" +
        "<span class='verdict-badge verdict-mughlaq'>mughlaq</span>" +
        "<p style='margin: 0;'>Document could not be fully scanned. Forwarded? No.</p>" +
        whatJustHappened(scan, scanMs, true, 0) +
        "</div>";
      output.innerHTML = html;
      return;
    }

    if (blocked) {
      html =
        "<div class='panel block'>" +
        "<span class='verdict-badge verdict-block'>" + escapeHtml(verdict || "blocked") + "</span>" +
        "<p style='margin: 0;'><strong>Blocked.</strong> " +
        "Reason: <code>" + escapeHtml(envelope.block_reason) + "</code>.</p>" +
        renderFindings(scan && scan.findings) +
        whatJustHappened(scan, scanMs, true, 0) +
        "</div>";
      output.innerHTML = html;
      return;
    }

    // Passed scan; check summary state.
    if (summaryError) {
      var msg;
      if (summaryError === "anthropic_key_missing") {
        msg = "Scan passed; LLM summarization unavailable. Document was not forwarded.";
      } else if (summaryError === "anthropic_timeout") {
        msg = "Scan passed; LLM call timed out at 30 seconds. Document was not forwarded.";
      } else if (summaryError.indexOf("text_extraction_failed") === 0) {
        msg = "Scan passed; text extraction failed before the LLM call. Document was not forwarded.";
      } else {
        msg = "Scan passed; LLM summarization unavailable. Document was not forwarded.";
      }
      html =
        "<div class='panel mughlaq'>" +
        "<span class='verdict-badge verdict-mughlaq'>" + escapeHtml(verdict || "sahih") + "</span>" +
        "<p style='margin: 0;'>" + escapeHtml(msg) + "</p>" +
        "<p style='color: var(--muted); margin-top: 0.4rem; font-size: 0.82rem;'>" +
        escapeHtml(summaryError) + "</p>" +
        whatJustHappened(scan, scanMs, false, 0) +
        "</div>";
      output.innerHTML = html;
      return;
    }

    // Pass + summary present.
    html =
      "<div class='panel pass'>" +
      "<span class='verdict-badge verdict-pass'>" + escapeHtml(verdict || "sahih") + "</span>" +
      "<p style='margin: 0;'><strong>Passed.</strong> Document forwarded to Claude.</p>" +
      "<p class='summary-text'>" + escapeHtml(envelope.summary || "") + "</p>" +
      whatJustHappened(scan, scanMs, false, envelope.llm_input_tokens) +
      "</div>";
    output.innerHTML = html;
  }

  function showStatus(msg) {
    output.innerHTML =
      "<div class='panel'>" +
      "<p class='scan-log'>" + escapeHtml(msg) + "</p>" +
      "</div>";
  }

  function showOversize() {
    output.innerHTML =
      "<div class='panel error'>" +
      "<p>File exceeds demo limit (25 MiB). Use the production /scan endpoint for larger files.</p>" +
      "</div>";
  }

  function showServerError(detail) {
    output.innerHTML =
      "<div class='panel error'>" +
      "<p><strong>Server error.</strong> " + escapeHtml(detail || "") + "</p>" +
      "</div>";
  }

  async function uploadFile(file) {
    if (!file) return;
    if (!/\.pdf$/i.test(file.name)) {
      showServerError("Only PDF files are accepted by this demo.");
      return;
    }
    showStatus("Scanning " + file.name + " ...");
    var fd = new FormData();
    fd.append("file", file);
    try {
      var resp = await fetch("/demo/summarize", {
        method: "POST",
        body: fd,
      });
      if (resp.status === 413) {
        showOversize();
        return;
      }
      if (!resp.ok) {
        var detail = "";
        try { detail = (await resp.json()).detail || ""; } catch (e) {}
        showServerError("HTTP " + resp.status + ". " + detail);
        return;
      }
      var envelope = await resp.json();
      render(envelope);
      appendWaitlistCta();
      refreshStats();
    } catch (e) {
      showServerError(String(e));
    }
  }

  dropzone.addEventListener("click", function () { fileInput.click(); });
  fileInput.addEventListener("change", function () {
    if (fileInput.files && fileInput.files[0]) uploadFile(fileInput.files[0]);
  });
  dropzone.addEventListener("dragover", function (e) {
    e.preventDefault();
    dropzone.classList.add("hover");
  });
  dropzone.addEventListener("dragleave", function () {
    dropzone.classList.remove("hover");
  });
  dropzone.addEventListener("drop", function (e) {
    e.preventDefault();
    dropzone.classList.remove("hover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  // Exhibit buttons: fetch a whitelisted fixture from
  // /demo/fixtures/<name>, wrap into a File, and run it through the
  // exact same uploadFile() path a manual user upload takes. Lets a
  // visitor see the firewall fire end-to-end without bringing their
  // own PDF.
  async function runExhibit(fixtureName) {
    showStatus("Fetching exhibit " + fixtureName + " ...");
    try {
      var resp = await fetch("/demo/fixtures/" + encodeURIComponent(fixtureName));
      if (!resp.ok) {
        showServerError("Could not load exhibit (" + resp.status + ").");
        return;
      }
      var blob = await resp.blob();
      var file = new File([blob], fixtureName, { type: "application/pdf" });
      await uploadFile(file);
    } catch (e) {
      showServerError(String(e));
    }
  }

  var exhibitButtons = document.querySelectorAll(".exhibit[data-fixture]");
  for (var i = 0; i < exhibitButtons.length; i++) {
    (function (btn) {
      btn.addEventListener("click", function () {
        var name = btn.getAttribute("data-fixture");
        if (name) runExhibit(name);
      });
    })(exhibitButtons[i]);
  }

  // Initial counter fetch on page load.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refreshStats);
  } else {
    refreshStats();
  }
})();
