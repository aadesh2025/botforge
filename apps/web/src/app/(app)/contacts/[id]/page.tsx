import { ContactsView } from "@/components/contacts/contacts-view";

/** Deep link from the Inbox: the list, with this contact's panel already open. */
export default async function ContactDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ContactsView initialId={id} />;
}
