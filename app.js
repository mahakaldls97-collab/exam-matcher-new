/* ═══════════════════════════════════════════════════════
   Exam Series & Answer Matcher — Frontend Logic
   ═══════════════════════════════════════════════════════ */

const API = "";

let paperAFile = null;
let paperBFile = null;
let keyFile    = null;

const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function showAlert(container, type, html) {
  container.innerHTML = `<div class="alert alert-${type}">${html}</div>`;
}

function setLoaderMessage(html) {
  const p = $("#global-loader p");
  if (p) p.innerHTML = html;
}

function setupUploadZone(zoneId, inputId, onFile) {
  const zone  = $(`#${zoneId}`);
  const input = $(`#${inputId}`);
  if (!zone || !input) return;

  input.addEventListener("change", () => {
    if (input.files[0]) onFile(input.files[0]);
  });

  zone.addEventListener("dragover",  e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", ()  => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const f = e.dataTransfer.files[0];
    if (f) { input.files = e.dataTransfer.files; onFile(f); }
  });
}

function markZoneFile(zoneId, file) {
  const zone = $(`#${zoneId}`);
  if (!zone) return;
  zone.classList.add("has-file");
  const icon   = zone.querySelector(".upload-icon");
  const label  = zone.querySelector(".upload-label");
  const name   = zone.querySelector(".file-name") || (() => {
    const el = document.createElement("div");
    el.className = "file-name";
    zone.appendChild(el);
    return el;
  })();
  if (icon)  icon.textContent  = "✅";
  if (label) label.textContent = "File selected!";
  name.textContent = file.name;
}

async function matchSeries() {
  if (!paperAFile) {
    return showAlert($("#upload-error"), "error", "⚠️ कृपया कम से कम अपना Question Paper (Series A) ज़रूर अपलोड करें।");
  }

  $("#upload-error").innerHTML = "";
  $("#match-btn").disabled = true;
  setLoaderMessage("📄 Document पढ़ा जा रहा है...<br><small>AI मॉडल पेपर्स को स्कैन कर रहा है...</small>");
  $("#global-loader").classList.add("show");

  let seconds = 0;
  const timer = setInterval(() => {
    seconds += 2;
    if (seconds === 4) {
      setLoaderMessage("🔍 दोनों पेपर्स के प्रश्नों को हिंदी और अंग्रेजी में पढ़ा जा रहा है...<br><small>कृपया प्रतीक्षा करें...</small>");
    } else if (seconds === 12) {
      setLoaderMessage("🤖 Series A और Series D के प्रश्नों का मिलान (Question Matching) हो रहा है...<br><small>बस थोड़ी ही देर और...</small>");
    } else if (seconds >= 24) {
      setLoaderMessage(`⏳ बड़ी फ़ाइल प्रोसेस हो रही है (${seconds}s)...<br><small>सारणी तैयार की जा रही है...</small>`);
    }
  }, 2000);

  try {
    const form = new FormData();
    form.append("paper_a", paperAFile);
    if (paperBFile) form.append("paper_b", paperBFile);
    if (keyFile)    form.append("answer_key", keyFile);

    const resp = await fetch(`${API}/api/match-series`, { method: "POST", body: form });
    const data = await resp.json();

    clearInterval(timer);
    if (!resp.ok) throw new Error(data.detail || "Server error");

    renderMatchedTable(data);
    $("#global-loader").classList.remove("show");
    $("#step-upload").style.display  = "none";
    $("#step-results").style.display = "block";
    $("#step-indicator-1").classList.remove("active");
    $("#step-indicator-1").classList.add("done");
    $("#step-indicator-2").classList.add("active");
    window.scrollTo({ top: 0, behavior: "smooth" });

  } catch (err) {
    clearInterval(timer);
    $("#global-loader").classList.remove("show");
    showAlert($("#upload-error"), "error", `❌ Error: ${err.message}`);
    $("#match-btn").disabled = false;
  }
}

function renderMatchedTable(data) {
  const tableBody = $("#results-table-body");
  tableBody.innerHTML = "";

  const rows = data.matched_table || [];
  $("#summary-badge").textContent = `कुल प्रश्न: ${rows.length} | दोस्त का पेपर: ${data.questions_b_count > 0 ? "Series D मैच हुआ ✅" : "अपलोड नहीं था"}`;

  rows.forEach(r => {
    const tr = document.createElement("tr");

    const ansBadge = r.correct_answer && r.correct_answer !== "?"
      ? `<span class="answer-chip chip-correct">${r.correct_answer}</span>`
      : `<span class="answer-chip chip-neutral">—</span>`;

    const bMatchBadge = r.series_b_q_no && r.series_b_q_no !== "—"
      ? `<strong style="color:var(--primary);font-size:1.05rem;">Q.${r.series_b_q_no}</strong>`
      : `<span style="color:var(--text-muted);">—</span>`;

    tr.innerHTML = `
      <td style="text-align:center;font-weight:700;font-size:1.05rem;">
        Q.${r.series_a_q_no}
      </td>
      <td class="q-preview">
        ${escHtml(r.question)}
      </td>
      <td style="text-align:center;">
        ${bMatchBadge}
      </td>
      <td style="text-align:center;">
        ${ansBadge}
      </td>
    `;
    tableBody.appendChild(tr);
  });
}

function restart() {
  paperAFile = null; paperBFile = null; keyFile = null;
  ["paper-a-zone", "paper-b-zone", "key-zone"].forEach(id => {
    const z = $(`#${id}`);
    if (!z) return;
    z.classList.remove("has-file");
    const name = z.querySelector(".file-name");
    if (name) name.textContent = "";
  });
  $$("input[type=file]").forEach(i => (i.value = ""));

  $("#step-results").style.display = "none";
  $("#step-upload").style.display  = "block";
  $("#step-indicator-2").classList.remove("active");
  $("#step-indicator-1").classList.remove("done");
  $("#step-indicator-1").classList.add("active");
  $("#match-btn").disabled = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.addEventListener("DOMContentLoaded", () => {
  setupUploadZone("paper-a-zone", "paper-a-input", f => { paperAFile = f; markZoneFile("paper-a-zone", f); });
  setupUploadZone("paper-b-zone", "paper-b-input", f => { paperBFile = f; markZoneFile("paper-b-zone", f); });
  setupUploadZone("key-zone",     "key-input",     f => { keyFile     = f; markZoneFile("key-zone", f); });

  $("#match-btn")?.addEventListener("click", matchSeries);
  $("#restart-btn")?.addEventListener("click", restart);
  $("#print-btn")?.addEventListener("click", () => window.print());
});
