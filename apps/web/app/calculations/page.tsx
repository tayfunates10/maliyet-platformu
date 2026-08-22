import Link from "next/link";
import { CalculationWorkspace } from "@/components/calculation-workspace";
import styles from "./page.module.css";

export default function CalculationsPage() {
  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <Link href="/" className={styles.backLink}>
          ← Ana sayfa
        </Link>
        <p className={styles.eyebrow}>SaaS çalışma alanı</p>
        <h1>Tenant sınırları içinde hesaplama kaydı oluşturun ve yönetin.</h1>
        <p className={styles.lead}>
          Sektör motoru yalnız API allowlist’inden seçilir. Oturum token’ı tarayıcı depolamasına
          yazılmaz; hesaplama verisi yalnız seçili organizasyon kapsamında okunur ve oluşturulur.
        </p>
      </header>
      <CalculationWorkspace />
    </main>
  );
}
