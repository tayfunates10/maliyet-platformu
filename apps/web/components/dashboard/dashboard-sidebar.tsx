"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { DashboardOrganization } from "@/lib/dashboard-api";
import styles from "./dashboard.module.css";

/**
 * Navigation entries.
 *
 * `href` is set only for routes that actually exist in this application. An
 * entry without one renders as a disabled control with a stated reason rather
 * than a link that looks live and goes nowhere.
 */
const NAV_ITEMS = Object.freeze([
  { key: "dashboard", label: "Gösterge Paneli", href: "/dashboard", glyph: "▤" },
  { key: "calculations", label: "Maliyet Hesaplamaları", href: "/calculations", glyph: "∑" },
  { key: "decision", label: "Karar Analizi", href: "/decision-analysis", glyph: "◪" },
  { key: "widget", label: "Widget Markalama", href: "/widget-branding", glyph: "◈" },
  { key: "baseline", label: "Mevzuat Baseline", href: null, glyph: "§" },
  { key: "reports", label: "Raporlar", href: null, glyph: "▦" },
  { key: "settings", label: "Ayarlar", href: null, glyph: "⚙" },
] as const);

const UNAVAILABLE_HINT = "Bu bölüm için henüz bir uygulama ekranı yok";

export function DashboardSidebar({
  organization,
  open,
  onNavigate,
  onSignOut,
  busy,
}: Readonly<{
  organization: DashboardOrganization | null;
  open: boolean;
  onNavigate: () => void;
  onSignOut: () => void;
  busy: boolean;
}>) {
  const pathname = usePathname();

  return (
    <nav
      className={`${styles.sidebar} ${open ? styles.sidebarOpen : ""}`}
      aria-label="Ana gezinme"
    >
      <p className={styles.brand}>
        <span className={styles.brandMark} aria-hidden="true">
          ₺
        </span>
        Maliyet Platformu
      </p>

      <div className={styles.nav}>
        {NAV_ITEMS.map((item) =>
          item.href === null ? (
            <button
              key={item.key}
              type="button"
              className={styles.navDisabled}
              disabled
              title={UNAVAILABLE_HINT}
            >
              <span className={styles.navIcon} aria-hidden="true">
                {item.glyph}
              </span>
              {item.label}
            </button>
          ) : (
            <Link
              key={item.key}
              href={item.href}
              className={styles.navLink}
              aria-current={pathname === item.href ? "page" : undefined}
              onClick={onNavigate}
            >
              <span className={styles.navIcon} aria-hidden="true">
                {item.glyph}
              </span>
              {item.label}
            </Link>
          ),
        )}
      </div>

      <div className={styles.sidebarFooter}>
        {organization === null ? null : (
          <div className={styles.tenantCard}>
            <span className={styles.tenantName}>{organization.legal_name}</span>
            <span className={styles.tenantMeta}>
              {organization.role}
              {organization.city === null ? "" : ` · ${organization.city}`}
            </span>
          </div>
        )}
        <button type="button" className={styles.signOut} onClick={onSignOut} disabled={busy}>
          Oturumu kapat
        </button>
      </div>
    </nav>
  );
}
