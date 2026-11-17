# PulseCheck

PulseCheck is a research prototype that estimates pulse from a fingertip smartphone camera signal and can request a repeat when signal evidence is weak. The browser demo lets you compare two estimator versions against simultaneous ECG, including a case the latest version still misses.

## Run the demo

From this directory, with Node.js 24 and npm:

```sh
cd demo
npm ci
npm run typecheck
npm run dev
```

Open [PulseCheck on localhost](http://127.0.0.1:8769/). The demo uses two bundled recordings and runs without the full dataset or an API key. To build the static site, run `npm run build` from `demo`. Open `demo/dist/index.html` to replay recordings offline.

1. Play **135021** and compare **Previous**, **Latest**, and **ECG reference**. The latest estimate is 67.6 bpm against 65.0 bpm on ECG.
2. Switch to **136096** for a remaining error. The latest estimate is 72.7 bpm against 63.4 bpm on ECG.
3. Expand **Held-out results** for the six-person evaluation.

**Start Record** opens an experimental 20-second camera capture in a supported browser on HTTPS or localhost. The browser analyzes the color signal locally. The live camera estimator still needs phone and ECG validation. **Demo sensor** simulates pairing and replays recorded data.

## Method and evaluation

The evaluated pipeline forms candidate rates from adaptive PPG peaks and from periodicity and waveform slope. Gradient-boosted trees score the candidates. A development-only quality threshold decides whether to display a value, and the latest version adds a spectral support check before displaying it. ECG QRS annotations provide training labels and the scoring reference. Prediction uses PPG signals.

The final comparison used **386 ten-second fingertip windows from 6 held-out people**, with 1,540 windows from 24 other people for development. A displayed estimate was scored as incorrect if it differed by **more than 5 bpm** from the median instantaneous rate of the annotated ECG QRS intervals in the same window.

| Outcome per 100 attempts | Previous | Latest |
| --- | ---: | ---: |
| Incorrect displayed estimate | 28.50 | 28.24 |
| Repeat requested for an estimate within 5 bpm of ECG | 5.18 | 5.18 |
| All repeat requests | 15.54 | 15.54 |

The latest version moved one held-out result within tolerance. **109 of its 326 displayed estimates (33.4%)** still missed the scoring tolerance. See [Evaluation](EVALUATION.md) for the protocol, counts, and limitations.

## Reproduce the evaluation

Use Python **3.11.9** and the versions pinned in [requirements.txt](requirements.txt). Download the [BUT PPG v2.0.0 ZIP](https://physionet.org/content/butppg/get-zip/2.0.0/) into `data/butppg-2.0.0.zip` and run from the PulseCheck root:

```sh
python -m pip install -r requirements.txt
python reproduce.py
```

The dataset ZIP SHA-256 is `9b910fc884f63eca1c5d3a00c5710f838e0053dce94f8a02196bd0adc2ffa33c`. Use `--archive PATH` if you saved it elsewhere and `--output PATH` for a different fresh output directory. The runner checks the archive, environment, and frozen source hashes. It trains and locks the models in `reproduction/`, scores the held-out windows, and compares the resulting counts and transitions with the published report. The archived report and lock stay in `results/`.

## Credits

- Andrea Nemcova and colleagues provided [BUT PPG v2.0.0](https://doi.org/10.13026/tn53-8153) through PhysioNet under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- OpenAI Codex assisted with the analysis, implementation, interface, and submission writing. OpenAI ImageGen generated the phone setup illustration.

See [Credits and attribution](CREDITS.md) for the full citations, dependencies, and how the bundled waveforms were derived.

[Evaluation](EVALUATION.md) · [Development notes](DEVELOPMENT.md) · [Devpost description](SUBMISSION.md) · [Video script](VIDEO-SCRIPT.md) · [Narrated animation](animation/index.html)
