import { checkOffline } from "./offline-math";
import { useState } from "react";

const pack = [
  {
    text: "1/2 + 1/3",
    n: 5n,
    d: 6n,
    hint: "Use sixths as the common denominator.",
  },
  {
    text: "3/4 − 1/6",
    n: 7n,
    d: 12n,
    hint: "Use twelfths as the common denominator.",
  },
  {
    text: "2/3 × 3/4",
    n: 1n,
    d: 2n,
    hint: "Multiply numerators and denominators, then simplify.",
  },
  {
    text: "3/5 ÷ 2/3",
    n: 9n,
    d: 10n,
    hint: "Multiply by the reciprocal of the second fraction.",
  },
  {
    text: "Simplify 8/12",
    n: 2n,
    d: 3n,
    hint: "Divide numerator and denominator by their common factor.",
  },
  {
    text: "2x + 3 = 11",
    n: 4n,
    d: 1n,
    hint: "Subtract 3 from both sides, then divide by 2.",
  },
];
export function OfflinePractice() {
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [message, setMessage] = useState("");
  const [hint, setHint] = useState(false);
  const problem = pack[index] ?? pack[0];
  if (!problem) return null;
  return (
    <details className="offline-pack">
      <summary>Public offline practice pack</summary>
      <p>
        Six original exercises run entirely on this device. There is no AI,
        saved learner history, synchronization, or server-verified progress in
        this mode.
      </p>
      <h2>{problem.text}</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setMessage(checkOffline(answer, problem.n, problem.d));
        }}
      >
        <label>
          Offline answer
          <input
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            maxLength={128}
          />
        </label>
        <div className="actions">
          <button>Check on this device</button>
          <button type="button" onClick={() => setHint(true)}>
            Show built-in hint
          </button>
          <button
            type="button"
            onClick={() => {
              setIndex((index + 1) % pack.length);
              setAnswer("");
              setMessage("");
              setHint(false);
            }}
          >
            Next public exercise
          </button>
        </div>
      </form>
      {hint && <p>{problem.hint}</p>}
      <p role="status">{message}</p>
    </details>
  );
}
