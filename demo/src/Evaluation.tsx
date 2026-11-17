import summary from "../../results/final-holdout-summary.json";

const metrics = [
  ["Wrong reading shown (>5 bpm from ECG)", "show_bad"],
  ["Repeat requested within 5 bpm of ECG", "retry_good"],
  ["All repeats", "retry_total"],
] as const;

export function Evaluation() {
  const { counts, per_100: rates } = summary;
  const shown = counts.latest.show_good + counts.latest.show_bad;
  return <details className="evaluation">
    <summary><strong>Held-out results</strong><span className="sample">{summary.people} people · {summary.records} attempts</span><span className="expand" aria-hidden="true" /></summary>
    <div className="eval-content">
      <table><caption>Per 100 attempts</caption>
        <thead><tr><th scope="col">Outcome</th><th scope="col">Previous</th><th scope="col">Latest</th></tr></thead>
        <tbody>{metrics.map(([label, key]) => <tr key={key}><th scope="row">{label}</th><td>{rates.previous[key].toFixed(2)}</td><td>{rates.latest[key].toFixed(2)}</td></tr>)}</tbody>
      </table>
      <p>Models and threshold locked before testing. Of {shown} readings shown by the latest version, {counts.latest.show_bad} differed from ECG by more than 5 bpm.</p>
    </div>
  </details>;
}
