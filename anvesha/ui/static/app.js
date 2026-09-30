/* ANVESHA mission-control client. Displays engine state only (no mock data). */
"use strict";
const $ = (id) => document.getElementById(id);
const C = { cyan: "#4fb3d9", amber: "#e3a33b", green: "#46b37a", red: "#d9534f", violet: "#9b8cd9", mute: "#6f7f90", line: "#1e2835", ink: "#c8d3de" };
const MODECOL = { SEARCH: C.amber, ACQUIRE: C.violet, TRACK: C.green, COAST: C.amber, REACQUIRE: C.red };
let ws = null, tel = null, world = null, camImg = null, paused = false;
const N = 600;
const hist = { t: [], elos: [], eimg: [], pr: [], tr: [], proc: [], fps: [] };
const trail = [];

/* ---------------- tabs ---------------- */
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x === b));
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "bench") loadBench();
});

/* ---------------- websocket ---------------- */
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "blob";
  ws.onopen = () => $("conn").classList.add("on");
  ws.onclose = () => { $("conn").classList.remove("on"); setTimeout(connect, 1500); };
  ws.onmessage = async (ev) => {
    if (typeof ev.data !== "string") {
      try { camImg = await createImageBitmap(ev.data); drawCam(); } catch (e) { }
      return;
    }
    const m = JSON.parse(ev.data);
    if (m.type === "tel") onTel(m.d);
    else if (m.type === "world") { world = m.d; drawWorld(); draw3D(); }
    else if (m.type === "error") logEv("ERROR  " + m.error);
    else if (m.type === "ack" && m.cmd === "start") { $("runId").textContent = m.meta.run_id || "—"; syncDeck(); resetHist(); }
  };
}
const send = (o) => ws && ws.readyState === 1 && ws.send(JSON.stringify(o));

/* ---------------- telemetry ---------------- */
function fmt(x, n = 2, u = "") { return (x === null || x === undefined || Number.isNaN(x)) ? "—" : (+x).toFixed(n) + u; }
function onTel(d) {
  tel = d;
  $("simT").textContent = d.t.toFixed(2);
  $("fps").textContent = fmt(d.fps, 0);
  const chip = $("modeChip"); chip.textContent = d.mode; chip.className = "chip " + d.mode;
  $("tMode").textContent = d.mode; $("tMode").style.color = MODECOL[d.mode] || C.ink;
  $("tConf").textContent = fmt(d.conf, 2);
  $("tMeas").textContent = d.meas ? `${d.meas[0].toFixed(1)}, ${d.meas[1].toFixed(1)}` : "—";
  $("tSnr").textContent = fmt(d.snr, 1);
  $("tErrI").textContent = fmt(d.truth.err_img, 1, " px");
  $("tErrL").textContent = fmt(d.truth.err_los, 1, " px");
  $("tErrL").style.color = d.truth.err_los !== null && d.truth.err_los <= 10 ? C.green : C.amber;
  $("tCe").textContent = fmt(d.truth.cent_err, 3, " px");
  $("tNd").textContent = d.ndet;
  $("tSig").textContent = fmt(d.noise_sigma, 2, " DN");
  $("tSp").textContent = fmt(d.sp_frac, 3);
  $("tJit").textContent = fmt(d.jit_sigma, 2, " px");
  $("tNis").textContent = fmt(d.nis, 2);
  $("tPd").textContent = fmt(d.pd, 2);
  $("tProc").textContent = fmt(d.proc_ms, 2, " ms");
  $("gPan").textContent = fmt(d.pan_deg, 3, "°"); $("gTilt").textContent = fmt(d.tilt_deg, 3, "°");
  $("gPr").textContent = fmt(d.pan_rate, 2, " °/s"); $("gTr").textContent = fmt(d.tilt_rate, 2, " °/s");
  $("gZoom").textContent = d.zoom.toFixed(0) + "×  (" + (4 * d.zoom).toFixed(0) + "°×" + (3 * d.zoom).toFixed(0) + "°)";
  $("fovLbl").textContent = (4 * d.zoom).toFixed(1) + "°×" + (3 * d.zoom).toFixed(1) + "°";
  $("gLim").textContent = d.rate_lim[0] + " / " + d.rate_lim[1] + " °/s";
  if (d.imm) {
    $("imm").innerHTML = d.imm.map((p, i) => `<div class="row"><span>${d.imm_names[i]}</span><div class="bar"><i style="width:${(p * 100).toFixed(1)}%"></i></div><span>${(p * 100).toFixed(0)}%</span></div>`).join("");
  } else $("imm").innerHTML = `<span class="muted">${d.imm_names && d.imm_names.length > 1 ? "no active track (searching)" : "single-model / no estimator in this pipeline"}</span>`;
  (d.events || []).forEach(logEv);
  push("t", d.t); push("elos", d.truth.err_los); push("eimg", d.truth.err_img);
  push("pr", d.pan_rate); push("tr", d.tilt_rate); push("proc", d.proc_ms); push("fps", d.fps);
  drawGimbal(); if (!camImg) drawCam();
  if ((hist.t.length % 6) === 0) drawCharts();
}
function push(k, v) { hist[k].push(v === null ? NaN : v); if (hist[k].length > N) hist[k].shift(); }
function resetHist() { Object.keys(hist).forEach(k => hist[k] = []); trail.length = 0; $("events").textContent = ""; }
function logEv(s) { const e = $("events"); e.textContent += s + "\n"; if (e.textContent.length > 20000) e.textContent = e.textContent.slice(-15000); e.scrollTop = e.scrollHeight; }
$("clearLog").onclick = () => $("events").textContent = "";

/* ---------------- camera view ---------------- */
function drawCam() {
  const cv = $("cam"), g = cv.getContext("2d");
  g.fillStyle = "#000"; g.fillRect(0, 0, 640, 480);
  if (camImg) g.drawImage(camImg, 0, 0, 640, 480);
  if (!tel) return;
  // boresight
  g.strokeStyle = C.cyan; g.lineWidth = 1; g.globalAlpha = 0.9;
  g.beginPath(); g.moveTo(320 - 18, 240); g.lineTo(320 - 5, 240); g.moveTo(320 + 5, 240); g.lineTo(320 + 18, 240);
  g.moveTo(320, 240 - 18); g.lineTo(320, 240 - 5); g.moveTo(320, 240 + 5); g.lineTo(320, 240 + 18); g.stroke();
  g.strokeRect(320 - 10 / tel.zoom * 1, 240 - 10 / tel.zoom * 1, 20 / tel.zoom, 20 / tel.zoom); // 10 px lock box
  g.globalAlpha = 1;
  // candidates
  g.strokeStyle = "rgba(155,140,217,0.55)";
  (tel.cands || []).forEach(c => { g.strokeRect(c[0] - 6, c[1] - 6, 12, 12); });
  // prediction + gate
  if (tel.pred_uv) {
    const [u, v] = tel.pred_uv; g.strokeStyle = C.violet;
    g.beginPath(); g.moveTo(u, v - 6); g.lineTo(u + 6, v); g.lineTo(u, v + 6); g.lineTo(u - 6, v); g.closePath(); g.stroke();
    if (tel.gate_px) { g.setLineDash([3, 3]); g.beginPath(); g.arc(u, v, Math.max(tel.gate_px, 6), 0, 2 * Math.PI); g.stroke(); g.setLineDash([]); }
  }
  if (tel.meas) {
    const [u, v] = tel.meas; g.strokeStyle = MODECOL[tel.mode] || C.green; g.lineWidth = 1.5;
    g.strokeRect(u - 9, v - 9, 18, 18); g.lineWidth = 1;
    g.beginPath(); g.moveTo(320, 240); g.lineTo(u, v); g.stroke();
  }
  // HUD text
  g.font = "11px Consolas, monospace"; g.fillStyle = "rgba(10,14,19,0.65)"; g.fillRect(0, 0, 640, 18); g.fillRect(0, 462, 640, 18);
  g.fillStyle = MODECOL[tel.mode] || C.ink; g.fillText(tel.mode, 8, 13);
  g.fillStyle = C.ink;
  g.fillText(`T+${tel.t.toFixed(2)}s  ZOOM ${tel.zoom}×  PAN ${tel.pan_deg.toFixed(3)}°  TILT ${tel.tilt_deg.toFixed(3)}°`, 90, 13);
  g.fillText(`ERR img ${fmt(tel.truth.err_img, 1)}px  LOS ${fmt(tel.truth.err_los, 1)}px  CONF ${fmt(tel.conf, 2)}  SNR ${fmt(tel.snr, 1)}  ${fmt(tel.proc_ms, 1)}ms`, 8, 475);
  if (world && world.occluded) { g.fillStyle = C.red; g.fillText("BEACON OCCLUDED (scripted)", 460, 13); }
}

/* ---------------- world view ---------------- */
function cmap(v) { // dark -> cyan -> white (sequential)
  const t = v / 255; const r = Math.round(10 + 120 * t * t), gg = Math.round(30 + 150 * t), b = Math.round(45 + 170 * Math.sqrt(t));
  return [r, gg, b];
}
function drawWorld() {
  if (!world) return;
  $("searchLbl").textContent = world.search === "belief" ? "belief search" : world.search + " search";
  const cv = $("world"), g = cv.getContext("2d"), S = cv.width / world.W;
  g.fillStyle = "#05080b"; g.fillRect(0, 0, cv.width, cv.height);
  const searching = tel && (tel.mode === "SEARCH" || tel.mode === "REACQUIRE" || tel.mode === "ACQUIRE");
  if (world.search === "belief" && world.belief && searching) {
    const raw = atob(world.belief), [h, w] = world.belief_shape;
    const img = g.createImageData(w, h);
    for (let i = 0; i < w * h; i++) { const v = raw.charCodeAt(i), c = cmap(v); img.data[4 * i] = c[0]; img.data[4 * i + 1] = c[1]; img.data[4 * i + 2] = c[2]; img.data[4 * i + 3] = 20 + v * 0.45; }
    const tmp = document.createElement("canvas"); tmp.width = w; tmp.height = h; tmp.getContext("2d").putImageData(img, 0, 0);
    g.imageSmoothingEnabled = true; g.drawImage(tmp, 0, 0, cv.width, cv.height);
  }
  // grid (1 deg lines: 160 px)
  g.strokeStyle = "rgba(255,255,255,0.05)"; g.lineWidth = 1;
  for (let x = 0; x <= world.W; x += 160) { g.beginPath(); g.moveTo(x * S, 0); g.lineTo(x * S, cv.height); g.stroke(); }
  for (let y = 0; y <= world.H; y += 160) { g.beginPath(); g.moveTo(0, y * S); g.lineTo(cv.width, y * S); g.stroke(); }
  // target trail (truth, display only)
  trail.push(world.target); if (trail.length > 240) trail.shift();
  g.strokeStyle = "rgba(227,163,59,0.45)"; g.beginPath();
  trail.forEach((p, i) => i ? g.lineTo(p[0] * S, p[1] * S) : g.moveTo(p[0] * S, p[1] * S)); g.stroke();
  g.fillStyle = C.amber; g.beginPath(); g.arc(world.target[0] * S, world.target[1] * S, 3.5, 0, 7); g.fill();
  (world.others || []).forEach(o => { g.fillStyle = "#8a6a3a"; g.beginPath(); g.arc(o[0] * S, o[1] * S, 3, 0, 7); g.fill(); });
  // plan
  if (world.plan) { g.setLineDash([4, 3]); g.strokeStyle = C.violet; g.beginPath(); g.moveTo(world.bore_g[0] * S, world.bore_g[1] * S); g.lineTo(world.plan[0] * S, world.plan[1] * S); g.stroke(); g.setLineDash([]);
    g.strokeRect(world.plan[0] * S - 4, world.plan[1] * S - 4, 8, 8); }
  // FOV
  const [fw, fh] = world.fov; const b = world.bore;
  g.strokeStyle = C.cyan; g.lineWidth = 1.5; g.strokeRect((b[0] - fw / 2) * S, (b[1] - fh / 2) * S, fw * S, fh * S); g.lineWidth = 1;
  g.beginPath(); g.arc(b[0] * S, b[1] * S, 2, 0, 7); g.fillStyle = C.cyan; g.fill();
  if (Math.hypot(world.platform[0], world.platform[1]) > 1) {
    g.strokeStyle = "rgba(79,179,217,0.4)"; g.beginPath(); g.moveTo(world.bore_g[0] * S, world.bore_g[1] * S); g.lineTo(b[0] * S, b[1] * S); g.stroke();
  }
  g.fillStyle = C.mute; g.font = "10px Consolas, monospace";
  g.fillText("12.5° × 12.5°  (grid 1°)", 6, cv.height - 6);
}

/* ---------------- 3D view (same state) ---------------- */
let three = null;
function init3D() {
  if (three || typeof THREE === "undefined") return;
  const host = $("three"), w = host.clientWidth || 520, h = host.clientHeight || 520;
  const r = new THREE.WebGLRenderer({ antialias: true }); r.setSize(w, h); r.setClearColor(0x05080b); host.appendChild(r.domElement);
  const sc = new THREE.Scene(), cam = new THREE.PerspectiveCamera(40, w / h, 0.1, 1000);
  cam.position.set(6, 5, 12); cam.lookAt(0, 2, -60);
  sc.add(new THREE.GridHelper(40, 40, 0x1e2835, 0x121a23));
  sc.add(new THREE.AmbientLight(0x8899aa, 0.8)); const dl = new THREE.DirectionalLight(0xffffff, 0.7); dl.position.set(5, 10, 5); sc.add(dl);
  const base = new THREE.Mesh(new THREE.BoxGeometry(2.2, 0.5, 2.2), new THREE.MeshStandardMaterial({ color: 0x2a3747 })); base.position.y = 0.25; sc.add(base);
  const panG = new THREE.Group(); panG.position.y = 0.5; base.add(panG); panG.position.set(0, 0.25, 0);
  const yoke = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.2, 0.2), new THREE.MeshStandardMaterial({ color: 0x3a4a5c })); yoke.position.y = 0.6; panG.add(yoke);
  const tiltG = new THREE.Group(); tiltG.position.y = 1.0; panG.add(tiltG);
  const head = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 1.3, 20), new THREE.MeshStandardMaterial({ color: 0x4fb3d9 })); head.rotation.x = Math.PI / 2; head.position.z = -0.3; tiltG.add(head);
  const rayGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, -60)]);
  tiltG.add(new THREE.Line(rayGeo, new THREE.LineBasicMaterial({ color: 0x4fb3d9 })));
  // sky patch = the 12.5 deg virtual screen at 60 units, exaggerated x3 for visibility
  const D = 60, EX = 3, half = Math.tan((12.5 * EX / 2) * Math.PI / 180) * D;
  const patch = new THREE.Mesh(new THREE.PlaneGeometry(2 * half, 2 * half), new THREE.MeshBasicMaterial({ color: 0x0f1b26, side: THREE.DoubleSide }));
  patch.position.set(0, 1.5, -D); sc.add(patch);
  const pg = new THREE.GridHelper(2 * half, 12, 0x2a3747, 0x1b2733); pg.rotation.x = Math.PI / 2; pg.position.set(0, 1.5, -D + 0.05); sc.add(pg);
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(2 * half, 2 * half)), new THREE.LineBasicMaterial({ color: 0x46535f })); edge.position.set(0, 1.5, -D + 0.1); sc.add(edge);
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(1.4, 16, 12), new THREE.MeshBasicMaterial({ color: 0xe3a33b })); sc.add(beacon);
  const fovMat = new THREE.LineBasicMaterial({ color: 0x4fb3d9 });
  const fov = new THREE.LineLoop(new THREE.BufferGeometry(), fovMat); sc.add(fov);
  three = { r, sc, cam, panG, tiltG, beacon, fov, D, EX };
}
function dirFromPx(x, y) { // screen px -> exaggerated direction at distance D
  const dpp = 4 / 640 * three.EX; const az = (x - 1000) * dpp * Math.PI / 180, el = -(y - 1000) * dpp * Math.PI / 180;
  return new THREE.Vector3(Math.sin(az) * three.D, 1.5 + Math.tan(el) * three.D, -Math.cos(az) * three.D);
}
function draw3D() {
  if ($("three").classList.contains("hidden") || !world || !tel) return;
  init3D(); if (!three) return;
  const dpp = 4 / 640 * three.EX;
  three.panG.rotation.y = -(world.bore[0] - 1000) * dpp * Math.PI / 180;
  three.tiltG.rotation.x = -(world.bore[1] - 1000) * dpp * Math.PI / 180;
  three.beacon.position.copy(dirFromPx(world.target[0], world.target[1]));
  const [fw, fh] = world.fov, b = world.bore;
  three.fov.geometry.setFromPoints([dirFromPx(b[0] - fw / 2, b[1] - fh / 2), dirFromPx(b[0] + fw / 2, b[1] - fh / 2), dirFromPx(b[0] + fw / 2, b[1] + fh / 2), dirFromPx(b[0] - fw / 2, b[1] + fh / 2)]);
  three.r.render(three.sc, three.cam);
}
$("v2d").onclick = () => { $("three").classList.add("hidden"); $("v2d").classList.add("on"); $("v3d").classList.remove("on"); };
$("v3d").onclick = () => { $("three").classList.remove("hidden"); $("v3d").classList.add("on"); $("v2d").classList.remove("on"); draw3D(); };

/* ---------------- gimbal glyph ---------------- */
function drawGimbal() {
  const cv = $("gimbal"), g = cv.getContext("2d"), W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2, R = 55, lim = 6.25; // screen half-extent in degrees
  g.strokeStyle = C.line; g.strokeRect(cx - R, cy - R, 2 * R, 2 * R);
  g.beginPath(); g.moveTo(cx - R, cy); g.lineTo(cx + R, cy); g.moveTo(cx, cy - R); g.lineTo(cx, cy + R); g.stroke();
  const x = cx + tel.pan_deg / lim * R, y = cy + tel.tilt_deg / lim * R;
  g.fillStyle = C.cyan; g.beginPath(); g.arc(x, y, 4, 0, 7); g.fill();
  // rate vector and command
  const k = 6;
  g.strokeStyle = C.green; g.beginPath(); g.moveTo(x, y); g.lineTo(x + tel.pan_rate * k, y + tel.tilt_rate * k); g.stroke();
  g.strokeStyle = C.violet; g.setLineDash([2, 2]); g.beginPath(); g.moveTo(x, y); g.lineTo(x + tel.cmd[0] * k, y + tel.cmd[1] * k); g.stroke(); g.setLineDash([]);
  g.fillStyle = C.mute; g.font = "9px Consolas, monospace"; g.fillText("pan/tilt ±6.25°", 4, 10); g.fillText("rate", 4, H - 16); g.fillStyle = C.violet; g.fillText("cmd", 30, H - 16);
}

/* ---------------- charts ---------------- */
function line(cv, series, opts) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height, pad = 22;
  g.clearRect(0, 0, W, H);
  const t = hist.t; if (t.length < 2) return;
  const t0 = t[0], t1 = t[t.length - 1];
  let lo = opts.min ?? Infinity, hi = opts.max ?? -Infinity;
  if (opts.min === undefined || opts.max === undefined) series.forEach(s => s.d.forEach(v => { if (!Number.isNaN(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  if (opts.floor !== undefined) lo = Math.min(lo, opts.floor); if (opts.ceil !== undefined) hi = Math.max(hi, opts.ceil);
  if (!(hi > lo)) { hi = lo + 1; }
  const X = (v) => pad + (v - t0) / Math.max(t1 - t0, 1e-6) * (W - pad - 4), Y = (v) => H - 14 - (v - lo) / (hi - lo) * (H - 20);
  g.strokeStyle = C.line; g.lineWidth = 1; g.beginPath(); g.moveTo(pad, 4); g.lineTo(pad, H - 14); g.lineTo(W - 4, H - 14); g.stroke();
  g.fillStyle = C.mute; g.font = "9px Consolas, monospace"; g.fillText(hi.toFixed(1), 1, 10); g.fillText(lo.toFixed(1), 1, H - 14);
  (opts.limits || []).forEach(L => { if (L >= lo && L <= hi) { g.strokeStyle = C.red; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(pad, Y(L)); g.lineTo(W - 4, Y(L)); g.stroke(); g.setLineDash([]); } });
  series.forEach(s => {
    g.strokeStyle = s.c; g.lineWidth = s.w || 1.2; g.beginPath(); let pen = false;
    s.d.forEach((v, i) => { if (Number.isNaN(v)) { pen = false; return; } const x = X(t[i]), y = Y(Math.min(Math.max(v, lo), hi)); pen ? g.lineTo(x, y) : g.moveTo(x, y); pen = true; });
    g.stroke();
  });
}
function drawCharts() {
  line($("chErr"), [{ d: hist.eimg, c: "rgba(227,163,59,0.6)", w: 1 }, { d: hist.elos, c: C.cyan, w: 1.4 }], { min: 0, max: 40, limits: [10] });
  const L = tel ? tel.rate_lim[0] : 5;
  line($("chRate"), [{ d: hist.pr, c: C.cyan }, { d: hist.tr, c: C.green }], { min: -L * 1.1, max: L * 1.1, limits: [L, -L] });
  line($("chProc"), [{ d: hist.proc, c: C.cyan }], { min: 0, ceil: 10, limits: [50] });
}

/* ---------------- KPIs from the metrics engine ---------------- */
async function refreshKpis() {
  try {
    const s = await (await fetch("/api/summary")).json();
    if (!s || !s.frames) return;
    const k = (lab, v, lim, unit, lower = true, nd = 2) => {
      const ok = v === null || v === undefined || Number.isNaN(v) ? "na" : ((lower ? v <= lim : v >= lim) ? "ok" : "bad");
      return `<div class="kpi ${ok}"><i>${lab}</i><b>${ok === "na" ? "—" : (+v).toFixed(nd)}${unit}</b></div>`;
    };
    const rq = s.reacquisition_time_max_s;
    $("kpis").innerHTML =
      k("ACQUISITION ≤2 s", s.acquisition_time_s, 2, " s") +
      k("LOS ERR mean ≤10", s.tracking_error_los_px.mean, 10, " px", true, 1) +
      k("IMG ERR mean (incl. jitter)", s.tracking_error_img_px.mean, 10, " px", true, 1) +
      k("TARGET LOSS <5 %", s.target_loss_pct_excl_occlusion, 5, " %", true, 1) +
      k("REACQ max ≤1 s", rq, 1, " s") +
      k("LOOP FPS ≥20", s.fps_loop, 20, "", false, 0);
  } catch (e) { }
}
setInterval(refreshKpis, 1500);

/* ---------------- deck ---------------- */
async function loadScenarios() {
  const l = await (await fetch("/api/scenarios")).json();
  $("scenario").innerHTML = l.map(s => `<option value="${s.id}" title="${s.description.replace(/"/g, "'")}">${s.id}</option>`).join("");
}
$("btnStart").onclick = () => { paused = false; send({ cmd: "start", scenario: $("scenario").value, pipeline: $("pipeline").value, seed: +$("seed").value }); };
$("btnPause").onclick = () => { paused = !paused; send({ cmd: paused ? "pause" : "resume" }); $("btnPause").textContent = paused ? "▶" : "❚❚"; };
$("speed").onchange = () => send({ cmd: "speed", value: +$("speed").value });
$("btnKick").onclick = () => send({ cmd: "kick", px: [Math.random() * 600 - 300, Math.random() * 400 - 200] });
const occ = $("btnOcc");
occ.onmousedown = () => send({ cmd: "occlude", on: true }); occ.onmouseup = occ.onmouseleave = () => send({ cmd: "occlude", on: false });
document.querySelectorAll("[data-key]").forEach(el => {
  const out = el.nextElementSibling && el.nextElementSibling.tagName === "OUTPUT" ? el.nextElementSibling : null;
  const handler = () => {
    let v = el.type === "checkbox" ? el.checked : el.value;
    if (el.dataset.scale) v = (+v * +el.dataset.scale);
    if (out) out.textContent = el.value;
    const key = el.dataset.key;
    send({ cmd: "set", key, value: v });
    if (key === "noise.gaussian_sigma") send({ cmd: "set", key: "noise.gaussian", value: +v > 0 });
    if (key === "noise.salt_pepper_frac") send({ cmd: "set", key: "noise.salt_pepper", value: +v > 0 });
  };
  el.addEventListener(el.type === "range" ? "input" : "change", handler);
});
async function syncDeck() {
  try {
    const c = await (await fetch("/api/config")).json();
    document.querySelectorAll("[data-key]").forEach(el => {
      const [a, b] = el.dataset.key.split("."); let v = c[a][b];
      if (el.dataset.scale) v = v / +el.dataset.scale;
      if (el.type === "checkbox") el.checked = !!v; else el.value = v;
      const out = el.nextElementSibling; if (out && out.tagName === "OUTPUT") out.textContent = Math.round(v);
    });
    if (!c.noise.gaussian) { const g = document.querySelector("[data-key='noise.gaussian_sigma']"); g.value = 0; g.nextElementSibling.textContent = 0; }
    if (!c.noise.salt_pepper) { const g = document.querySelector("[data-key='noise.salt_pepper_frac']"); g.value = 0; g.nextElementSibling.textContent = 0; }
  } catch (e) { }
}
$("btnReport").onclick = async () => {
  const r = await (await fetch("/api/report", { method: "POST" })).json();
  if (r.html) { logEv("REPORT  " + r.html); window.open(r.html, "_blank"); } else logEv("REPORT  " + (r.error || "failed"));
};

/* ---------------- benchmark tab ---------------- */
const PL = { baseline_a: "A · threshold+PID", baseline_b: "B · blob+KF+PID", baseline_c: "C · CNN+KF+PID", anvesha: "ANVESHA" };
function benchTable(agg, pipes) {
  if (!agg) return `<p class="muted">No results yet.</p>`;
  const scen = [...new Set(Object.values(agg).map(r => r.scenario))].sort();
  const f = (v, n = 2) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : (+v).toFixed(n);
  const cls = (v, lim, lower = true) => (v === null || Number.isNaN(v)) ? "" : ((lower ? v <= lim : v >= lim) ? "ok" : "bad");
  let h = `<table class="bt"><tr><th>Scenario</th><th>Pipeline</th><th>Acq. mean s</th><th>Acq. max s</th><th>LOS err px</th><th>Img err px</th><th>Centroid RMS px</th><th>Loss %</th><th>Reacq max s</th><th>Unrecov.</th><th>FPS</th></tr>`;
  scen.forEach(s => (pipes || Object.keys(PL)).forEach(p => {
    const r = agg[`${s}|${p}`]; if (!r) return;
    h += `<tr class="${p}"><td>${s}</td><td>${PL[p] || p}</td><td class="${cls(r.acq_time_mean_s, 2)}">${f(r.acq_time_mean_s)}</td><td class="${cls(r.acq_time_max_s, 2)}">${f(r.acq_time_max_s)}</td>
      <td class="${cls(r.err_los_mean_px, 10)}">${f(r.err_los_mean_px)}</td><td class="${cls(r.err_img_mean_px, 10)}">${f(r.err_img_mean_px)}</td><td>${f(r.centroid_err_rms_px, 3)}</td>
      <td class="${cls(r.loss_pct_excl_occ, 5)}">${f(r.loss_pct_excl_occ)}</td><td class="${cls(r.reacq_max_s, 1)}">${f(r.reacq_max_s)}</td><td>${r.reacq_unrecovered}</td><td>${f(r.fps_loop, 0)}</td></tr>`;
  }));
  return h + "</table>";
}
async function loadBench() {
  const b = await (await fetch("/api/bench")).json();
  $("benchTable").innerHTML = benchTable(b.bench);
  $("ablTable").innerHTML = benchTable(b.ablation, ["anvesha", "abl_no_belief", "abl_no_zoom", "abl_no_imu_ff", "abl_no_jitter_R", "abl_no_cnn", "abl_kf_cv"]);
}

/* ---------------- video tab ---------------- */
$("vRun").onclick = async () => {
  const r = await (await fetch("/api/video", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: $("vPath").value, truth: $("vTruth").value, beacon_size: +$("vSize").value }) })).json();
  $("vOut").textContent = JSON.stringify(r, null, 1);
  const poll = setInterval(async () => {
    const s = await (await fetch("/api/video")).json();
    $("vOut").textContent = JSON.stringify(s, null, 1);
    if (s.state !== "running") clearInterval(poll);
  }, 1000);
};

loadScenarios().then(connect);
