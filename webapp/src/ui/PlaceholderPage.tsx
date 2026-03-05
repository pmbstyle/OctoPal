type PlaceholderPageProps = {
  title: string;
  description: string;
};

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <p>{description}</p>
      <div className="placeholder-grid">
        <article className="placeholder-card">
          <h3>Loading state</h3>
          <p>Reusable skeleton and optimistic refresh patterns will live here.</p>
        </article>
        <article className="placeholder-card">
          <h3>Error state</h3>
          <p>Consistent retry behavior and transport error messaging.</p>
        </article>
        <article className="placeholder-card">
          <h3>Empty state</h3>
          <p>Guided messaging when no data is available for selected filters.</p>
        </article>
      </div>
    </section>
  );
}
