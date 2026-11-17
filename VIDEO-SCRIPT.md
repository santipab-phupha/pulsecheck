# PulseCheck demo video

Target runtime is **90 seconds**. Start on the signal explorer with **135021** selected and the ECG trace visible. Show the UI as you speak. The narration is in English.

| Time | On screen | Narration |
| --- | --- | --- |
| 0:00–0:13 | Click **Play** immediately. Show the playhead crossing the paired PPG and ECG traces. | “This is PulseCheck. The top trace is a real fingertip camera recording. The lower trace is the ECG captured alongside it. We want to know when a camera-based pulse estimate is worth showing.” |
| 0:13–0:27 | Highlight the three rates on **135021**, then select **136096** and show its orange error indicator. | “Here, the previous estimate was seventy-four. The latest is sixty-seven point six, closer to the ECG at sixty-five. In this second recording, our estimate stays more than nine beats per minute from ECG.” |
| 0:27–0:40 | Put the process on screen as text over the player. **PPG → Candidate rates → Signal checks → Show or retry** | “We score candidate rates from the waveform. A quality gate can request another capture. A spectral check helps select the final rate that gets displayed.” |
| 0:40–1:04 | Expand **Held-out results**. Enlarge the two version columns. Add **109 / 326 displayed readings outside ±5 bpm** below the table. | “We froze the pipeline and tested three hundred eighty-six recordings from six people kept out of development. Per hundred attempts, incorrect displayed readings went from twenty-eight point five to twenty-eight point two four. Unnecessary repeats stayed at five point one eight. One held-out estimate improved enough to pass, and a third of displayed estimates still fell outside tolerance.” |
| 1:04–1:18 | Click **Start Record** to show the camera prompt. Add **Experimental live camera** as a caption. | “The browser can also capture a fingertip signal directly from a phone camera. This path uses a separate experimental estimator. The results you just saw come from the locked pipeline on recorded data.” |
| 1:18–1:30 | Show the README and evaluation files. End on **PulseCheck** with the public repository link once available. | “We have shared the split, scoring code, and results so others can reproduce the evaluation. Next we will test live camera readings against ECG across phones and measure whether people get better readings after a retry.” |

## Recording notes

- Keep the two traces and the version values visible in the first 27 seconds. Use a tight crop on the held-out results during the numbers.
- Record the **Start Record** screen as a preview of the camera feature. If you include a successful measurement from a physical phone, label it as a live demonstration and keep the experimental caption visible.
- Use a legible caption for both **BUT PPG v2.0.0, PhysioNet, CC BY 4.0** and the repository link. Get consent before including an identifiable person.
- Before submitting, open the final video from a signed-out browser and make sure it plays in full. Paste the [Devpost description](SUBMISSION.md) into the project page and attach the public repository and video links. [Official rules](https://ai-for-medicine.devpost.com/rules)
