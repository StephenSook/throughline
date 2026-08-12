export default function DegradedBanner({ message }: { message: string }) {
  return (
    <div className="border border-bad border-l-[3px] bg-panel px-4 py-3 text-sm">
      <b className="text-bad">Degraded.</b> {message}
    </div>
  );
}
