export function checkOffline(input: string, n: bigint, d: bigint): string {
  if (input.length > 128) return "Use a bounded integer or fraction.";
  const match =
    /^\s*(?:x\s*=\s*)?([+-]?\d{1,9})(?:\s*\/\s*([+-]?\d{1,9}))?\s*$/.exec(
      input,
    );
  if (!match?.[1]) return "Use an integer or fraction.";
  const numerator = BigInt(match[1]),
    denominator = BigInt(match[2] ?? "1");
  if (denominator === 0n) return "The denominator cannot be zero.";
  return numerator * d === n * denominator
    ? "Correct value (checked on this device)."
    : "Different value. Try again or use the hint.";
}
