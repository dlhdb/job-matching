interface PlaceholderProps {
  title: string;
  message?: string;
}

/** 還沒做好或不存在的頁面 */
export function Placeholder({ title, message = "這一頁還在製作中。" }: PlaceholderProps) {
  return (
    <section className="card" aria-label={title}>
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}
