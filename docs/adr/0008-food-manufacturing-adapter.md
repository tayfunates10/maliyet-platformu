# ADR 0008 — Gıda İmalat Reçete ve Paketleme Adapter'ı

- Durum: Kabul edildi
- Tarih: 2026-08-19

## Amaç

Ortak imalat çekirdeğini gıda üretiminin reçete ölçekleme, paket gramajı/adedi ve
açık kayıp kategorileriyle beslemek; mevzuat veya raf ömrü gibi doğrulanmamış
kuralları maliyet motoruna gömmemek.

## Kararlar

1. `recipe_batches × theoretical_output_per_recipe` batch teorik çıktısını verir.
2. Proses kaybı, bozulma ve kalite reddi aynı output unit içinde ayrı ayrı girilir.
3. Good output = theoretical output - tüm açık loss kategorileri.
4. İlk gıda adapter'ı packaged-output modudur. `package_count × package_content_quantity` good output ile exact eşleşmelidir.
5. Paket gramajı/quantity common output unit'e UI/import katmanında dönüştürülmüş gelmelidir; adapter gizli gram→kg dönüşümü yapmaz.
6. Recipe ingredient quantity recipe batch sayısıyla, packaging material quantity paket adediyle ölçeklenir.
7. Cold-chain maliyeti food semantic result'ta ayrı kategori olarak korunur; common manufacturing çekirdeğine `other` conversion category ile aktarılır.
8. Recovery/by-product credit ortak manufacturing kontratını kullanır ve açık monetary input olmak zorundadır.
9. Package unit cost exact net batch cost / package count olarak hesaplanır; hidden rounding yoktur.
10. Snapshot food regulatory, shelf-life veya inventory valuation policy uygulanmış gibi davranmaz.

## Bilinçli kapsam dışı

- Bulk/unpackaged output
- Rework/reprocessing flows
- Raf ömrü ve son tüketim tarihi hesapları
- Türk Gıda Kodeksi sınıflandırma/etiket kuralları
- Besin değeri/alerjen hesapları
- Soğuk zincir sıcaklık mevzuatı
- Stok parti/lot traceability
- Vergisel zayi/fire politikası

Bu alanlar ayrı source-backed rules veya operasyon PR'larında eklenir.
