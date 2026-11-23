export default function AboutData() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Data, sources and limitations</h1>
      <section className="card space-y-2">
        <h2 className="text-lg font-bold">California Independent Medical Review decisions</h2>
        <p>
          Source: <strong>California Department of Managed Health Care</strong>, Independent Medical Review (IMR) Determinations, published on the
          California Health and Human Services Open Data Portal under a Creative Commons Attribution license.
        </p>
        <p>
          We use these decisions to show how often independent reviewers overturned plan decisions for similar treatments, and to quote
          reviewers&apos; findings. These are California decisions; your plan, state and facts may differ. A low overturn rate does not mean you
          shouldn&apos;t appeal.
        </p>
      </section>
      <section className="card space-y-2">
        <h2 className="text-lg font-bold">Federal regulations</h2>
        <p>
          From the electronic Code of Federal Regulations (eCFR) API: 29 CFR 2560.503-1, 45 CFR 147.136, 42 CFR Part 422 Subpart M, 42 CFR Part 438
          Subpart F and parts of 45 CFR Part 149. Federal regulations are in the public domain.
        </p>
      </section>
      <section className="card space-y-2">
        <h2 className="text-lg font-bold">Plain-language summaries</h2>
        <p>
          Our rights summaries are written from the regulations above and marked as draft until a person reviews them against the cited paragraphs.
        </p>
      </section>
      <section className="card space-y-2">
        <h2 className="text-lg font-bold">Limitations</h2>
        <ul className="list-disc space-y-1 pl-6">
          <li>Our denial-category model is trained on synthetic letters. Real letters vary; always check the category and facts.</li>
          <li>Deadlines are counted from the date on your letter and are only shown when we have a cited rule for your plan type.</li>
          <li>This is not legal or medical advice. You are the author of your appeal.</li>
        </ul>
      </section>
    </div>
  );
}
