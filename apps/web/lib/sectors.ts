export type SectorGroup = "manufacturing" | "service-commerce";

export interface SectorDefinition {
  readonly slug: string;
  readonly name: string;
  readonly description: string;
  readonly group: SectorGroup;
}

export const SECTORS: readonly SectorDefinition[] = [
  {
    slug: "food-manufacturing",
    name: "Gıda İmalatı",
    description: "Reçete, fire, randıman, ambalaj, enerji ve üretim işçiliği maliyetleri.",
    group: "manufacturing",
  },
  {
    slug: "textile-manufacturing",
    name: "Tekstil İmalatı",
    description: "Kumaş, iplik, fason süreçler, kesim/dikim firesi ve ürün bazlı maliyet.",
    group: "manufacturing",
  },
  {
    slug: "basic-metals",
    name: "Ana Metal",
    description: "Hammadde, enerji, makine/fırın saati, randıman ve hurda geri kazanımı.",
    group: "manufacturing",
  },
  {
    slug: "e-commerce",
    name: "E-Ticaret",
    description: "Ürün, kargo, pazaryeri, ödeme, reklam, iade ve fulfillment maliyetleri.",
    group: "service-commerce",
  },
  {
    slug: "commerce",
    name: "Ticaret",
    description: "Alış, taşıma, depo, fire, finansman, POS ve gerçek satış marjı.",
    group: "service-commerce",
  },
  {
    slug: "transportation",
    name: "Ulaştırma",
    description: "Sefer, araç, yakıt, personel, yol, bakım ve kapasite maliyetleri.",
    group: "service-commerce",
  },
  {
    slug: "accommodation",
    name: "Konaklama",
    description: "Oda/gece kapasitesi, doluluk, kanal komisyonu ve operasyon maliyetleri.",
    group: "service-commerce",
  },
  {
    slug: "tourism",
    name: "Turizm",
    description: "Tur/paket, transfer, rehber, bilet, konaklama ve döviz etkisi.",
    group: "service-commerce",
  },
] as const;
