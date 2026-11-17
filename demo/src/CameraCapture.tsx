import { useEffect, useRef, useState } from "react";
import { estimateCameraPulse } from "./cameraPulse";

type Sample = { time: number; red: number; green: number; blue: number };
type Stage = "ready" | "requesting" | "recording" | "result" | "retry" | "error";

export function CameraCapture({ onClose }: { onClose: () => void }) {
  const [stage, setStage] = useState<Stage>("ready");
  const [elapsed, setElapsed] = useState(0);
  const [bpm, setBpm] = useState<number | null>(null);
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const animation = useRef<number | null>(null);
  const session = useRef(0);

  function stop() {
    session.current += 1;
    if (animation.current !== null) cancelAnimationFrame(animation.current);
    animation.current = null;
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
  }

  useEffect(() => () => stop(), []);

  async function start() {
    stop();
    const currentSession = session.current;
    setStage("requesting");
    setElapsed(0);
    setBpm(null);
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Camera access needs HTTPS or localhost. Open this page over a secure connection.");
      setStage("error");
      return;
    }
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 320 }, height: { ideal: 240 } },
        audio: false,
      });
      if (session.current !== currentSession || !video.current) {
        media.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = media;
      const track = media.getVideoTracks()[0];
      track.onended = () => {
        if (session.current !== currentSession) return;
        stop();
        setError("Camera disconnected. Try again.");
        setStage("error");
      };
      const capabilities = track.getCapabilities?.() as MediaTrackCapabilities & { torch?: boolean } | undefined;
      if (capabilities?.torch) {
        try {
          await track.applyConstraints({ advanced: [{ torch: true } as MediaTrackConstraintSet] });
        } catch {
          // Some cameras report a torch but do not allow the browser to enable it.
        }
      }
      if (session.current !== currentSession || !video.current) return;
      video.current.srcObject = media;
      await video.current.play();
      if (session.current !== currentSession) return;

      const context = canvas.current?.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("Unable to read camera frames.");
      const samples: Sample[] = [];
      let startTime: number | null = null;
      let lastVideoTime = -1;
      setStage("recording");

      function sample(now: number) {
        if (session.current !== currentSession) return;
        const currentVideo = video.current;
        if (!currentVideo) return;
        if (startTime === null) startTime = now;
        const seconds = (now - startTime) / 1000;
        setElapsed(Math.min(20, seconds));
        if (currentVideo.readyState >= 2 && currentVideo.currentTime !== lastVideoTime) {
          lastVideoTime = currentVideo.currentTime;
          const width = currentVideo.videoWidth;
          const height = currentVideo.videoHeight;
          const crop = Math.min(width, height) * 0.5;
          if (crop > 0) {
            context!.drawImage(currentVideo, (width - crop) / 2, (height - crop) / 2, crop, crop, 0, 0, 32, 32);
            const data = context!.getImageData(0, 0, 32, 32).data;
            let red = 0, green = 0, blue = 0;
            for (let i = 0; i < data.length; i += 4) {
              red += data[i];
              green += data[i + 1];
              blue += data[i + 2];
            }
            samples.push({ time: seconds, red: red / 1024, green: green / 1024, blue: blue / 1024 });
          }
        }
        if (seconds >= 20) {
          const estimate = estimateCameraPulse(samples);
          stop();
          if (estimate) {
            setBpm(Math.round(estimate.bpm));
            setStage("result");
          } else {
            setStage("retry");
          }
          return;
        }
        animation.current = requestAnimationFrame(sample);
      }
      animation.current = requestAnimationFrame(sample);
    } catch (exception) {
      if (session.current !== currentSession) return;
      stop();
      const name = exception instanceof DOMException ? exception.name : "";
      setError(name === "NotAllowedError" ? "Camera permission was denied. Allow camera access in your browser settings."
        : name === "NotFoundError" ? "No camera was found on this device."
        : "Could not start the camera. Check camera permissions and try again.");
      setStage("error");
    }
  }

  const active = stage === "requesting" || stage === "recording";
  return <section className="camera-capture" aria-label="Live camera measurement">
    <div className="camera-preview">
      <video ref={video} autoPlay muted playsInline aria-label="Camera preview" />
      <canvas ref={canvas} width={32} height={32} hidden />
      <div className="camera-overlay">
        {stage === "recording" ? <><span className="camera-live"><i />LIVE CAMERA</span><strong>{Math.max(0, 20 - Math.floor(elapsed))}<small> sec</small></strong><span>Keep your fingertip still</span></>
          : <><span className="camera-live">CAMERA MEASUREMENT</span><strong>{stage === "result" && bpm !== null ? <>{bpm}<small> bpm</small></> : "20 sec"}</strong>
            <span>{stage === "result" ? "Experimental estimate" : "Cover your rear camera with your fingertip"}</span></>}
      </div>
    </div>
    <div className="camera-content">
      <div className="camera-progress" role="progressbar" aria-label="Measurement progress" aria-valuemin={0} aria-valuemax={20} aria-valuenow={Math.floor(elapsed)}><span style={{ width: `${Math.min(100, elapsed * 5)}%` }} /></div>
      {stage === "ready" && <p>Place your fingertip over the rear camera. Keep your hand still and allow camera access.</p>}
      {stage === "requesting" && <p role="status">Opening camera…</p>}
      {stage === "recording" && <p role="status">Measuring the light changes in the camera image.</p>}
      {stage === "result" && <p>Based on this camera recording. This live estimator is experimental and has not been validated against ECG.</p>}
      {stage === "retry" && <p role="status">The signal was unclear. Cover the camera fully, hold still, and try again.</p>}
      {stage === "error" && <p role="alert">{error}</p>}
      <div className="camera-actions">
        {active ? <button className="quiet" onClick={() => { stop(); setStage("ready"); }}>Cancel</button>
          : <button className="action" onClick={start}>{stage === "ready" ? "Allow camera & start" : "Measure again"}</button>}
        <button className="quiet" onClick={() => { stop(); onClose(); }}>Close</button>
      </div>
    </div>
  </section>;
}
