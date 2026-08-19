# ADR 0006 — Sektör Bağımsız Maliyet ve Vergi Öncesi Kârlılık Çekirdeği

- Durum: Kabul edildi
- Tarih: 2026-08-19

## Amaç

Gıda, tekstil, ana metal, e-ticaret, ticaret, ulaştırma, konaklama ve turizm
motorlarının ortak kullanacağı maliyet/kârlılık matematiğini tek bir çekirdekte
toplamak.

## Kararlar

1. Çekirdek sektör bilmez. Sektör modülleri girdileri standardize edip bu motora verir.
2. Tüm parasal girdiler ve oranlar `Decimal` olmak zorundadır. Runtime'da float da reddedilir.
3. Gelir akışı `gross revenue - explicit reductions = net revenue` şeklindedir.
4. Direkt maliyetler contribution profit'ten, genel giderler operating profit'ten düşülür.
5. Amortisman bu PR'da mevzuata göre hesaplanmaz; dışarıda doğrulanmış dönem maliyeti girdisi olarak alınır.
6. Finansman maliyeti ayrı gösterilir.
7. Sonuç `pretax_accounting_profit` noktasında durur. Muhasebe kârı otomatik olarak vergi matrahı kabul edilmez.
8. Vergi matrahı daha sonra indirim/istisna/kanunen kabul edilmeyen gider gibi explicit reconciliation girdileri ve rules-engine üzerinden hesaplanacaktır.
9. Markup ve satış marjı ayrı kavramlardır ve ayrı fonksiyonlarla hesaplanır.
10. Genel gider dağıtımı açık allocation weight kullanır. Target'lar key'e göre sıralanır; Decimal bölme tekrarlı olduğunda son target kalan exact residual'ı alır ve pool toplamı kaybolmaz. Bu, para yuvarlama politikası değildir.
11. Break-even revenue yalnız explicit contribution margin ratio verilirse hesaplanır; motor bu oranı tahmin etmez.
12. Snapshot `taxable_base_inferred=false` alanını taşır.

## Sonuç zinciri

```text
gross revenue
- discounts / returns / reductions
= net revenue
- direct costs
= contribution profit
- allocated overhead
= operating profit before depreciation and financing
- depreciation input
- financing costs
= pretax accounting profit
```

## Bilinçli kapsam dışı

- Vergi matrahı reconciliation
- KDV'nin gelir/maliyet sunumuna etkisi
- Mevzuata göre amortisman oranı/ömrü
- Stok değerleme
- Kur farkı muhasebe politikası
- Ürün reçetesi/BOM
- Sektör özel fire/randıman mantığı
- Yasal para yuvarlama

Bunların her biri ayrı rules/data veya sektör PR'ında uygulanacaktır.
