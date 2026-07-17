import { Globe, Hash, MessageCircle, MessagesSquare, Send, type LucideIcon } from "lucide-react";
import type { Channel } from "@/lib/mock/types";
import { cn } from "@/lib/utils";

const map: Record<Channel, LucideIcon> = {
  web: Globe,
  whatsapp: MessageCircle,
  telegram: Send,
  slack: Hash,
  discord: MessagesSquare,
};

export function ChannelIcon({ channel, className }: { channel: Channel; className?: string }) {
  const Icon = map[channel];
  return <Icon className={cn("size-3.5", className)} />;
}
