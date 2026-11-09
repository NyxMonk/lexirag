import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/layout/Sidebar";

export function AppShell() {
  return (
    <div className="flex h-screen min-w-[1024px] overflow-hidden">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
