import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Evaluation } from "./Evaluation";
import { Capture, DeviceFlow, Panel } from "./DeviceFlow";
import { CameraCapture } from "./CameraCapture";
import { SignalExplorer, type Recording } from "./SignalExplorer";
import "./styles.css";
import "./session.css";

declare global {
  interface Window { PULSECHECK_DATA?: { cases: Recording[] } }
}

type SavedSession = { id: string; caseId: string; time: number };
type View = "device" | "capture" | "history" | "camera" | null;
const recordings = window.PULSECHECK_DATA?.cases ?? [];
const sessionKey = "pulsecheck.sessions.v1";

function read(key: string) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function store(key: string, value: string) {
  try { localStorage.setItem(key, value); return true; } catch { return false; }
}
function readHistory(): SavedSession[] {
  try {
    const items: unknown = JSON.parse(read(sessionKey) ?? "[]");
    if (!Array.isArray(items)) return [];
    return items.filter(item => item && typeof item.id === "string" && Number.isFinite(item.time)
      && recordings.some(record => record.id === item.caseId));
  } catch { return []; }
}

function App() {
  const [welcome, setWelcome] = useState(() => !read("pulsecheck.visited"));
  const [known, setKnown] = useState(() => !!read("pulsecheck.paired"));
  const [connected, setConnected] = useState(false);
  const [view, setView] = useState<View>(null);
  const [caseId, setCaseId] = useState("135021");
  const [history, setHistory] = useState(readHistory);
  const [notice, setNotice] = useState("");
  const record = recordings.find(item => item.id === caseId) ?? recordings[0];
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3500);
    return () => clearTimeout(timer);
  }, [notice]);

  function finishWelcome() {
    setWelcome(false);
    store("pulsecheck.visited", "1");
  }
  const pair = useCallback(() => {
    setConnected(true);
    setKnown(true);
    store("pulsecheck.paired", "1");
    finishWelcome();
  }, []);
  function save() {
    const entry = { id: crypto.randomUUID(), time: Date.now(), caseId: record.id };
    const entries = [...new Map([...history, ...readHistory(), entry].map(item => [item.id, item])).values()].sort((a,b) => b.time - a.time);
    setHistory(entries);
    const persisted = store(sessionKey, JSON.stringify(entries));
    setView("history");
    setNotice(persisted ? "Session saved" : "Session saved for this visit");
  }
  function openHistory() {
    const stored = readHistory();
    if (stored.length) setHistory(stored);
    setView("history");
  }
  return <>
    <header className="mast"><div className="wrap mast-inner">
      <a href="#top" className="brand"><span className="brand-mark" aria-hidden="true">∿</span>PulseCheck</a>
      <nav className="tools" aria-label="Workspace">
        <button onClick={openHistory}>Sessions{history.length > 0 && <span className="count">{history.length}</span>}</button>
        {record && <button className={`device-pill ${connected ? "online" : ""}`} onClick={() => setView("device")}><i />{connected ? "Demo connected" : "Demo sensor"}</button>}
      </nav>
    </div></header>
    <main className="wrap" id="top">
      {welcome && record && <section className="welcome" aria-labelledby="welcome-title">
        <img src="./measurement-setup.png" alt="Illustration of fingertip camera placement" />
        <div className="welcome-copy"><span className="welcome-label">Sensor setup</span>
          <h1 id="welcome-title">Your first pulse session.</h1>
          <p>Use your phone camera or explore recorded signals.</p>
          <div className="welcome-actions"><button className="action" onClick={() => setView("camera")}>Measure with camera <span aria-hidden="true">→</span></button><button className="text-btn" onClick={() => setView("device")}>Connect demo sensor</button>
            <button className="text-btn" onClick={finishWelcome}>Browse recordings</button></div>
        </div>
      </section>}
      <header className="page-title">{welcome ? <h2>Signal explorer</h2> : <h1>Signal explorer</h1>}
        {connected ? <button className="session-launch" onClick={() => setView("capture")}>Start demo session <span aria-hidden="true">→</span></button> : <span>Fingertip PPG / ECG</span>}
      </header>
      {record ? <SignalExplorer recordings={recordings} active={record} select={setCaseId} showPhoto={!welcome} suspended={view !== null} startRecord={() => setView("camera")} /> : <p role="alert">Recordings could not load. Open the demo from its original folder.</p>}
      <Evaluation />
      <footer className="source-footer"><span>Research demo</span><a className="dataset" href="https://physionet.org/content/butppg/2.0.0/">BUT PPG dataset ↗</a></footer>
    </main>
    {view === "camera" && <Panel title="Measure pulse" onClose={() => setView(null)}><CameraCapture onClose={() => setView(null)} /></Panel>}
    {view === "device" && <DeviceFlow known={known} connected={connected} onPair={pair} onClose={() => setView(null)}
      onDisconnect={() => { setConnected(false); setView(null); setNotice("Demo sensor disconnected"); }}
      onCapture={() => setView("capture")} />}
    {view === "capture" && connected && record && <Capture record={record} onClose={() => setView(null)} onSave={save} />}
    {view === "history" && <Panel title="Saved demo sessions" onClose={() => setView(null)}>
      <div className="dialog-body history"><p className="subcopy">{history.length ? "Demo replays saved in this browser." : "Your saved demo replays will appear here."}</p>
        {history.length === 0 && record && <button className="action" onClick={() => setView(connected ? "capture" : "device")}>Start a demo session</button>}
        {history.map(item => {
          const saved = recordings.find(r => r.id === item.caseId)!;
          return <button className="session-row" key={item.id} onClick={() => { setCaseId(item.caseId); setView(null); document.querySelector(".page-title")?.scrollIntoView({block:"start"}); }}>
            <span><b>Case {item.caseId}</b><small>{new Date(item.time).toLocaleString("en", { month:"short", day:"numeric", hour:"numeric", minute:"2-digit" })}</small></span>
            <span>{saved.latestBpm.toFixed(1)} bpm <span aria-hidden="true">↗</span></span>
          </button>;
        })}
      </div></Panel>}
    <div className={notice ? "toast visible" : "toast"} role="status">{notice}</div>
  </>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
