# PulseCheck

*A fingertip pulse research prototype that can ask for another measurement.*

## Problem

A phone camera offers a way to estimate pulse when a dedicated sensor is unavailable. But movement or weak contact can distort the signal and still produce a plausible number. PulseCheck explores when a smartphone pulse estimate has enough signal evidence to show and when it should ask for another measurement.

## What we built

PulseCheck combines adaptive peak detection with learned scoring based on waveform timing, spectral evidence, and signal slope. The pipeline estimates pulse from fingertip photoplethysmography (PPG). A quality gate can withhold an estimate and request a repeat. The latest version checks whether the PPG spectrum supports the chosen rate.

The interactive demo replays real synchronized PPG and ECG and shows the previous and latest estimates. It includes one example that improved and one still outside tolerance. A separate experimental camera mode reads a fingertip signal directly in the browser.

## Evaluation

We developed the pipeline on 1,540 recorded windows from 24 people in BUT PPG v2.0.0 and froze both variants before testing 386 ten-second windows from six other people. We calculated the reference rate from annotated ECG QRS intervals in the same window. We counted an estimate as wrong when it differed by more than 5 bpm.

Per 100 attempts, incorrect displayed estimates fell from **28.50 to 28.24**. Repeats on estimates already within tolerance stayed at **5.18 per 100** and all repeats stayed at **15.54 per 100**. One held-out estimate moved into tolerance. The latest version still missed tolerance on **109 of the 326 estimates it displayed**. The README links to the participant split, frozen settings, paired outputs, and reproduction instructions.

## Who benefits, and who could be harmed

People who want a quick pulse check and lack a dedicated sensor are the intended future users. A prompt to repeat a weak capture could help people avoid relying on a doubtful reading. A wrong displayed value could falsely reassure someone with an abnormal pulse or cause unnecessary concern. Frequent repeat requests could also make the feature difficult to use.

## Limitations

The held-out cohort contains six people with repeated recordings. This retrospective benchmark evaluated recorded fingertip signals and simulated repeat decisions. Clinical use, real-world repeat success, phone compatibility, and accuracy of the separate live camera feature remain unverified.

## What we would do with another month

Collect consented, paired phone and ECG measurements across several phone models and capture conditions. Predefine the participant split and scoring rules, then report error and retry rates by device and condition. Run an observed usability test to see whether people can get a better signal after a repeat prompt.

## Attribution

Data and annotations come from Andrea Nemcova and colleagues via PhysioNet. [BUT PPG v2.0.0](https://doi.org/10.13026/tn53-8153) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

OpenAI Codex assisted with analysis, code, and writing. OpenAI ImageGen generated the setup illustration. The repository documents dependencies and derived data.
