import type { Channel } from "./types";

export type ThreadStatus = "open" | "handoff" | "closed";
export type MsgRole = "visitor" | "agent" | "operator";

export interface ThreadMessage {
  id: string;
  role: MsgRole;
  text: string;
  at: string;
}

export interface InboxThread {
  id: string;
  visitor: string;
  agentName: string;
  channel: Channel;
  status: ThreadStatus;
  assignee: string | null;
  tags: string[];
  unread: boolean;
  updatedAt: string;
  messages: ThreadMessage[];
}

export const inboxThreads: InboxThread[] = [
  {
    id: "cnv_1",
    visitor: "+91 98••• ••210",
    agentName: "Support Concierge",
    channel: "whatsapp",
    status: "handoff",
    assignee: null,
    tags: ["shipping", "priority"],
    unread: true,
    updatedAt: "2026-07-17T06:38:00Z",
    messages: [
      { id: "m1", role: "visitor", text: "Hi, my order hasn't shipped yet. Order #48213", at: "2026-07-17T06:30:00Z" },
      { id: "m2", role: "agent", text: "Let me check that for you — one moment.", at: "2026-07-17T06:30:20Z" },
      { id: "m3", role: "agent", text: "It looks like order #48213 is still awaiting dispatch. I'm escalating this to a teammate who can push it through.", at: "2026-07-17T06:31:00Z" },
      { id: "m4", role: "visitor", text: "Please, I need it before the weekend.", at: "2026-07-17T06:38:00Z" },
    ],
  },
  {
    id: "cnv_2",
    visitor: "visitor_9f2c",
    agentName: "Sales Qualifier",
    channel: "web",
    status: "open",
    assignee: null,
    tags: ["pricing"],
    unread: true,
    updatedAt: "2026-07-17T06:31:00Z",
    messages: [
      { id: "m1", role: "visitor", text: "Do you offer volume pricing for 500+ seats?", at: "2026-07-17T06:28:00Z" },
      { id: "m2", role: "agent", text: "Yes! For 500+ seats we offer custom Scale pricing with dedicated support. Want me to have someone reach out?", at: "2026-07-17T06:31:00Z" },
    ],
  },
  {
    id: "cnv_5",
    visitor: "+91 90••• ••884",
    agentName: "Order Tracker",
    channel: "whatsapp",
    status: "open",
    assignee: "Aadesh Sree",
    tags: ["refund"],
    unread: false,
    updatedAt: "2026-07-17T05:41:00Z",
    messages: [
      { id: "m1", role: "visitor", text: "Where is my refund? It's been 5 days.", at: "2026-07-17T05:30:00Z" },
      { id: "m2", role: "operator", text: "Hi, this is Aadesh. I can see the refund was approved today and should land within 2 business days.", at: "2026-07-17T05:41:00Z" },
    ],
  },
  {
    id: "cnv_3",
    visitor: "@rahul_dev",
    agentName: "Support Concierge",
    channel: "telegram",
    status: "closed",
    assignee: null,
    tags: ["widget"],
    unread: false,
    updatedAt: "2026-07-17T06:12:00Z",
    messages: [
      { id: "m1", role: "visitor", text: "How do I reset the widget theme to default colors?", at: "2026-07-17T06:05:00Z" },
      { id: "m2", role: "agent", text: "In the Channels tab, click 'Reset theme' next to the color pickers. That restores the default ember theme.", at: "2026-07-17T06:06:00Z" },
      { id: "m3", role: "visitor", text: "Perfect, thanks!", at: "2026-07-17T06:12:00Z" },
    ],
  },
];
