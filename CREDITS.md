# Credits and attribution

## Data

- Nemcova, A., Smisek, R., Vargova, E., Maršánová, L., Vitek, M., Smital, L., Filipenska, M., Sikorova, P., & Gálík, P. (2024). *Brno University of Technology Smartphone PPG Database (BUT PPG), v2.0.0*. PhysioNet. [Dataset DOI](https://doi.org/10.13026/tn53-8153)
- Nemcova, A., Vargova, E., Smisek, R., Marsanova, L., Smital, L., & Vitek, M. (2021). *Brno University of Technology Smartphone PPG Database (BUT PPG): Annotated Dataset for PPG Quality Assessment and Heart Rate Estimation*. [Dataset paper](https://doi.org/10.1155/2021/3453007)
- PhysioNet provides the archive. [PhysioNet citation](https://doi.org/10.1038/s44360-026-00096-z)

PhysioNet lists the dataset under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). The bundled example traces are derived from original recordings **135021** and **136096**. PulseCheck selects the red channel, filters and scales the display traces, and resamples the filtered ECG for plotting. The replay retains the aligned QRS marks and includes derived bpm estimates. The evaluation CSVs and plots contain derived data and measurements. See [export_demo_data.py](export_demo_data.py) for the exact display transformation.

## Software and models

The evaluation uses [NumPy](https://numpy.org/), [SciPy](https://scipy.org/), [scikit-learn](https://scikit-learn.org/), [Matplotlib](https://matplotlib.org/), and [threadpoolctl](https://github.com/joblib/threadpoolctl). PulseCheck fits its gradient-boosted models on the development partition using scikit-learn. Versions are pinned in [requirements.txt](requirements.txt).

The web demo uses [React and React DOM](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped) type definitions, [esbuild](https://esbuild.github.io/), and [Node.js](https://nodejs.org/). [package-lock.json](demo/package-lock.json) records the frontend dependency versions and sources.

## AI assistance

OpenAI Codex assisted with research code, signal processing, visualizations, frontend development, verification, documentation, and preparation of the submission materials. OpenAI ImageGen generated the [fingertip setup illustration](demo/assets/measurement-setup.png). The PPG and ECG waveforms come from the cited dataset.

OpenAI’s Speech API generated the English narration for the [demo film](animation/index.html) using the Marin voice. [Text to speech guide](https://developers.openai.com/api/docs/guides/text-to-speech)
