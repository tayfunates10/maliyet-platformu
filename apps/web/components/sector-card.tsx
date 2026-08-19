import type { SectorDefinition } from "@/lib/sectors";

interface SectorCardProps {
  readonly sector: SectorDefinition;
}

export function SectorCard({ sector }: SectorCardProps) {
  const groupLabel = sector.group === "manufacturing" ? "İmalat" : "Hizmet / ticaret";

  return (
    <article className="sectorCard">
      <p className="sectorGroup">{groupLabel}</p>
      <h3>{sector.name}</h3>
      <p>{sector.description}</p>
    </article>
  );
}
