# ADR 0005 — Decimal-Only Calculation Kernel ve Yuvarlama Sınırı

- Durum: Kabul edildi
- Tarih: 2026-08-19

## Bağlam

Vergi ve SGK hesaplarının oran/eşikleri rules-engine içinden gelmektedir. Hesap
motorunun aynı değerleri tekrar sabitlemesi geçmiş hesapları kırar ve mevzuat
kaynağını görünmez hale getirir. Ayrıca binary floating point finansal sonuçlarda
kuruş sapmalarına yol açabilir.

## Karar

1. Calculation kernel oran/eşik bilmez; yalnız `ResolvedRule` tüketir.
2. Tüm finansal input ve ara sonuçlar `Decimal` ile hesaplanır.
3. Kernel içinde implicit `round()` veya kuruşa `quantize()` yapılmaz.
4. Bir beyan/rapor alanı için yasal yuvarlama gerektiğinde bu politika ayrıca
   resmi kaynağa bağlı rule/policy olarak uygulanacaktır.
5. Progressive gelir vergisi tarifesinde source payload'daki `base_tax` değeri
   yalnız formülde kullanılmaz; önce önceki dilimlerden türeyen tax ile eşleştiği
   doğrulanır. Tutarsız tariff fail-closed olur.
6. Flat-rate tax hesaplaması `payload.rate` değerini kullanır.
7. 4/a full-month SGK primitive'i aylık PEK alt/üst sınırını uygular; işveren,
   çalışan ve birleşik oran toplamlarının kendi iç tutarlılığını doğrular.
8. Kısmi ay, teşvik, istisna veya farklı sigortalılık statüsü bu primitive'de
   tahmin edilmez. Ayrı rule ve ayrı hesap yolu gerektirir.
9. Her sonuç hesapta kullanılan exact rule provenance snapshot'ını taşır.

## Resmi davranış dayanağı

GİB 2026 gelir vergisi tarifesini her dilim için belirli matraha kadar oran ve
sonraki dilimde `önceki kısım için vergi + fazlasına oran` biçiminde yayımlar.
SGK ise prime esas kazanç alt sınırının altında kalan günlük kazancın alt sınır,
üst sınırın üzerindeki kazancın üst sınır üzerinden hesaplanacağını açıklar.

## Bilinçli kapsam dışı

- Yasal kuruş/tecil/beyanname yuvarlama politikaları
- Ücret bordrosunda gelir vergisi istisnaları
- Kısmi ay SGK gün hesabı
- SGK teşvikleri
- Asgari kurumlar vergisi
- KDV matrah ve tevkifat formülleri

Bu alanlar kaynak-backed rule/formül PR'larında eklenecektir.
