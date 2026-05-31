import Link from "next/link";

export default function NotFound() {
  return (
    <div className="empty">
      <h2>Not found</h2>
      <p className="muted">That page doesn’t exist. <Link href="/">Back to overview</Link>.</p>
    </div>
  );
}
