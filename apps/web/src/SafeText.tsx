import katex from "katex";
import "katex/dist/katex.min.css";

/** Restricted formatting only: text, bold, code and bounded inline math. */
export function SafeText({ text }: { text: string }) {
  return (
    <div className="explanation">
      {text
        .slice(0, 6000)
        .split(/(\*\*[^*\n]{1,500}\*\*|`[^`\n]{1,500}`|\$[^$\n]{1,1000}\$)/g)
        .map((part, i) => {
          if (part.startsWith("**") && part.endsWith("**"))
            return <strong key={i}>{part.slice(2, -2)}</strong>;
          if (part.startsWith("`") && part.endsWith("`"))
            return <code key={i}>{part.slice(1, -1)}</code>;
          if (part.startsWith("$") && part.endsWith("$"))
            return (
              <span
                key={i}
                dangerouslySetInnerHTML={{
                  __html: katex.renderToString(part.slice(1, -1), {
                    trust: false,
                    throwOnError: false,
                    maxExpand: 100,
                    maxSize: 10,
                    output: "htmlAndMathml",
                    strict: "error",
                  }),
                }}
              />
            );
          return <span key={i}>{part}</span>;
        })}
    </div>
  );
}
