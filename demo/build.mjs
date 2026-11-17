import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build, context } from "esbuild";

const directory = fileURLToPath(new URL(".", import.meta.url));
const resolve = (path) => new URL(path, import.meta.url);
await mkdir(resolve("dist/"), { recursive: true });
await Promise.all([
  copyFile(resolve("index.html"), resolve("dist/index.html")),
  copyFile(resolve("assets/measurement-setup.png"), resolve("dist/measurement-setup.png")),
  copyFile(resolve("assets/recordings.js"), resolve("dist/data.js")),
]);

const options = {
  absWorkingDir: directory,
  entryPoints: { app: "src/main.tsx" },
  outdir: "dist",
  bundle: true,
  format: "iife",
  target: ["es2022"],
  minify: true,
  logLevel: "info",
};

if (process.argv.includes("--serve")) {
  const dev = await context(options);
  await dev.watch();
  const server = await dev.serve({ host: "127.0.0.1", port: 8769, servedir: "dist" });
  console.log(`PulseCheck at http://127.0.0.1:${server.port}/`);
} else {
  await build(options);
}
