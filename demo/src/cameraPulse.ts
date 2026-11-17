export type CameraSample = { time: number; red: number; green: number; blue: number };
export type CameraEstimate = { bpm: number; quality: number };

const SAMPLE_RATE = 15;
const MIN_FREQUENCY = 0.75;
const MAX_FREQUENCY = 3;

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function spectrum(values: number[]) {
  const windowSize = Math.round(1.5 * SAMPLE_RATE);
  const detrended = values.map((value, index) => {
    const start = Math.max(0, index - windowSize);
    const end = Math.min(values.length, index + windowSize + 1);
    let average = 0;
    for (let i = start; i < end; i++) average += values[i];
    return value - average / (end - start);
  });
  let bestFrequency = 0;
  let bestPower = 0;
  let totalPower = 0;
  const bins: { frequency: number; power: number }[] = [];
  for (let frequency = MIN_FREQUENCY; frequency <= MAX_FREQUENCY + 0.001; frequency += 0.01) {
    let real = 0;
    let imaginary = 0;
    for (let i = 0; i < detrended.length; i++) {
      const window = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (detrended.length - 1));
      const phase = 2 * Math.PI * frequency * i / SAMPLE_RATE;
      real += detrended[i] * window * Math.cos(phase);
      imaginary -= detrended[i] * window * Math.sin(phase);
    }
    const power = real * real + imaginary * imaginary;
    bins.push({ frequency, power });
    totalPower += power;
    if (power > bestPower) {
      bestPower = power;
      bestFrequency = frequency;
    }
  }
  const nearbyPower = bins.reduce((sum, bin) => sum + (Math.abs(bin.frequency - bestFrequency) <= 0.15 ? bin.power : 0), 0);
  return { frequency: bestFrequency, concentration: nearbyPower / Math.max(totalPower, 1e-12) };
}

/** Experimental camera estimate. This runs independently of the frozen research model. */
export function estimateCameraPulse(samples: CameraSample[]): CameraEstimate | null {
  if (samples.length < 100 || samples.some(sample =>
    !Number.isFinite(sample.time) || !Number.isFinite(sample.red) ||
    !Number.isFinite(sample.green) || !Number.isFinite(sample.blue)
  )) return null;

  const first = samples[0].time;
  const duration = samples[samples.length - 1].time - first;
  if (duration < 12 || duration > 35) return null;
  const gaps = samples.slice(1).map((sample, index) => sample.time - samples[index].time);
  if (gaps.some(gap => gap <= 0 || gap > 0.5) || median(gaps) > 0.125) return null;

  const red = median(samples.map(sample => sample.red));
  const green = median(samples.map(sample => sample.green));
  const blue = median(samples.map(sample => sample.blue));
  // A fingertip over the lens produces a red-dominant image. Fully clipped frames
  // or a scene without lens coverage cannot provide a meaningful pulse waveform.
  if (red < 40 || red > 253.5 || red < green * 1.08 || red < blue * 1.08) return null;

  const values: number[] = [];
  let index = 0;
  for (let time = first; time <= samples[samples.length - 1].time; time += 1 / SAMPLE_RATE) {
    while (index + 1 < samples.length && samples[index + 1].time < time) index++;
    const left = samples[index];
    const right = samples[Math.min(index + 1, samples.length - 1)];
    const weight = right.time === left.time ? 0 : (time - left.time) / (right.time - left.time);
    values.push(left.red + weight * (right.red - left.red));
  }
  const center = median(values);
  const amplitude = median(values.map(value => Math.abs(value - center)));
  if (amplitude < 0.08 || amplitude > 30) return null;

  const whole = spectrum(values);
  const firstHalf = spectrum(values.slice(0, Math.floor(values.length / 2)));
  const secondHalf = spectrum(values.slice(Math.floor(values.length / 2)));
  const agreement = Math.max(
    Math.abs(whole.frequency - firstHalf.frequency),
    Math.abs(whole.frequency - secondHalf.frequency),
  );
  if (whole.concentration < 0.45 || firstHalf.concentration < 0.35 ||
      secondHalf.concentration < 0.35 || agreement > 0.2) return null;

  return { bpm: Math.round(whole.frequency * 600) / 10, quality: whole.concentration };
}
