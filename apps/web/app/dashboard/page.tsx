import type { Metadata } from "next";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export const metadata: Metadata = {
  title: "Gösterge Paneli · Maliyet Platformu",
  description:
    "Tenant sınırları içinde maliyet, mevzuat baseline, karar analizi ve widget durumu.",
};

export default function DashboardPage() {
  return <DashboardShell />;
}
