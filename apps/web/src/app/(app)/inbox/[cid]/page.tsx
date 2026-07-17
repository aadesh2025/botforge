import { InboxView } from "@/components/inbox/inbox-view";

export default function InboxThreadPage({ params }: { params: { cid: string } }) {
  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-text">Inbox</h1>
        <p className="text-sm text-muted">Live conversations across every channel. Take over when the bot needs a hand.</p>
      </div>
      <InboxView initialId={params.cid} />
    </div>
  );
}
