export function BusyStatus({ message }: { message: string }) {
  return (
    <div className="busy-status" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
