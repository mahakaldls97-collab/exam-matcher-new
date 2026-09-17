/* ═══════════════════════════════════════════════════════
   Exam Series & Answer Matcher — Frontend Controller
   ═══════════════════════════════════════════════════════ */

let fileA = null;
let fileB = null;
let fileKey = null;

const $ = (id) => document.getElementById(id);

// Bind file inputs and drag-and-drop
function setupBox(dropZoneId, inputId, infoId, onSelect) {
  const dropZone = $(dropZoneId);
  const input = $(inputId);
  const info = $(infoId);

  if (!dropZone || !input) return;

  dropZone.addEventListener("click", () => input.click());

  input.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0], dropZone, info, onSelect);
    }
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      input.files = e.dataTransfer.files;
      handleFile(e.dataTransfer.files[0], dropZone, info, onSelect);
    }
  });
}

function handleFile(file, dropZone, info, onSelect) {
  onSelect(file);
  dropZone.classList.add("has-file");
  const content = dropZone.querySelector(".drop-content");
  if (content) content.style.display = "none";
  if (info) {
    info.style.display = "block";
    info.innerHTML = `✅ <strong>${escapeHtml(file.name)}</strong><br><small>(${(file.size / (1024 * 1024)).toFixed(2)} MB)</small>`;
  }
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function startMatching() {
  const errorBox = $("error-box");
  const statusCard = $("status-card");
  const statusTitle = $("status-title");
  const statusDesc = $("status-desc");
  const matchBtn = $("match-btn");
  const resultsSection = $("results-section");

  errorBox.style.display = "none";
  errorBox.textContent = "";

  if (!fileA) {
    errorBox.style.display = "block";
    errorBox.textContent = "⚠️ कृपया कम से कम अपना पेपर (Series A) ज़रूर अपलोड करें।";
    return;
  }

  matchBtn.disabled = true;
  statusCard.style.display = "flex";
  resultsSection.style.display = "none";

  // Dynamic status updates
  statusTitle.textContent = "📄 PDF को स्कैन किया जा रहा है...";
  statusDesc.textContent = "AI मॉडल पेपर्स के प्रश्नों को हिंदी और अंग्रेजी में पढ़ रहा है...";

  let timerSec = 0;
  const timer = setInterval(() => {
    timerSec += 3;
    if (timerSec === 6) {
      statusTitle.textContent = "🔍 प्रश्नों का विश्लेषण चालू है...";
      statusDesc.textContent = "बड़ा पेपर है, प्रत्येक पेज के प्रश्नों को प्रोसेस किया जा रहा है...";
    } else if (timerSec === 15) {
      statusTitle.textContent = "🤖 दोनों पेपर्स की सीरीज का मिलान हो रहा है...";
      statusDesc.textContent = "Series A और Series D के प्रश्नों को मैच किया जा रहा है...";
    } else if (timerSec >= 30) {
      statusTitle.textContent = `⏳ अंतिम सारणी तैयार हो रही है (${timerSec}s)...`;
      statusDesc.textContent = "कृपया प्रतीक्षा करें, जल्द ही परिणाम सामने होंगे...";
    }
  }, 3000);

  try {
    const formData = new FormData();
    formData.append("paper_a", fileA);
    if (fileB) formData.append("paper_b", fileB);
    if (fileKey) formData.append("answer_key", fileKey);

    const res = await fetch("/api/match-series", {
      method: "POST",
      body: formData
    });

    clearInterval(timer);

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Server Error (${res.status})`);
    }

    const data = await res.json();
    renderResults(data);

    statusCard.style.display = "none";
    resultsSection.style.display = "block";
    resultsSection.scrollIntoView({ behavior: "smooth" });

  } catch (err) {
    clearInterval(timer);
    statusCard.style.display = "none";
    errorBox.style.display = "block";
    errorBox.textContent = `❌ त्रुटि (Error): ${err.message}`;
  } finally {
    matchBtn.disabled = false;
  }
}

function renderResults(data) {
  const tbody = $("match-table-body");
  tbody.innerHTML = "";

  const rows = data.matched_table || [];

  $("stat-total").textContent = data.total_questions || rows.length;
  $("stat-matched").textContent = data.questions_b_count > 0 ? `${rows.length} (Series D)` : "Single Series";
  $("stat-key").textContent = data.has_key ? "हाँ (Yes) ✅" : "नहीं (No)";

  rows.forEach((r) => {
    const tr = document.createElement("tr");

    // Options formatting
    let optsHtml = "";
    if (r.options && typeof r.options === "object") {
      optsHtml = `<div class="opts-preview">` + 
        Object.entries(r.options).map(([k, v]) => `<span class="opt-pill"><strong>${k}:</strong> ${escapeHtml(v)}</span>`).join(" ") +
        `</div>`;
    }

    // Answer badge
    let ansHtml = "—";
    if (r.correct_answer && r.correct_answer !== "?") {
      ansHtml = `<span class="ans-badge">${escapeHtml(r.correct_answer)}</span>`;
    }

    tr.innerHTML = `
      <td style="text-align:center; font-weight:700; font-size:1.05rem;">
        Q.${escapeHtml(r.series_a_q_no)}
      </td>
      <td>
        <div class="q-text">${escapeHtml(r.question)}</div>
        ${optsHtml}
      </td>
      <td style="text-align:center; font-weight:700; color:var(--primary); font-size:1.1rem;">
        ${r.series_b_q_no && r.series_b_q_no !== "—" ? `Q.${escapeHtml(r.series_b_q_no)}` : "—"}
      </td>
      <td style="text-align:center;">
        ${ansHtml}
      </td>
      <td style="text-align:center; font-size:0.85rem; color:var(--text-muted);">
        ${r.matched_by === "ai" ? "AI Matched" : "Direct"}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Setup CSV Download
function setupDownloadCsv() {
  const btn = $("download-csv-btn");
  if (!btn) return;

  btn.addEventListener("click", () => {
    const table = $("match-table");
    if (!table) return;

    let csv = [];
    const rows = table.querySelectorAll("tr");
    for (let r of rows) {
      const cols = r.querySelectorAll("th, td");
      const rowData = [];
      for (let c of cols) {
        let text = c.innerText.replace(/"/g, '""').replace(/\n/g, ' ');
        rowData.push(`"${text}"`);
      }
      csv.push(rowData.join(","));
    }

    const csvBlob = new Blob([csv.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(csvBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "Exam_Series_Match_Results.csv";
    a.click();
    URL.revokeObjectURL(url);
  });
}

// Initialise on load
document.addEventListener("DOMContentLoaded", () => {
  setupBox("drop-zone-a", "file-a", "file-info-a", (f) => { fileA = f; });
  setupBox("drop-zone-b", "file-b", "file-info-b", (f) => { fileB = f; });
  setupBox("drop-zone-key", "file-key", "file-info-key", (f) => { fileKey = f; });

  $("match-btn")?.addEventListener("click", startMatching);
  $("print-btn")?.addEventListener("click", () => window.print());
  setupDownloadCsv();
});
