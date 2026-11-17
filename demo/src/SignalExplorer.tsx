import { useCallback, useEffect, useRef, useState } from "react";
import { DURATION, Waveform } from "./Waveform";

export type Recording = {
  id: string;
  previousBpm: number;
  latestBpm: number;
  ecgBpm: number;
  ppg: number[];
  ppgHz: number;
  ecg: number[];
  ecgHz: number;
  beats: number[];
};

const TOLERANCE = 5;
const PPG_COLOR = "#91eff0";
const ECG_COLOR = "#ffb4a2";

function usePlayback() {
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const current = useRef(0);
  const frame = useRef<number | null>(null);
  const started = useRef(0);

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
  }, []);

  const pause = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    setPlaying(false);
  }, []);

  function seek(time: number) {
    current.current = time;
    setPosition(time);
    if (time === DURATION) pause();
    else if (frame.current !== null) started.current = performance.now() - time * 1000;
  }

  function toggle() {
    if (frame.current !== null) {
      pause();
      return;
    }
    if (current.current === DURATION) seek(0);
    started.current = performance.now() - current.current * 1000;
    setPlaying(true);
    function tick(now: number) {
      current.current = Math.min(DURATION, (now - started.current) / 1000);
      setPosition(current.current);
      if (current.current === DURATION) pause();
      else frame.current = requestAnimationFrame(tick);
    }
    frame.current = requestAnimationFrame(tick);
  }

  return { position, playing, pause, seek, toggle };
}

function withinTolerance(record: Recording) {
  return Math.abs(record.latestBpm - record.ecgBpm) <= TOLERANCE;
}

function Player({ record, suspended }: { record: Recording; suspended: boolean }) {
  const [showEcg, setShowEcg] = useState(true);
  const { position, playing, seek, toggle, pause } = usePlayback();
  useEffect(() => { if (suspended) pause(); }, [suspended, pause]);
  const difference = Math.abs(record.latestBpm - record.ecgBpm);
  return <section className="monitor" aria-label={`Recorded signals for case ${record.id}`}>
    <header className="monitor-head"><h2>Case <b>{record.id}</b></h2>
      <button className="ecg-toggle" aria-pressed={showEcg} aria-controls="ecg-track" onClick={() => setShowEcg(!showEcg)}>
        ECG trace <span className="switch" aria-hidden="true" />
      </button>
    </header>
    <div className="plot-area">
      <div className="tracks">
        <div className="track"><span className="channel">PPG</span>
          <Waveform values={record.ppg} hz={record.ppgHz} color={PPG_COLOR} label="Recorded fingertip PPG waveform" />
        </div>
        <div className="track ecg" id="ecg-track" hidden={!showEcg}><span className="channel">ECG</span>
          {showEcg && <Waveform values={record.ecg} hz={record.ecgHz} beats={record.beats} color={ECG_COLOR} label="Simultaneous ECG with annotated QRS beats" />}
        </div>
        <div className="cursor" style={{left: `${100 * position / DURATION}%`}} aria-hidden="true" />
      </div>
      <div className="axis" aria-hidden="true">{[0,2,4,6,8,10].map(n => <span key={n}>{n} s</span>)}</div>
    </div>
    <div className="transport">
      <button className="play" onClick={toggle}><i className={playing ? "pause-icon" : "play-icon"} aria-hidden="true" />
        {playing ? "Pause" : position === DURATION ? "Replay" : "Play"}
      </button>
      <input type="range" min={0} max={DURATION} step={0.01} value={position} aria-label="Playback position in seconds" onChange={e => seek(e.currentTarget.valueAsNumber)} />
      <output className="timer" aria-live="off">{position.toFixed(1)} / 10 s</output>
    </div>
    <dl className="metrics">
      <div className="latest"><dt>Latest</dt><dd>{record.latestBpm.toFixed(1)} <small>bpm</small></dd></div>
      <div><dt>Previous</dt><dd>{record.previousBpm.toFixed(1)} <small>bpm</small></dd></div>
      <div><dt>ECG reference</dt><dd>{record.ecgBpm.toFixed(1)} <small>bpm</small></dd></div>
    </dl>
    <p className={`verdict ${withinTolerance(record) ? "" : "miss"}`}><i aria-hidden="true" />
      Latest is {difference.toFixed(1)} bpm from ECG <span>±5 bpm tolerance</span>
    </p>
  </section>;
}

export function SignalExplorer({ recordings, active, select, showPhoto, suspended, startRecord }: {
  recordings: Recording[]; active: Recording; select: (id: string) => void; showPhoto: boolean; suspended: boolean; startRecord: () => void;
}) {
  return <div className="workspace">
    <Player key={active.id} record={active} suspended={suspended} />
    <aside className={showPhoto ? "library" : "library no-photo"} aria-labelledby="library-title">
      {showPhoto && <figure><img src="./measurement-setup.png" alt="Illustration of a fingertip over a phone camera" /><figcaption>Fingertip camera setup</figcaption></figure>}
      <div className="library-body"><h2 id="library-title">Recordings</h2><p>Development set</p>
        <div className="case-list">{recordings.map(record => {
          const good = withinTolerance(record);
          return <button key={record.id} className="case-card" aria-pressed={active.id === record.id} onClick={() => select(record.id)}>
            <span className="case-info"><b>{record.id}</b><span>{good ? "Within tolerance" : "Outside tolerance"}</span></span>
            <Waveform values={record.ppg} hz={record.ppgHz} color={good ? "#167375" : "#ac5d45"} thumbnail />
          </button>;
        })}</div>
        <button className="action start-record" onClick={startRecord}>Start Record</button>
      </div>
    </aside>
  </div>;
}
