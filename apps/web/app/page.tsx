import { SectorCard } from "@/components/sector-card";
import { getPublicApiBaseUrl } from "@/lib/runtime-config";
import { SECTORS } from "@/lib/sectors";

export default function HomePage() {
  const apiBaseUrl = getPublicApiBaseUrl();

  return (
    <main>
      <section className="hero" aria-labelledby="hero-title">
        <div className="eyebrow">Maliyet • Kârlılık • Sermaye</div>
        <h1 id="hero-title">İşletmenin gerçek maliyetini görün.</h1>
        <p className="lead">
          Türkiye mevzuatına göre sürümlenen kurallar ve sektör özelinde maliyet sürücüleriyle
          karar desteği sağlayacak web platformunun ilk uygulama kabuğu.
        </p>
        <div className="status" role="status" aria-label="API yapılandırması">
          <span>API hedefi</span>
          <code>{apiBaseUrl}</code>
        </div>
      </section>

      <section className="sectorSection" aria-labelledby="sectors-title">
        <div className="sectionHeading">
          <p className="eyebrow">İlk kapsam</p>
          <h2 id="sectors-title">8 faaliyet alanı, tek hesaplama çekirdeği</h2>
        </div>
        <div className="sectorGrid">
          {SECTORS.map((sector) => (
            <SectorCard key={sector.slug} sector={sector} />
          ))}
        </div>
      </section>
    </main>
  );
}
