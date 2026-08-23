import Link from "next/link";
import { DecisionAnalysisWorkspace } from "@/components/decision-analysis-workspace";
import styles from "../calculations/page.module.css";

export default function DecisionAnalysisPage() {
  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <Link href="/" className={styles.backLink}>
          ← Ana sayfa
        </Link>
        <p className={styles.eyebrow}>SaaS karar desteği</p>
        <h1>Yatırım getirisini ve üç açık senaryoyu tenant sınırları içinde analiz edin.</h1>
        <p className={styles.lead}>
          ROI, ROE, ROIC ve senaryo sonuçları yalnız server-side Decimal motorundan gelir. Tarayıcı
          vergi oranı, finansman karması, enflasyon, iskonto oranı veya senaryo şoku üretmez.
        </p>
      </header>
      <DecisionAnalysisWorkspace />
    </main>
  );
}
