# AGENTS.md — İnsan ve AI Geliştirici Devralma Sözleşmesi

Bu dosya repository üzerinde çalışan her insan veya AI geliştiricinin önce okuması gereken kanonik çalışma sözleşmesidir.

## 1. Ürün amacı

Maliyet Platformu; Türkiye mevzuatını dikkate alan, sektör bazlı gerçek maliyet, kâr/zarar, fiyatlandırma, sermaye ve senaryo analizi yapan çok kiracılı (multi-tenant) bir SaaS platformudur.

## 2. Kilitli sektör kapsamı

İmalat: gıda, tekstil, ana metal.
Hizmet/ticaret: e-ticaret, ticaret, ulaştırma, konaklama, turizm.

E-ticaret bir NACE sektörü gibi modellenmez; satış kanalı/operasyon modeli olarak sektör motorlarına bağlanabilir.

## 3. Değiştirilemez teknik ilkeler

- Mevzuat oranı ve parasal eşik kod içine hard-code edilmez.
- Tüm mevzuat kuralları `effective_from`, `effective_to`, kaynak, sürüm ve kapsam bilgisi taşır.
- Para hesapları binary `float` ile yapılmaz.
- Hesaplama sonucu; giriş snapshot'ı, kural snapshot'ı ve motor sürümü ile audit edilebilir olmalıdır.
- Tenant izolasyonu güvenlik sınırıdır; organizasyonlar arası veri sızıntısı kabul edilemez.
- Public/widget sonucu, işletme içi gerçek maliyet detaylarını varsayılan olarak içermez.
- Bir PR'ın amacı başka bir PR'ın kapsamını gizlice genişletmemelidir.
- CI kırmızıysa iş tamamlandı olarak raporlanmaz.

## 4. Git/PR akışı

- `main` production-line ana daldır.
- Her yeni PR güncel `main` dalından açılır.
- Geliştirme `feat/NNN-kisa-ad`, `fix/NNN-kisa-ad`, `chore/NNN-kisa-ad` dallarında yapılır.
- Açık stacked PR zinciri kullanılmaz; önceki PR merge edilmeden sonraki PR başlatılmaz.
- Tüm zorunlu CI kapıları yeşilse PR squash merge ile `main`e alınır.
- Merge sonrası sıradaki PR yeniden güncel `main` dalından açılır.
- CI, migration veya güvenlik kapılarından biri kırmızıysa merge yapılmaz.

## 5. PR teslim raporu

Her PR açıklaması en az şunları içerir:

1. Amaç ve kapsam.
2. Kapsam dışı bırakılanlar.
3. Mimari karar ve gerekçe.
4. Değişen dosyalar/modüller.
5. Test komutları ve sonuçları.
6. Güvenlik/tenant etkisi.
7. Mevzuat/veri kaynağı etkisi.
8. Migration/deployment etkisi.
9. Bilinen riskler ve açık işler.
10. Sonraki PR.

## 6. Kod kalitesi

- İsimler alan dilini açıkça ifade etmelidir; belirsiz `data`, `value`, `thing` gibi isimlerden kaçının.
- Fonksiyonlar tek sorumluluk taşımalıdır.
- Domain kuralları route/controller içine gömülmemelidir.
- Dış sistemler adapter sınırı arkasında tutulmalıdır.
- Yeni davranış testsiz eklenmez.
- Financial rounding açık bir politika ile uygulanır; çağıranın rastgele `round()` kullanmasına izin verilmez.
- Tenant-owned tablo ilişkileri yalnız uygulama filtresine bırakılmaz; mümkün olduğunda veritabanı constraint'leri ile de korunur.
- Migration dosyaları geri alınabilir olmalı ve model metadata'sı ile drift testinden geçmelidir.

## 7. Devralma sırası

Yeni geliştirici şu sırayla okumalıdır:

1. `README.md`
2. `AGENTS.md`
3. `docs/product-scope.md`
4. `docs/adr/0001-system-architecture.md`
5. İlgili sonraki ADR
6. `docs/engineering/pr-quality-gates.md`
7. İlgili açık PR'ın açıklaması ve yorumları
