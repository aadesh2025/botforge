import type {
  Agent,
  Conversation,
  CurrentUser,
  DashboardSummary,
  Organization,
  UsagePoint,
} from "./types";

export const currentUser: CurrentUser = {
  id: "usr_1",
  name: "Aadesh Sree",
  email: "aadesh@aurozen.ai",
  initials: "AS",
};

export const organizations: Organization[] = [
  { id: "org_1", name: "AUROZEN AI", slug: "aurozen", plan: "scale", role: "owner" },
  { id: "org_2", name: "Western Collection", slug: "western", plan: "pro", role: "admin" },
  { id: "org_3", name: "Vinayaga Implex", slug: "vinayaga", plan: "free", role: "owner" },
];

export const agents: Agent[] = [
  {
    id: "agt_1",
    name: "Support Concierge",
    status: "live",
    provider: "groq",
    model: "llama-3.3-70b-versatile",
    channels: ["web", "whatsapp", "telegram"],
    conversations7d: 1284,
    resolutionRate: 0.87,
    updatedAt: "2026-07-17T05:20:00Z",
  },
  {
    id: "agt_2",
    name: "Sales Qualifier",
    status: "live",
    provider: "groq",
    model: "llama-3.1-8b-instant",
    channels: ["web", "slack"],
    conversations7d: 642,
    resolutionRate: 0.74,
    updatedAt: "2026-07-16T22:10:00Z",
  },
  {
    id: "agt_3",
    name: "Docs Assistant",
    status: "draft",
    provider: "gemini",
    model: "gemini-1.5-flash",
    channels: ["web"],
    conversations7d: 0,
    resolutionRate: 0,
    updatedAt: "2026-07-17T04:02:00Z",
  },
  {
    id: "agt_4",
    name: "Order Tracker",
    status: "paused",
    provider: "openai",
    model: "gpt-4o-mini",
    channels: ["whatsapp"],
    conversations7d: 58,
    resolutionRate: 0.63,
    updatedAt: "2026-07-14T11:45:00Z",
  },
];

export const recentConversations: Conversation[] = [
  {
    id: "cnv_1",
    agentName: "Support Concierge",
    channel: "whatsapp",
    preview: "My order hasn't shipped yet, can you check status #48213?",
    visitor: "+91 98••• ••210",
    status: "handoff",
    messages: 14,
    updatedAt: "2026-07-17T06:38:00Z",
  },
  {
    id: "cnv_2",
    agentName: "Sales Qualifier",
    channel: "web",
    preview: "Do you offer volume pricing for 500+ seats?",
    visitor: "visitor_9f2c",
    status: "open",
    messages: 6,
    updatedAt: "2026-07-17T06:31:00Z",
  },
  {
    id: "cnv_3",
    agentName: "Support Concierge",
    channel: "telegram",
    preview: "How do I reset the widget theme to default colors?",
    visitor: "@rahul_dev",
    status: "closed",
    messages: 9,
    updatedAt: "2026-07-17T06:12:00Z",
  },
  {
    id: "cnv_4",
    agentName: "Support Concierge",
    channel: "web",
    preview: "Thanks, that fixed it! The RAG citations show now.",
    visitor: "visitor_a71b",
    status: "closed",
    messages: 4,
    updatedAt: "2026-07-17T05:58:00Z",
  },
  {
    id: "cnv_5",
    agentName: "Order Tracker",
    channel: "whatsapp",
    preview: "Where is my refund? It's been 5 days.",
    visitor: "+91 90••• ••884",
    status: "open",
    messages: 11,
    updatedAt: "2026-07-17T05:41:00Z",
  },
];

// 14-day usage series with a gentle upward trend + weekday rhythm.
export const usageSeries: UsagePoint[] = Array.from({ length: 14 }).map((_, i) => {
  const date = new Date("2026-07-04T00:00:00Z");
  date.setUTCDate(date.getUTCDate() + i);
  const weekday = date.getUTCDay();
  const weekendDip = weekday === 0 || weekday === 6 ? 0.62 : 1;
  const growth = 1 + i * 0.045;
  const base = 240 * weekendDip * growth;
  const conversations = Math.round(base);
  const tokens = Math.round(conversations * 1180 * (0.9 + (i % 3) * 0.08));
  const cost = +(tokens * 0.00000059).toFixed(2);
  return { date: date.toISOString().slice(0, 10), tokens, cost, conversations };
});

export const dashboardSummary: DashboardSummary = {
  conversations7d: 1984,
  conversationsDelta: 12.4,
  messages7d: 14620,
  messagesDelta: 9.1,
  resolutionRate: 0.83,
  resolutionDelta: 2.7,
  tokens7d: 18_940_000,
  cost7d: 11.18,
  costDelta: -4.2,
  activeAgents: 2,
  totalAgents: 4,
};
