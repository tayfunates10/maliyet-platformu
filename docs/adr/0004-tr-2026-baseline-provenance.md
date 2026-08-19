# ADR 0004 — Türkiye 2026 Baseline Veri Provenance Politikası

- Durum: Kabul edildi
- Tarih: 2026-08-19

## Amaç

Production mevzuat verisinin uygulama koduna karışmasını ve kaynağı doğrulanmamış oranların sisteme girmesini engellemek.

## Karar

1. Production oran/eşik verileri `data/` altında manifest olarak tutulur; Python/TypeScript kaynak koduna sabit yazılmaz.
2. Her source kaydı resmi kurum URL'si, resmi referans, review tarihi ve SHA-256 taşır.
3. Çalışma ortamı resmi PDF/HTML byte'larını doğrudan materialize edemediğinde hash uydurulmaz. Bunun yerine yalnız hesapta kullanılan doğrulanmış gerçekler küçük bir `normalized_evidence` capture dosyasına alınır ve `content_sha256` bu repository içi evidence dosyasının exact byte hash'idir.
4. Capture dosyası açıkça bunun remote PDF/HTML hash'i olmadığını yazar. Remote byte hash ileride ingest pipeline tarafından alınabilirse yeni source revision olarak kaydedilir.
5. Loader her capture hash'ini yükleme öncesi doğrular; mismatch fail-closed olur.
6. Manifest Pydantic `extra=forbid` şemasıyla parse edilir. Binary float rules-engine tarafından reddedilir.
7. Aynı dataset tekrar yüklenebilir; mevcut source/definition/version ile manifest arasında drift varsa update edilmez, hata verilir.
8. 2026'ya özgü kurallar 2027'ye taşmaz. Açık uçlu kurallar yalnız resmi yürürlük kaynağı bunu destekliyorsa açık uçlu tutulur.

## İlk baseline kapsamı

- 2026 ücret dışı gelir vergisi tarifesi
- 2026 ücret gelir vergisi tarifesi
- 2026 gelir vergisi mükellefi genel geçici vergi oranı
- 2026 genel kurumlar vergisi oranı
- 2026 genel kurum geçici vergi oranı
- KDV List I / List II / default oran sınıfları
- 2026 özel sektör 4/a PEK alt/üst sınırları
- genel 4/a işveren/çalışan prim bileşenleri
- 4/a SGDP oranları

## Bilinçli kapsam dışı

- Yurt içi asgari kurumlar vergisinin istisna/muafiyet matcher'ı
- üretim/ihracat kurumlar vergisi indirimleri
- KDV mal/hizmet sınıflandırma motoru
- KDV tevkifatı
- stopaj kural paketleri
- 4/b ve tüm teşvik senaryoları

Bu kapsam dışı alanlar doğruluk gereği ayrı review edilebilir PR'larda eklenecektir.
