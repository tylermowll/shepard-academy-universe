import { useEffect, useRef, useState } from "react";
import { api, type Schema } from "./client";
import { SafeText } from "./SafeText";

type Props = {
  session: Schema<"TutoringSessionPublic">;
  offline: boolean;
  disabled: boolean;
  active: boolean;
  act: (action: () => Promise<void>) => Promise<void>;
  refresh: () => Promise<void>;
};

export function TutorConversation(props: Props) {
  const { session, active } = props;
  const viewport = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const previousSession = useRef("");
  const [atBottom, setAtBottom] = useState(true);
  const revision = session.problems
    .flatMap((problem) =>
      problem.operations.map((item) => `${item.id}:${item.status}`),
    )
    .join("|");
  useEffect(() => {
    if (!active || !viewport.current) return;
    if (follow.current || previousSession.current !== session.id)
      viewport.current.scrollTop = viewport.current.scrollHeight;
    previousSession.current = session.id;
  }, [active, revision, session.id]);

  return (
    <div className="conversation-frame">
      <div
        ref={viewport}
        className="conversation-scroll"
        role="log"
        aria-label="Learning conversation"
        aria-live="polite"
        aria-relevant="additions text"
        tabIndex={0}
        onScroll={(event) => {
          const node = event.currentTarget;
          follow.current =
            node.scrollHeight - node.scrollTop - node.clientHeight < 72;
          setAtBottom(follow.current);
        }}
      >
        {session.problems.map((problem, index) => (
          <section
            key={problem.id}
            aria-label={`Activity ${index + 1} conversation`}
          >
            {problem.status !== "assigned" && (
              <details className="conversation-activity">
                <summary>Earlier activity {index + 1}</summary>
                <SafeText text={problem.problem_text} />
              </details>
            )}
            {problem.operations.map((operation) => (
              <TutorMessage
                key={operation.id}
                {...props}
                operation={operation}
              />
            ))}
          </section>
        ))}
        {!session.problems.some((problem) =>
          problem.operations.some((item) => item.kind !== "generation"),
        ) && (
          <p className="conversation-empty">
            Send your work or ask a question. Photos and replies stay together
            here.
          </p>
        )}
      </div>
      {!atBottom && (
        <button
          className="conversation-latest"
          onClick={() => {
            follow.current = true;
            if (viewport.current)
              viewport.current.scrollTop = viewport.current.scrollHeight;
            setAtBottom(true);
          }}
        >
          Latest messages ↓
        </button>
      )}
    </div>
  );
}

function TutorMessage({
  operation,
  offline,
  disabled,
  act,
  refresh,
}: Props & {
  operation: Schema<"OperationPublic">;
}) {
  const reading = operation.reading;
  const feedback = operation.feedback;
  const ambiguities = operation.ambiguities ?? [];
  // The backend owns whether a reading may advance. Localized uncertainty can
  // coexist with usable evidence; do not reconstruct a stricter frontend gate.
  const rejected = Boolean(reading && !reading.can_continue);
  if (operation.kind === "generation" && operation.status === "completed")
    return null;
  return (
    <article
      className="operation tutor-operation"
      aria-label={reading ? "Photo exchange" : "Message exchange"}
    >
      {(operation.text || reading || operation.kind === "hint") && (
        <div className="learner-message">
          <p className="eyebrow">You{reading ? " · Photo" : ""}</p>
          {operation.text && <p className="user-text">{operation.text}</p>}
          {operation.kind === "hint" && !operation.text && (
            <p>Requested help with this activity.</p>
          )}
          {operation.work_text && (
            <p className="user-text">{operation.work_text}</p>
          )}
        </div>
      )}
      {reading && (
        <section className="photo-reading" aria-label="Reading from your photo">
          <details open>
            <summary>
              <h5>Reading from your photo</h5>
            </summary>
            <p className="user-text">
              {operation.interpretation || "No usable reading was recovered."}
            </p>
          </details>
          {(ambiguities.length > 0 ||
            reading.organization_feedback.length > 0) && (
            <details className="reading-details">
              <summary>Reading details</summary>
              {ambiguities.length > 0 && (
                <ul>
                  {ambiguities.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              )}
              {reading.organization_feedback.length > 0 && (
                <ul>
                  {reading.organization_feedback.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              )}
            </details>
          )}
          {rejected && (
            <div role="status" className="reading-question">
              <strong>This photo needs clarification.</strong>
              <p>
                {reading.rejection_reason ||
                  ambiguities[0] ||
                  "The reader could not identify enough of the work to give reliable feedback. Type the relevant line or send a closer photo of it."}
              </p>
              <p>
                You can ask about this reading below, clarify the uncertain
                part, or attach another photo.
              </p>
            </div>
          )}
        </section>
      )}
      {feedback && !rejected ? (
        <section className="tutor-feedback" aria-label="Tutor response">
          <p className="eyebrow">Tutor</p>
          {feedback.strengths.map((item, index) => (
            <SafeText key={`strength-${index}`} text={item} />
          ))}
          {feedback.guidance.map((item, index) => (
            <SafeText key={`guidance-${index}`} text={item} />
          ))}
          {feedback.next_step && <SafeText text={feedback.next_step} />}
          {feedback.uncertainty_note && (
            <p className="notice">{feedback.uncertainty_note}</p>
          )}
          <details className="response-details">
            <summary>Response details</summary>
            {feedback.concepts.length > 0 && (
              <p>{feedback.concepts.join(" · ")}</p>
            )}
            <p className="fine">
              {operation.source} · AI feedback can be mistaken; it is not a
              verified grade.
            </p>
          </details>
        </section>
      ) : !rejected && operation.message ? (
        <SafeText text={operation.message} />
      ) : null}
      {operation.safe_error && !rejected && (
        <div role="status" className="error">
          <p>{operation.safe_error}</p>
          {operation.error_code && (
            <p className="fine">Diagnostic code: {operation.error_code}</p>
          )}
        </div>
      )}
      {operation.status === "failed" && operation.retryable && !rejected && (
        <button
          disabled={disabled || offline}
          onClick={() =>
            void act(async () => {
              await api(`/operations/${operation.id}/retry`, "POST");
              await refresh();
            })
          }
        >
          Retry tutor response
        </button>
      )}
      {["queued", "interpreting", "tutoring", "checking"].includes(
        operation.status,
      ) && (
        <button
          disabled={disabled || offline}
          onClick={() =>
            void act(async () => {
              await api(`/operations/${operation.id}/cancel`, "POST");
              await refresh();
            })
          }
        >
          Stop response
        </button>
      )}
      {operation.status === "canceled" && !reading && (
        <p className="fine">Response stopped.</p>
      )}
    </article>
  );
}
