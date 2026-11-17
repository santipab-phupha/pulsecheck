import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = new URL("./", import.meta.url);
const scenes = JSON.parse(await readFile(new URL("scenes.json", dir), "utf8"));
const key = process.env.OPENAI_API_KEY;
if (!key) throw new Error("Set OPENAI_API_KEY in the environment.");

const scratch = await mkdtemp(join(tmpdir(), "pulsecheck-speech-"));
const model = "gpt-4o-mini-tts";
const voice = "marin";
function ffmpeg(args) {
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", ...args], { stdio: "inherit", cwd: scratch });
}
function duration(name) {
  return Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", name], { cwd: scratch, encoding: "utf8" }).trim());
}
try {
  // Generate clips independently so each scene can start on a narration boundary.
  const paths = await Promise.all(scenes.map(async (scene, index) => {
    const res = await fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model, voice, input: scene.narration, response_format: "wav",
        instructions: "Warm, clear demo narration in natural English at a steady pace. Pronounce PulseCheck as pulse check and E C G as three separate letters. Speak only the supplied text." }),
      signal: AbortSignal.timeout(60000),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(`OpenAI Speech returned HTTP ${res.status} (${detail.error?.code ?? "request failed"}).`);
    }
    const name = `speech-${index}.wav`;
    await writeFile(join(scratch, name), Buffer.from(await res.arrayBuffer()));
    return name;
  }));
  let start = 0;
  const timeline = scenes.map((scene, index) => {
    const actual = duration(paths[index]);
    const tempo = Math.max(1, actual / (scene.duration - 0.75));
    const output = `scene-${index}.wav`;
    ffmpeg(["-i", paths[index], "-af", `atempo=${tempo},adelay=250,apad`, "-t", String(scene.duration),
      "-ar", "24000", "-ac", "1", output]);
    const entry = { ...scene, start, end: start + scene.duration };
    start = entry.end;
    console.log(`Scene ${index + 1}: ${actual.toFixed(2)} s speech, ${scene.duration} s scene`);
    return entry;
  });
  await writeFile(join(scratch, "tracks.txt"), timeline.map((_, i) => `file scene-${i}.wav`).join("\n"));
  ffmpeg(["-f", "concat", "-safe", "0", "-i", "tracks.txt", "-codec:a", "libmp3lame", "-b:a", "96k", "narration.mp3"]);
  await writeFile(new URL("narration.mp3", dir), await readFile(join(scratch, "narration.mp3")));
  await writeFile(new URL("timeline.js", dir), `window.PULSECHECK_TIMELINE = ${JSON.stringify(timeline, null, 2)};\n`);
  console.log(`Exported ${start} seconds of OpenAI narration.`);
} finally {
  await rm(scratch, { recursive: true, force: true });
}
