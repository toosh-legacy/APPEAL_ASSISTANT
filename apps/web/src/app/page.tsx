import Link from "next/link";

export default function Home() {
  return (
    <div className="space-y-6">
      <section className="card">
        <h1 className="text-3xl font-bold">Got a health insurance denial?</h1>
        <p className="mt-3">
          Paste your denial letter. We explain it in plain words, find your appeal deadline, and help you draft an appeal letter where every legal statement is
          linked to its source.
        </p>
        <Link href="/start" className="btn mt-5">
          Start my appeal
        </Link>
      </section>

      <section className="card" aria-labelledby="how">
        <h2 id="how" className="text-xl font-bold">
          How it works
        </h2>
        <ol className="mt-2 list-decimal space-y-1 pl-6">
          <li>Paste or upload your letter.</li>
          <li>Check the facts we found and fix anything wrong.</li>
          <li>Read why they said no and when your appeal is due.</li>
          <li>Edit your letter, then download it as PDF or Word. You send it yourself.</li>
        </ol>
      </section>

      <section className="card" aria-labelledby="privacy">
        <h2 id="privacy" className="text-xl font-bold">
          Our privacy promise
        </h2>
        <ul className="mt-2 list-disc space-y-1 pl-6">
          <li>Names, member IDs, phone numbers and other identifiers are replaced with tokens before any AI step sees your letter.</li>
          <li>A safety check blocks any step that would still see a raw identifier.</li>
          <li>We never send anything to your insurer. You can delete your case at any time.</li>
        </ul>
      </section>

      <section className="card" aria-labelledby="sources">
        <h2 id="sources" className="text-xl font-bold">
          Where the information comes from
        </h2>
        <ul className="mt-2 list-disc space-y-1 pl-6">
          <li>Federal rules from the official eCFR website (free to use).</li>
          <li>Real decisions from outside doctors who reviewed denials, from the California Department of Managed Health Care (CC BY).</li>
        </ul>
        <p className="mt-2">
          We publish our latest test results in the evaluation report. <Link href="/about/data">Learn more about the data</Link>.
        </p>
      </section>
    </div>
  );
}
