"use client";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="empty">
      <h2>Something went wrong</h2>
      <p className="muted">The data API may be starting up or briefly unavailable.</p>
      <button className="seg" onClick={() => reset()} style={{ padding: "0.4rem 0.9rem", cursor: "pointer" }}>
        Try again
      </button>
    </div>
  );
}
