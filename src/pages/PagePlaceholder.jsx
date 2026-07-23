export function PagePlaceholder({ title, description }) {
  return (
    <section aria-labelledby="placeholder-title">
      <h2 id="placeholder-title">{title}</h2>
      <p>{description}</p>
    </section>
  );
}
