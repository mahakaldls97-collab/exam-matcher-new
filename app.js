/* ═══════════════════════════════════════════════════════
   Exam Series & Answer Matcher — Frontend (Polling Mode)
   ═══════════════════════════════════════════════════════ */

let fileA = null;
let fileB = null;
let fileKey = null;

const $ = (id) => document.getElementById(id);

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

  dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
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
    info.innerHTML = `✅ <strong>${esc(file.name)}</strong><br><small>(${(file.size / (1024 * 1024)).toFixed(2)} MB)</small>`;
  }
}

function esc(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const STATUS_MESSAGES = {
  "starting": "📄 फ़ाइलें अपलोड हो गई हैं, प्रोसेसिंग शुरू हो रही है...",
  "extracting_paper_a": "🔍 आपके पेपर (Series A) को AI स्कैन कर रहा है...",
  "extracting_answer_key": "🔑 Answer Key पढ़ी जा रही है...",
  "extracting_paper_b": "👥 दोस्त का पेपर (Series D) स्कैन हो रहा है...",
  "matching_series": "🤖 दोनों सीरीज के प्रश्नों का मिलान (Matching) हो रहा है..."
};

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
  statusTitle.textContent = "📤 फ़ाइलें अपलोड हो रही हैं...";
  statusDesc.textContent = "कृपया प्रतीक्षा करें...";

  try {
    // Step 1: Upload files and get task_id (instant response, no timeout!)
    const formData = new FormData();
    formData.append("paper_a", fileA);
    if (fileB) formData.append("paper_b", fileB);
    if (fileKey) formData.append("answer_key", fileKey);

    const uploadRes = await fetch("/api/match-series", { method: "POST", body: formData });
    if (!uploadRes.ok) {
      const errData = await uploadRes.json().catch(() => ({}));
      throw new Error(errData.detail || `Server Error (${uploadRes.status})`);
    }

    const uploadData = await uploadRes.json();
    const taskId = uploadData.task_id;

    statusTitle.textContent = "⏳ AI प्रोसेसिंग चालू है...";
    statusDesc.textContent = "बड़ा पेपर है, 1-2 मिनट लग सकते हैं। कृपया यह पेज खुला रखें...";

    // Step 2: Poll for results every 4 seconds
    let elapsed = 0;
    const pollInterval = setInterval(async () => {
      elapsed += 4;
      try {
        const pollRes = await fetch(`/api/task/${taskId}`);
        const taskData = await pollRes.json();

        // Update status message
        if (STATUS_MESSAGES[taskData.status]) {
          statusTitle.textContent = STATUS_MESSAGES[taskData.status];
          statusDesc.textContent = `(${elapsed} सेकंड बीत चुके हैं...)`;
        }

        if (taskData.status === "done") {
          clearInterval(pollInterval);
          renderResults(taskData.result);
          statusCard.style.display = "none";
          resultsSection.style.display = "block";
          resultsSection.scrollIntoView({ behavior: "smooth" });
          matchBtn.disabled = false;
        } else if (taskData.status === "error") {
          clearInterval(pollInterval);
          statusCard.style.display = "none";
          errorBox.style.display = "block";
          errorBox.textContent = `❌ त्रुटि: ${taskData.error}`;
          matchBtn.disabled = false;
        }
      } catch (pollErr) {
        // Network glitch, keep polling
        statusDesc.textContent = `(${elapsed}s) नेटवर्क चेक हो रहा है...`;
      }
    }, 4000);

  } catch (err) {
    statusCard.style.display = "none";
    errorBox.style.display = "block";
    errorBox.textContent = `❌ त्रुटि (Error): ${err.message}`;
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
    let optsHtml = "";
    if (r.options && typeof r.options === "object") {
      optsHtml = `<div class="opts-preview">` +
        Object.entries(r.options).map(([k, v]) => `<span class="opt-pill"><strong>${k}:</strong> ${esc(v)}</span>`).join(" ") +
        `</div>`;
    }
    let ansHtml = "—";
    if (r.correct_answer && r.correct_answer !== "?") {
      ansHtml = `<span class="ans-badge">${esc(r.correct_answer)}</span>`;
    }

    tr.innerHTML = `
      <td style="text-align:center; font-weight:700; font-size:1.05rem;">Q.${esc(r.series_a_q_no)}</td>
      <td><div class="q-text">${esc(r.question)}</div>${optsHtml}</td>
      <td style="text-align:center; font-weight:700; color:var(--primary); font-size:1.1rem;">
        ${r.series_b_q_no && r.series_b_q_no !== "—" ? `Q.${esc(r.series_b_q_no)}` : "—"}
      </td>
      <td style="text-align:center;">${ansHtml}</td>
      <td style="text-align:center; font-size:0.85rem; color:var(--text-muted);">${r.matched_by === "ai" ? "AI" : "Direct"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function setupDownloadCsv() {
  const btn = $("download-csv-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const table = $("match-table");
    if (!table) return;
    let csv = [];
    for (let r of table.querySelectorAll("tr")) {
      const rowData = [];
      for (let c of r.querySelectorAll("th, td")) {
        let text = c.innerText.replace(/"/g, '""').replace(/\n/g, ' ');
        rowData.push(`"${text}"`);
      }
      csv.push(rowData.join(","));
    }
    const blob = new Blob([csv.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "Exam_Match_Results.csv";
    a.click();
    URL.revokeObjectURL(url);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupBox("drop-zone-a", "file-a", "file-info-a", (f) => { fileA = f; });
  setupBox("drop-zone-b", "file-b", "file-info-b", (f) => { fileB = f; });
  setupBox("drop-zone-key", "file-key", "file-info-key", (f) => { fileKey = f; });

  $("match-btn")?.addEventListener("click", startMatching);
  $("print-btn")?.addEventListener("click", () => window.print());
  setupDownloadCsv();
});
