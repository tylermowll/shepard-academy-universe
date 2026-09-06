export function App() {
  return (
    <main className="mx-auto flex min-h-svh max-w-5xl flex-col px-6 py-10 sm:px-12 sm:py-16">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-emerald-900/15 pb-6">
        <p className="font-semibold tracking-tight">Math Practice Tutor</p>
        <p className="rounded-full bg-emerald-900/10 px-3 py-1 text-sm font-medium">
          In development
        </p>
      </header>

      <section
        className="flex flex-1 flex-col justify-center py-16 sm:py-24"
        aria-labelledby="welcome"
      >
        <p className="mb-5 text-sm font-semibold uppercase tracking-widest text-emerald-800">
          One step at a time
        </p>
        <h1
          id="welcome"
          className="max-w-3xl text-5xl leading-tight font-semibold tracking-tight sm:text-7xl"
        >
          Make room for a little math.
        </h1>
        <p className="mt-7 max-w-xl text-lg leading-relaxed text-stone-700">
          A space to work through a problem, learn from a mistake, and try
          again.
        </p>
        <aside
          className="mt-10 max-w-xl rounded-2xl border border-emerald-900/15 bg-white/70 p-6"
          aria-label="Preview availability"
        >
          <h2 className="font-semibold">A first look</h2>
          <p className="mt-2 leading-relaxed text-stone-700">
            This app is still being built. Practice sessions are not available
            yet.
          </p>
        </aside>
      </section>

      <footer className="border-t border-emerald-900/15 pt-6 text-sm text-stone-700">
        Planned first topics: fractions and simple linear equations.
      </footer>
    </main>
  );
}
