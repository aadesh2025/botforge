export interface Workflow {
  id: string;
  name: string;
  active: boolean;
  nodes: number;
  lastRun: string | null;
  boundAgents: string[];
  trigger: "webhook" | "schedule" | "manual";
}

export const workflows: Workflow[] = [
  {
    id: "wf_1",
    name: "Create support ticket",
    active: true,
    nodes: 6,
    lastRun: "2026-07-17T06:20:00Z",
    boundAgents: ["Support Concierge"],
    trigger: "webhook",
  },
  {
    id: "wf_2",
    name: "Sync lead to CRM",
    active: true,
    nodes: 9,
    lastRun: "2026-07-17T05:02:00Z",
    boundAgents: ["Sales Qualifier"],
    trigger: "webhook",
  },
  {
    id: "wf_3",
    name: "Send order status email",
    active: true,
    nodes: 5,
    lastRun: "2026-07-16T22:40:00Z",
    boundAgents: ["Order Tracker"],
    trigger: "webhook",
  },
  {
    id: "wf_4",
    name: "Nightly KB reindex",
    active: false,
    nodes: 4,
    lastRun: "2026-07-15T00:00:00Z",
    boundAgents: [],
    trigger: "schedule",
  },
  {
    id: "wf_5",
    name: "Escalate to Slack on handoff",
    active: true,
    nodes: 3,
    lastRun: "2026-07-17T06:38:00Z",
    boundAgents: ["Support Concierge"],
    trigger: "webhook",
  },
];
