# ADR 0007 — Ortak İmalat Batch Maliyet Çekirdeği

- Durum: Kabul edildi
- Tarih: 2026-08-19

## Amaç

Gıda, tekstil ve ana metal sektörlerinin tekrar eden üretim matematiğini ortak
bir çekirdeğe almak; sektöre özgü reçete, proses ve mevzuat ayrıntılarını bu
çekirdeğe gömmemek.

## Kararlar

1. BOM/material satırları kendi ölçü birimlerinde `quantity × unit_cost` ile maliyetlenir.
2. Farklı malzeme birimleri fiziksel olarak toplanmaz. Kg + metre + adet üzerinden sahte yield üretilmez.
3. Yield/loss aynı `output_unit` içindeki `theoretical_output_quantity` ve `good_output_quantity` üzerinden hesaplanır.
4. Good output sıfır olamaz ve teorik çıktıyı aşamaz.
5. Conversion cost kategorileri ortak çekirdekte labor, energy, machine, packaging, subcontracting, quality ve other ile sınırlıdır.
6. Scrap/by-product/reusable output değeri yalnız explicit `RecoveryCredit` olarak net batch maliyetini azaltır. Motor piyasa/hurda fiyatı tahmin etmez.
7. Recovery credit gross batch cost'u aşamaz; negatif üretim maliyeti üretilmez.
8. Unit cost = net batch cost / good output quantity. Hidden rounding yoktur.
9. Sonuç, sektör-bağımsız costing engine'e tek direct-cost line olarak aktarılabilir.
10. Snapshot inventory valuation veya tax policy uygulandığını iddia etmez.

## Maliyet zinciri

```text
material usage cost
+ labor / energy / machine / packaging / subcontract / quality / other
= gross batch cost
- explicit scrap/by-product/recovery credit
= net batch cost
/ good output quantity
= exact unit cost
```

## Bilinçli kapsam dışı

- Gıda reçete besin/içerik mevzuatı ve raf ömrü
- Tekstil kesim marker/verim algoritması, iplik/kumaş özel dönüşümleri
- Ana metal alaşım/ergitme/enerji fizik modeli
- Stok değerleme yöntemleri
- Vergisel fire/zayi kabul kuralları
- Standart maliyet vs fiili maliyet varyans muhasebesi
- Döviz birim maliyet dönüşümü
- Yasal/rapor kuruş yuvarlama

Bu alanlar sektör PR'larında veya ayrı accounting/rules katmanlarında ele alınacaktır.
