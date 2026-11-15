const $ = (s, r = document) => r.querySelector(s);
const main = $("#main");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmtTime = t => { t = Math.max(0, Math.round(t)); return `${Math.floor(t/60)}:${String(t%60).padStart(2,"0")}`; };
const fmtSize = b => b >= 1073741824 ? (b/1073741824).toFixed(2)+" GB" : (b/1048576).toFixed(1)+" MB";
const state = { jobId: localStorage.getItem("jobId"), timer: null };
const STATUS = { uploaded:"Siap diproses", queued:"Antre", transcribing:"Transkripsi", analyzing:"Analisis", awaiting_selection:"Menunggu pilihan", rendering:"Render", done:"Selesai", error:"Gagal" };
const badge = s => `<span class="badge ${s==="done"?"done":s==="error"?"error":(s==="uploaded"||s==="awaiting_selection")?"":"run"}">${esc(STATUS[s]||s)}</span>`;

async function api(path, opts = {}) {
  let r;
  try { r = await fetch(path, opts); } catch { throw new Error("Tidak bisa terhubung ke server."); }
  let data = null; try { data = await r.json(); } catch {}
  if (!r.ok) {
    const d = data && data.detail;
    throw new Error(Array.isArray(d) ? d.map(x => x.msg).join("; ") : (d || `Kesalahan ${r.status}`));
  }
  return data;
}

function setNav(active) {
  const id = state.jobId;
  const items = [["dashboard","Dashboard","#/dashboard",true],["upload","Upload","#/upload",true],
    ["settings","Pengaturan",`#/settings/${id}`,!!id],["process","Proses",`#/process/${id}`,!!id],
    ["results","Hasil",`#/results/${id}`,!!id],["history","Riwayat","#/history",true]];
  $("#nav").innerHTML = items.map(([k,l,h,on]) => `<a href="${h}" class="${k===active?"on":""} ${on?"":"off"}">${l}</a>`).join("");
}
const needJob = () => { main.innerHTML = `<div class="card">Belum ada pekerjaan. <a href="#/upload">Unggah video</a> dulu.</div>`; };

const routes = { dashboard: viewDashboard, upload: viewUpload, settings: viewSettings, process: viewProcess, results: viewResults, history: viewHistory };
function go() {
  clearInterval(state.timer);
  const [name, id] = (location.hash.slice(2) || "dashboard").split("/");
  if (id) { state.jobId = id; localStorage.setItem("jobId", id); }
  const view = routes[name] || viewDashboard;
  setNav(routes[name] ? name : "dashboard");
  view(id || state.jobId).catch(e => { main.innerHTML = `<div class="card err">${esc(e.message)}</div>`; });
}
window.addEventListener("hashchange", go);

/* ---------- Dashboard ---------- */
async function viewDashboard() {
  const [h, jobs] = await Promise.all([api("/api/health"), api("/api/jobs")]);
  const ok = v => v ? `<span class="ok">Siap</span>` : `<span class="bad">Belum</span>`;
  main.innerHTML = `<h1>Dashboard</h1>
  <div class="grid">
    <div class="card"><div class="muted">Total pekerjaan</div><div class="stat">${jobs.length}</div></div>
    <div class="card"><div class="muted">FFmpeg</div><div class="stat">${ok(h.ffmpeg)}</div></div>
    <div class="card"><div class="muted">faster-whisper</div><div class="stat">${ok(h.faster_whisper)}</div></div>
  </div>
  <div class="card"><h2>Batas &amp; info</h2>
    <p class="muted">Format: ${h.formats.join(", ")} · Maks upload ${h.max_upload_mb} MB · Maks durasi ${h.max_video_minutes} menit.<br>
    Model Whisper terunduh: ${Object.entries(h.models_cached).map(([m,v])=>`${m}: ${v?"ya":"belum (diunduh otomatis saat pertama dipakai)"}`).join(" · ")}.<br>
    Semua pemrosesan berjalan lokal di CPU server. Deteksi highlight hanya membaca transkrip, bukan isi visual video.</p>
    <a class="btn" href="#/upload">Mulai unggah video</a></div>
  <div class="card"><h2>Pekerjaan terbaru</h2>${jobs.slice(0,3).map(j => `<p><a href="#/${j.status==="done"?"results":"process"}/${j.id}">${esc(j.filename)}</a> ${badge(j.status)}</p>`).join("") || `<p class="muted">Belum ada.</p>`}</div>`;
}

/* ---------- Upload ---------- */
async function viewUpload() {
  const h = await api("/api/health");
  main.innerHTML = `<h1>Upload Video</h1>
  <div class="card"><h2>Import URL YouTube</h2>
    <p class="muted">Periksa judul dan thumbnail video publik. Untuk pemrosesan, unggah file sumber yang Anda miliki atau berhak gunakan; aplikasi tidak mengunduh video YouTube.</p>
    <div class="row"><input id="yturl" type="url" placeholder="https://www.youtube.com/watch?v=..." style="flex:1;min-width:180px"><button id="ytcheck">Periksa URL</button></div>
    <div id="ytresult" class="muted" style="margin-top:12px"></div>
  </div>
  <div class="card"><h2>Atau upload file video</h2><div class="drop">
    <p>Pilih video (${h.formats.join(", ")}) — maks ${h.max_upload_mb} MB</p>
    <input type="file" id="file" accept=".mp4,.mov,.mkv,video/mp4,video/quicktime,video/x-matroska">
    <p id="finfo" class="muted"></p><div class="bar"><div id="ubar"></div></div><p id="umsg" class="muted"></p>
    <button id="ubtn" disabled>Unggah</button></div></div>`;
  const file = $("#file"), btn = $("#ubtn");
  $("#ytcheck").onclick = async () => {
    const url = $("#yturl").value.trim(), out = $("#ytresult"), check = $("#ytcheck");
    if (!url) { out.textContent = "Tempel URL YouTube terlebih dahulu."; return; }
    check.disabled = true; out.textContent = "Memeriksa URL...";
    try {
      const d = await api("/api/youtube/preview", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({url})});
      out.innerHTML = `<div class="row" style="align-items:flex-start"><img src="${esc(d.thumbnail)}" alt="Thumbnail" style="width:150px;max-width:40%;border-radius:8px"><div><b>${esc(d.title)}</b><p>${esc(d.author)}</p></div></div><p class="muted">${esc(d.notice)}</p>`;
    } catch(e) { out.textContent = e.message; }
    finally { check.disabled = false; }
  };
  const msg = (t, bad) => { $("#umsg").textContent = t; $("#umsg").className = bad ? "bad" : "muted"; };
  file.onchange = () => {
    const f = file.files[0]; btn.disabled = true; msg("");
    if (!f) return;
    $("#finfo").textContent = `${f.name} — ${fmtSize(f.size)}`;
    const ext = "." + f.name.split(".").pop().toLowerCase();
    if (!h.formats.includes(ext)) return msg("Format tidak didukung. Gunakan MP4, MOV, atau MKV.", true);
    if (f.size > h.max_upload_mb * 1048576) return msg(`File terlalu besar. Batas ${h.max_upload_mb} MB.`, true);
    btn.disabled = false;
  };
  btn.onclick = () => {
    const f = file.files[0]; if (!f) return;
    btn.disabled = true; file.disabled = true;
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `/api/upload?filename=${encodeURIComponent(f.name)}`);
    xhr.upload.onprogress = e => { if (e.lengthComputable) { const p = e.loaded / e.total; $("#ubar").style.width = (p*100)+"%"; msg(`Mengunggah ${Math.round(p*100)}% (${fmtSize(e.loaded)} / ${fmtSize(e.total)})`); } };
    xhr.onload = () => {
      let d = {}; try { d = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status === 200) { msg("Upload selesai. Memeriksa video..."); location.hash = `#/settings/${d.id}`; }
      else { msg(d.detail || `Upload gagal (${xhr.status}).`, true); btn.disabled = false; file.disabled = false; }
    };
    xhr.onerror = () => { msg("Koneksi terputus saat upload. Coba lagi.", true); btn.disabled = false; file.disabled = false; };
    msg("Memulai upload..."); xhr.send(f);
  };
}

/* ---------- Pengaturan ---------- */
async function viewSettings(id) {
  if (!id) return needJob();
  const job = await api(`/api/jobs/${id}`);
  if (!["uploaded", "error"].includes(job.status)) { location.hash = `#/process/${id}`; return; }
  main.innerHTML = `<h1>Pengaturan Editing</h1><div class="card"><p><b>${esc(job.filename)}</b><br><span class="muted">${fmtSize(job.size)} · ${fmtTime(job.duration)}</span></p>
  <label>Mode</label><div class="seg" id="mode">
    <label class="on"><input type="radio" name="mode" value="adaptive" checked>Adaptive<br><span class="muted">Otomatis pilih klip &amp; durasi</span></label>
    <label><input type="radio" name="mode" value="professional">Professional<br><span class="muted">Atur sendiri &amp; pilih klip manual</span></label></div>
  <div id="pro" hidden>
    <label>Jumlah klip (1–10)</label><input type="number" id="count" value="3" min="1" max="10">
    <label>Durasi minimum (detik)</label><input type="number" id="mind" value="20" min="10" max="90">
    <label>Durasi maksimum (detik)</label><input type="number" id="maxd" value="60" min="15" max="180"></div>
  <label>Bahasa ucapan</label><select id="lang"><option value="auto">Deteksi otomatis</option><option value="id">Indonesia</option><option value="en">Inggris</option></select>
  <label>Model Whisper</label><select id="model"><option value="base">base (lebih akurat, lebih lambat)</option><option value="tiny">tiny (lebih cepat)</option></select>
  <label>Rasio</label><select id="aspect"><option>9:16</option><option>16:9</option><option>1:1</option></select>
  <label>Resolusi</label><select id="res"><option value="720p">720p (lebih cepat)</option><option value="1080p">1080p</option></select>
  <label><input type="checkbox" id="subs" checked> Bakar subtitle ke video</label>
  <p id="smsg" class="bad"></p>
  <div class="row"><button id="go">Mulai proses AI</button></div></div>`;
  document.querySelectorAll("#mode input").forEach(r => r.onchange = () => {
    $("#pro").hidden = r.value !== "professional" || !r.checked;
    document.querySelectorAll("#mode label").forEach(l => l.classList.toggle("on", l.querySelector("input").checked));
    $("#pro").hidden = $("input[name=mode]:checked").value !== "professional";
  });
  $("#go").onclick = async () => {
    const body = { mode: $("input[name=mode]:checked").value, language: $("#lang").value, whisper_model: $("#model").value,
      aspect: $("#aspect").value, resolution: $("#res").value, subtitles: $("#subs").checked };
    if (body.mode === "professional") { body.clip_count = +$("#count").value; body.min_duration = +$("#mind").value; body.max_duration = +$("#maxd").value; }
    $("#go").disabled = true;
    try { await api(`/api/jobs/${id}/start`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body) }); location.hash = `#/process/${id}`; }
    catch (e) { $("#smsg").textContent = e.message; $("#go").disabled = false; }
  };
}

/* ---------- Proses ---------- */
async function viewProcess(id) {
  if (!id) return needJob();
  main.innerHTML = `<h1>Proses AI</h1><div id="pstatus"></div><div id="pcands"></div><div id="ptrans"></div>`;
  let candsShown = false, transShown = false;
  const stages = [["transcribing","Transkripsi"],["analyzing","Analisis"],["awaiting_selection","Pilih klip"],["rendering","Render"]];
  const tick = async () => {
    let job;
    try { job = await api(`/api/jobs/${id}`); } catch (e) { $("#pstatus").innerHTML = `<div class="card err">${esc(e.message)}</div>`; clearInterval(state.timer); return; }
    if (job.status === "done") { location.hash = `#/results/${id}`; return; }
    const idx = job.status === "queued" ? -1 : stages.findIndex(s => s[0] === job.status);
    const st = job.settings || {};
    $("#pstatus").innerHTML = `<div class="card"><p><b>${esc(job.filename)}</b> ${badge(job.status)}</p>
      <div class="stages">${stages.map((s,i)=>`<span class="stage ${i===idx?"now":(idx>i||(job.status==="error"&&false))?"past":""}">${s[1]}</span>`).join("")}</div>
      ${["queued","transcribing","analyzing","rendering"].includes(job.status) ? `<div class="bar"><div style="width:${Math.round((job.progress||0)*100)}%"></div></div>` : ""}
      <p class="muted">${esc(job.message||"")}</p>
      ${job.status==="error" ? `<p class="bad">${esc(job.error||"Terjadi kesalahan.")}</p><a class="btn" href="#/settings/${id}">Coba lagi</a>` : ""}
      ${job.status==="uploaded" ? `<a class="btn" href="#/settings/${id}">Atur &amp; mulai proses</a>` : ""}
      ${job.language ? `<p class="muted">Bahasa terdeteksi: ${esc(job.language)} · Mode: ${esc(st.mode||"-")}</p>` : ""}</div>`;
    if (job.status === "awaiting_selection" && !candsShown) {
      candsShown = true;
      $("#pcands").innerHTML = `<div class="card"><h2>Kandidat klip</h2><p class="muted">Dipilih berdasarkan analisis transkrip (bukan visual). Centang yang ingin dirender.</p>
        ${job.candidates.map(c => `<div class="cand"><input type="checkbox" class="pick" value="${c.id}" checked><div><b>${fmtTime(c.start_s)} – ${fmtTime(c.end_s)}</b> (${Math.round(c.end_s-c.start_s)} dtk) · skor ${c.score}<br>
        <span class="muted">${esc(c.reason)}</span><br>“${esc(c.text)}”</div></div><hr style="border-color:var(--line)">`).join("")}
        <p id="cmsg" class="bad"></p><button id="rbtn">Render klip terpilih</button></div>`;
      $("#rbtn").onclick = async () => {
        const ids = [...document.querySelectorAll(".pick:checked")].map(x => +x.value);
        if (!ids.length) { $("#cmsg").textContent = "Pilih minimal satu klip."; return; }
        $("#rbtn").disabled = true;
        try { await api(`/api/jobs/${id}/render`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({candidate_ids: ids}) }); candsShown = false; $("#pcands").innerHTML = ""; }
        catch (e) { $("#cmsg").textContent = e.message; $("#rbtn").disabled = false; }
      };
    } else if (job.status !== "awaiting_selection" && candsShown) { candsShown = false; $("#pcands").innerHTML = ""; }
    if (job.has_transcript && !transShown) {
      transShown = true;
      try {
        const t = await api(`/api/jobs/${id}/transcript`);
        $("#ptrans").innerHTML = `<div class="card"><details><summary>Transkrip (${t.segments.length} segmen)</summary><div class="trans">${t.segments.map(s => `<p><b>${fmtTime(s.start)}</b> ${esc(s.text)}</p>`).join("")}</div></details></div>`;
      } catch { transShown = false; }
    }
  };
  await tick();
  state.timer = setInterval(tick, 1500);
}

/* ---------- Hasil ---------- */
async function viewResults(id) {
  if (!id) return needJob();
  const job = await api(`/api/jobs/${id}`);
  if (job.status !== "done") { main.innerHTML = `<div class="card">Pekerjaan belum selesai. <a href="#/process/${id}">Lihat proses</a></div>`; return; }
  const st = job.settings || {};
  main.innerHTML = `<h1>Hasil Klip</h1><p class="muted">${esc(job.filename)} · ${esc(st.aspect)} · ${esc(st.resolution)} · subtitle ${st.subtitles?"aktif":"mati"}</p>
  <div class="row" style="margin:0 0 14px"><a class="btn" href="/api/jobs/${id}/download.zip">Unduh semua (ZIP)</a></div>
  <div class="grid">${job.clips.map(c => `<div class="card"><video controls playsinline preload="metadata" src="/api/jobs/${id}/clips/${c.id}/preview"></video>
    <p><b>Klip ${c.number}</b> · ${fmtTime(c.start_s)}–${fmtTime(c.end_s)} · ${fmtSize(c.size)}</p>
    <a class="btn" href="/api/jobs/${id}/clips/${c.id}/download">Unduh</a></div>`).join("")}</div>`;
}

/* ---------- Riwayat ---------- */
async function viewHistory() {
  const jobs = await api("/api/jobs");
  main.innerHTML = `<h1>Riwayat</h1>${jobs.map(j => `<div class="card"><p><b>${esc(j.filename)}</b> ${badge(j.status)}<br>
    <span class="muted">${fmtSize(j.size)} · ${fmtTime(j.duration)} · ${esc(j.created_at.replace("T"," ").slice(0,16))} UTC</span></p>
    ${j.status==="error" ? `<p class="bad">${esc(j.error||"")}</p>` : ""}
    <div class="row" style="margin-top:6px"><a class="btn sec" href="#/${j.status==="done"?"results":j.status==="uploaded"?"settings":"process"}/${j.id}">Buka</a>
    <button class="danger" data-del="${j.id}">Hapus</button></div></div>`).join("") || `<div class="card muted">Belum ada pekerjaan.</div>`}`;
  document.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Hapus pekerjaan ini beserta semua file hasilnya?")) return;
    try { await api(`/api/jobs/${b.dataset.del}`, { method: "DELETE" }); if (state.jobId === b.dataset.del) { state.jobId = null; localStorage.removeItem("jobId"); } go(); }
    catch (e) { alert(e.message); }
  });
}

if (!location.hash) location.hash = "#/dashboard"; else go();
