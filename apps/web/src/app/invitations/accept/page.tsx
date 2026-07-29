import { Suspense } from "react";
import { AcceptInvitation } from "@/components/invitations/accept-invitation";

/** The landing page for an invitation email's link.
 *
 * Outside the authenticated `(app)` layout on purpose: an invited person usually has no
 * account yet, so this has to work with no session at all.
 */
export default function AcceptInvitationPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
        <AcceptInvitation />
      </Suspense>
    </main>
  );
}
