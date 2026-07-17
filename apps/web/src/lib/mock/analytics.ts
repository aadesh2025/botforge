export interface TopQuestion {
  q: string;
  count: number;
  resolved: boolean;
}

export const topQuestions: TopQuestion[] = [
  { q: "Where is my order?", count: 412, resolved: true },
  { q: "What is your return policy?", count: 308, resolved: true },
  { q: "Do you ship internationally?", count: 221, resolved: true },
  { q: "How do I reset my password?", count: 164, resolved: true },
  { q: "Can I change my delivery address?", count: 131, resolved: true },
];

export const unansweredQuestions: TopQuestion[] = [
  { q: "Do you integrate with Shopify Plus?", count: 38, resolved: false },
  { q: "Is there an offline mode?", count: 24, resolved: false },
  { q: "What's the SLA for enterprise?", count: 19, resolved: false },
];

export interface ChannelShare {
  channel: string;
  share: number; // 0..1
}

export const channelBreakdown: ChannelShare[] = [
  { channel: "Web", share: 0.46 },
  { channel: "WhatsApp", share: 0.31 },
  { channel: "Telegram", share: 0.14 },
  { channel: "Slack", share: 0.09 },
];

// Latency distribution buckets (first-token, ms)
export const latencyBuckets: { label: string; count: number }[] = [
  { label: "<0.5s", count: 620 },
  { label: "0.5–1s", count: 1180 },
  { label: "1–1.5s", count: 540 },
  { label: "1.5–2s", count: 190 },
  { label: ">2s", count: 64 },
];
