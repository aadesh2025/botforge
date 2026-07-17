"use client";

import { CreditCard, LogOut, Settings, User } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { currentUser } from "@/lib/mock/data";

export function UserMenu() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="rounded-md outline-none ring-offset-2 focus-visible:ring-2 focus-visible:ring-ember">
        <Avatar className="size-8 border border-border">
          <AvatarFallback className="bg-gradient-to-br from-ember to-ember-2 text-[#0A0B0D]">
            {currentUser.initials}
          </AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[220px]">
        <DropdownMenuLabel className="normal-case tracking-normal">
          <div className="flex flex-col">
            <span className="text-sm font-medium text-text">{currentUser.name}</span>
            <span className="text-xs font-normal text-faint">{currentUser.email}</span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem>
          <User className="size-4" /> Profile
        </DropdownMenuItem>
        <DropdownMenuItem>
          <Settings className="size-4" /> Settings
        </DropdownMenuItem>
        <DropdownMenuItem>
          <CreditCard className="size-4" /> Billing
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="text-error focus:text-error">
          <LogOut className="size-4" /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
