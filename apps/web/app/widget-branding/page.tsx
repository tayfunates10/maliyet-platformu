import Link from "next/link";
import { WidgetBrandingManager } from "@/components/widget-branding-manager";
import { getPublicApiBaseUrl } from "@/lib/runtime-config";
import styles from "./page.module.css";

export default function WidgetBrandingPage() {
  const apiBaseUrl = getPublicApiBaseUrl();

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <Link href="/" className={styles.backLink}>
          ← Ana sayfa
        </Link>
        <p className={styles.eyebrow}>Widget yönetimi</p>
        <h1>Marka görünümünü taslak olarak düzenleyin, sonra açıkça yayınlayın.</h1>
        <p className={styles.lead}>
          Taslak kaydetme ve canlı presentation yayınlama ayrı işlemlerdir. Finansal hesaplama,
          mevzuat ve tenant yetkisi API tarafında kalır.
        </p>
      </header>
      <WidgetBrandingManager apiBaseUrl={apiBaseUrl} />
    </main>
  );
}
