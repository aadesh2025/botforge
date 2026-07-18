import {
  LayoutDashboard,
  Bot,
  BookOpen,
  Inbox,
  BarChart3,
  MessagesSquare,
  Workflow,
  Settings,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: number;
};

export type NavGroup = {
  heading?: string;
  items: NavItem[];
};

export const nav: NavGroup[] = [
  {
    items: [{ label: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    heading: "Build",
    items: [
      { label: "Agents", href: "/agents", icon: Bot },
      { label: "Knowledge", href: "/knowledge", icon: BookOpen },
      { label: "Automations", href: "/automations", icon: Workflow },
    ],
  },
  {
    heading: "Operate",
    items: [
      { label: "Conversations", href: "/conversations", icon: MessagesSquare },
      { label: "Inbox", href: "/inbox", icon: Inbox, badge: 3 },
      { label: "Analytics", href: "/analytics", icon: BarChart3 },
    ],
  },
  {
    heading: "Workspace",
    items: [{ label: "Settings", href: "/settings/org", icon: Settings }],
  },
];
