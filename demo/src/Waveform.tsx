import { memo, useEffect, useRef } from "react";

type WaveformProps = {
  values: readonly number[];
  hz: number;
  label?: string;
  color: string;
  beats?: readonly number[];
  thumbnail?: boolean;
};

export const DURATION = 10;

export const Waveform = memo(function Waveform({ values, hz, label, color, beats, thumbnail }: WaveformProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const surface = canvas;
    const ctx = context;

    function draw() {
      const { width, height } = surface.getBoundingClientRect();
      if (width <= 0 || height <= 0) return;
      const scale = window.devicePixelRatio || 1;
      surface.width = Math.round(width * scale);
      surface.height = Math.round(height * scale);
      ctx.scale(scale, scale);
      const x = (time: number) => time * width / DURATION;
      const y = (value: number) => height / 2 - value * (height / 2 - (thumbnail ? 4 : 9));

      if (!thumbnail) {
        ctx.lineWidth = 1;
        ctx.strokeStyle = "rgba(177,211,222,.16)";
        ctx.beginPath();
        for (let second = 0; second <= DURATION; second++) {
          ctx.moveTo(x(second), 0);
          ctx.lineTo(x(second), height);
        }
        for (const fraction of [0.25, 0.5, 0.75]) {
          ctx.moveTo(0, height * fraction);
          ctx.lineTo(width, height * fraction);
        }
        ctx.stroke();
      }

      ctx.lineWidth = thumbnail ? 1.1 : 1.75;
      ctx.lineJoin = "round";
      ctx.strokeStyle = color;
      ctx.beginPath();
      ctx.moveTo(0, y(values[0]));
      for (let i = 1; i < values.length; i++) ctx.lineTo(x(i / hz), y(values[i]));
      ctx.stroke();

      if (!beats) return;
      ctx.fillStyle = color;
      for (const beat of beats) {
        const index = Math.min(values.length - 1, Math.round(beat * hz));
        ctx.beginPath();
        ctx.arc(x(beat), y(values[index]), 2.6, 0, 2 * Math.PI);
        ctx.fill();
      }
    }

    const observer = new ResizeObserver(draw);
    observer.observe(surface);
    draw();
    return () => observer.disconnect();
  }, [values, hz, color, beats, thumbnail]);

  return (
    <canvas
      ref={ref}
      className={thumbnail ? "mini-wave" : "waveform"}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={!label}
    />
  );
});
