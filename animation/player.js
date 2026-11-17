const el = (id) => document.getElementById(id);
const timeline = window.PULSECHECK_TIMELINE;
const recordings = window.PULSECHECK_DATA.cases;
const slides = [...document.querySelectorAll(".slide")];
const audio = el("narration");
const play = el("play");
const seek = el("seek");
const status = el("status");
const duration = timeline.at(-1).end;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
let currentScene = -1;
let frame;

function formatTime(time) {
  const whole = Math.floor(time);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function addCase(record) {
  const card = document.createElement("article");
  const difference = Math.abs(record.latestBpm - record.ecgBpm);
  const missed = difference > 5;
  card.className = missed ? "case miss" : "case";
  const heading = document.createElement("h3");
  heading.textContent = `Case ${record.id}`;
  const rates = document.createElement("dl");
  for (const [label, rate] of [["Previous", record.previousBpm], ["Latest", record.latestBpm], ["ECG", record.ecgBpm]]) {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    const number = document.createElement("dd");
    term.textContent = label;
    number.textContent = rate.toFixed(1);
    group.append(term, number);
    rates.append(group);
  }
  const verdict = document.createElement("p");
  verdict.textContent = `${difference.toFixed(1)} bpm from ECG · ${missed ? "Outside tolerance" : "Within tolerance"}`;
  card.append(heading, rates, verdict);
  el("cases").append(card);
  return card;
}

const cases = recordings.map(addCase);
const steps = [...document.querySelectorAll(".step")];
const chapterButtons = timeline.map((scene, index) => {
  const chapter = document.createElement("button");
  chapter.type = "button";
  chapter.textContent = scene.label;
  chapter.setAttribute("aria-label", `Seek to ${scene.label} · ${formatTime(scene.start)}`);
  chapter.addEventListener("click", () => jump(scene.start));
  el("chapters").append(chapter);
  const note = document.createElement("p");
  const name = document.createElement("strong");
  name.textContent = `${formatTime(scene.start)} · ${scene.label}`;
  note.append(name, document.createElement("br"), scene.narration.replaceAll("E C G", "ECG"));
  el("transcript").append(note);
  return chapter;
});

function drawTrace(canvas, values, hz, color, elapsed, beats = []) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  const scale = devicePixelRatio || 1;
  const pixelsWide = Math.round(width * scale);
  const pixelsHigh = Math.round(height * scale);
  if (canvas.width !== pixelsWide || canvas.height !== pixelsHigh) {
    canvas.width = pixelsWide;
    canvas.height = pixelsHigh;
  }
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);
  const x = (time) => time * width / 10;
  const y = (value) => height / 2 - value * (height / 2 - 4);

  context.lineWidth = 1;
  context.strokeStyle = "#69869846";
  context.beginPath();
  for (let second = 0; second <= 10; second++) {
    context.moveTo(x(second), 0);
    context.lineTo(x(second), height);
  }
  for (const part of [.25, .5, .75]) {
    context.moveTo(0, part * height);
    context.lineTo(width, part * height);
  }
  context.stroke();

  function trace(stop, opacity) {
    context.strokeStyle = color;
    context.globalAlpha = opacity;
    context.lineWidth = 1.8;
    context.lineJoin = "round";
    context.beginPath();
    context.moveTo(0, y(values[0]));
    for (let i = 1; i < values.length && i / hz <= stop; i++) context.lineTo(x(i / hz), y(values[i]));
    context.stroke();
    context.globalAlpha = 1;
  }
  trace(10, .35);
  const cursor = Math.min(elapsed, 10);
  trace(cursor, 1);
  context.fillStyle = color;
  for (const beat of beats) {
    if (beat > cursor) break;
    context.beginPath();
    context.arc(x(beat), y(values[Math.min(values.length - 1, Math.round(beat * hz))]), 2.3, 0, 2 * Math.PI);
    context.fill();
  }
  if (cursor > 0 && cursor < 10) {
    context.fillStyle = "#ffffff90";
    context.fillRect(x(cursor), 0, 1, height);
  }
}

function render() {
  const time = Math.min(audio.currentTime, duration);
  const index = timeline.findLastIndex((scene) => time >= scene.start);
  const scene = timeline[index];
  const elapsed = time - scene.start;
  if (index !== currentScene) {
    slides.forEach((slide, i) => { slide.hidden = i !== index; });
    chapterButtons.forEach((button, i) => {
      if (i === index) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    el("scene-label").textContent = scene.label;
    currentScene = index;
  }
  if (index === 0) {
    const [caseOne] = recordings;
    const cursor = reducedMotion.matches ? 10 : elapsed;
    drawTrace(el("ppg"), caseOne.ppg, caseOne.ppgHz, "#94f1dc", cursor);
    drawTrace(el("ecg"), caseOne.ecg, caseOne.ecgHz, "#ffb59f", cursor, caseOne.beats);
  }
  if (index === 1) cases.forEach((card, i) => card.classList.toggle("active", reducedMotion.matches || i === Number(elapsed >= 8.5)));
  if (index === 2) steps.forEach((step, i) => step.classList.toggle("active", reducedMotion.matches || i <= Math.floor(elapsed / 2.4)));
  if (index === 4) {
    el("countdown").firstChild.textContent = `${20 - Math.floor(elapsed)} `;
    el("capture-progress").style.width = `${Math.min(elapsed * 5, 100)}%`;
  }
  if (!seek.matches(":active")) seek.value = time;
  el("clock").textContent = `${formatTime(time)} / ${formatTime(duration)}`;
}

function jump(time) {
  audio.currentTime = time;
  render();
}
function showStatus(message) {
  status.hidden = !message;
  status.textContent = message;
}
function tick() {
  render();
  if (!audio.paused) frame = requestAnimationFrame(tick);
}

seek.max = duration;
seek.addEventListener("input", () => jump(seek.valueAsNumber));
play.addEventListener("click", async () => {
  if (!audio.paused) {
    audio.pause();
    return;
  }
  if (audio.ended || audio.currentTime >= duration) jump(0);
  try {
    showStatus("");
    await audio.play();
  } catch {
    showStatus("Narration could not play. Keep narration.mp3 beside this page.");
  }
});
audio.addEventListener("playing", () => {
  play.textContent = "Pause";
  cancelAnimationFrame(frame);
  tick();
});
audio.addEventListener("pause", () => {
  cancelAnimationFrame(frame);
  play.textContent = audio.ended ? "Replay" : "Play film";
  render();
});
audio.addEventListener("ended", () => {
  play.textContent = "Replay";
  render();
});
audio.addEventListener("seeked", render);
audio.addEventListener("error", () => showStatus("The narration file could not load."));
el("mute").addEventListener("click", (event) => {
  audio.muted = !audio.muted;
  event.currentTarget.setAttribute("aria-pressed", String(audio.muted));
  event.currentTarget.textContent = audio.muted ? "Unmute" : "Mute";
});
const player = document.querySelector(".player");
const fullscreen = el("fullscreen");
fullscreen.hidden = !document.fullscreenEnabled;
fullscreen.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await player.requestFullscreen();
  } catch {
    showStatus("Full screen is unavailable in this browser.");
  }
});
document.addEventListener("fullscreenchange", () => {
  fullscreen.textContent = document.fullscreenElement ? "Exit full screen" : "Full screen";
  render();
});
window.addEventListener("resize", render);
reducedMotion.addEventListener("change", render);
render();
