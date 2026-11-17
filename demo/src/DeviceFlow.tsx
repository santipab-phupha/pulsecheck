import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Recording } from "./SignalExplorer";
import { DURATION, Waveform } from "./Waveform";

export function Panel({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return <dialog className="device-dialog" ref={ref} aria-labelledby="panel-title" onCancel={e => { e.preventDefault(); onClose(); }}>
    <header className="dialog-head"><h2 id="panel-title">{title}</h2><button type="button" className="close-btn" aria-label="Close panel" onClick={onClose}>×</button></header>
    {children}
  </dialog>;
}

type PairStage = "scan" | "found" | "pairing" | "ready";

export function DeviceFlow({ known, connected, onPair, onDisconnect, onCapture, onClose }: {
  known: boolean; connected: boolean; onPair: () => void; onDisconnect: () => void; onCapture: () => void; onClose: () => void;
}) {
  const [stage, setStage] = useState<PairStage>(connected ? "ready" : known ? "found" : "scan");
  useEffect(() => {
    if (stage === "scan") {
      const timer = window.setTimeout(() => setStage("found"), 1000);
      return () => clearTimeout(timer);
    }
    if (stage === "pairing") {
      const timer = window.setTimeout(() => { onPair(); setStage("ready"); }, 850);
      return () => clearTimeout(timer);
    }
  }, [stage, onPair]);

  const status = { scan: "Searching for demo sensor…", found: known ? "Saved demo sensor" : "Demo sensor found", pairing: "Pairing demo sensor…", ready: "Demo sensor connected" }[stage];
  const busy = stage === "scan" || stage === "pairing";
  return <Panel title="Sensor connection" onClose={onClose}>
    <div className={`radar ${busy ? "scanning" : ""}`} aria-hidden="true"><div className="radar-phone"><i /></div></div>
    <div className="dialog-body">
      <p className="device-status" role="status"><i />{status}</p>
      <h3>Fingertip camera</h3><p className="subcopy">Virtual sensor · Recorded PPG + ECG</p>
      {stage === "found" && <button className="action" onClick={() => setStage("pairing")}>{known ? "Reconnect sensor" : "Pair sensor"}</button>}
      {busy && <button className="action pending" disabled>{stage === "scan" ? "Searching…" : "Pairing…"}</button>}
      {stage === "ready" && <><button className="action" onClick={onCapture}>Start 10-second session</button><button className="quiet" onClick={onDisconnect}>Disconnect sensor</button></>}
    </div>
  </Panel>;
}

export function Capture({ record, onSave, onClose }: { record: Recording; onSave: () => void; onClose: () => void }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const timer = window.setInterval(() => {
      const seconds = Math.min(DURATION, (performance.now() - start) / 1000);
      setElapsed(seconds);
      if (seconds === DURATION) clearInterval(timer);
    }, 50);
    return () => clearInterval(timer);
  }, []);
  const done = elapsed === DURATION;
  const error = Math.abs(record.latestBpm - record.ecgBpm);
  return <Panel title={done ? "Session complete" : "Recording replay"} onClose={onClose}>
    <div className="capture-view">
      <div className="capture-meta"><span>PPG · {record.id}</span><span>{Math.floor(elapsed)} / {DURATION} s</span></div>
      <div className="capture-trace" style={{clipPath: `inset(0 ${100 * (1 - elapsed / DURATION)}% 0 0)`}}>
        <Waveform values={record.ppg} hz={record.ppgHz} color="#91eff0" label="Replayed fingertip pulse waveform" />
      </div>
    </div>
    <div className="dialog-body">
      {done ? <><p className="subcopy">Latest estimate</p><h3 className="session-bpm">{record.latestBpm.toFixed(1)} <small>bpm</small></h3>
        <p className="subcopy">ECG {record.ecgBpm.toFixed(1)} bpm · {error.toFixed(1)} bpm difference</p>
        <button className="action" onClick={onSave}>Save to sessions</button></>
      : <><h3>Reading the sample</h3><p className="subcopy">Replaying 10 seconds from the paired demo sensor.</p><button className="quiet" onClick={onClose}>Cancel session</button></>}
    </div>
  </Panel>;
}
