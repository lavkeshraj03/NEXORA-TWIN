"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main id="main-content" tabIndex={-1} className="fallback"><h1>Something interrupted your workspace.</h1><p>Try loading the page again.</p><button className="button primary" onClick={reset}>Try again</button></main>;
}
