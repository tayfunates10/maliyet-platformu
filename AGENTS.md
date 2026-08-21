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
- Parolalar plaintext, reversible encryption veya hızlı genel amaçlı hash ile saklanmaz; versioned memory-hard password hashing zorunludur.
- Raw bearer/session token veritabanında saklanmaz.
- Organization bootstrap sırasında owner/creator/role kimliği request body'den seçilemez; ilk owner authenticated server identity'dir.
- TaxProfile vergi oranı, parasal eşik veya formül kaynağı değildir; bunlar yalnız versioned rules engine'den gelir.
- Mevcut TaxProfile `entity_type` değeri kanuni şirket türü taksonomisi olarak yorumlanamaz; yalnız beyan edilmiş uygulama bağlamıdır.
- TaxProfile yazma yetkisi yalnız authenticated `owner` ve `admin` rollerine aittir.
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
- Aynı PR için art arda gelen değişiklikler mümkün olduğunca tek, bütünlüklü committe toplanır; eski CI run'larının gereksiz kuyruk oluşturmasına izin verilmez.

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
- Alembic revision kimlikleri 32 karakteri geçmez; migration history tek head olarak kalır.
- Migration beklenen tablo listesi elle kopyalanmaz; SQLAlchemy metadata'dan türetilir.
- FastAPI veritabanı dependency override'ları ortak pytest fixture'ı üzerinden yapılır; generator nesnesi doğrudan dependency sonucu olarak döndürülmez.
- HTTP JSON yanıtları UUID/tarih gibi tiplerle karşılaştırılmadan önce typed response model ile doğrulanır.
- Parola alanına global whitespace trim uygulanmaz; kullanıcının girdiği parola byte dizisi doğrulama ve hash sırasında korunur.
- Başarısız giriş/lockout sayaçları güvenlik state'idir; 401 üretirken request rollback ile kaybolmalarına izin verilmez.
- Kimlik doğrulama hataları kullanıcı varlığını ifşa edecek farklı hata metinleri döndürmez.
- Logout caller'dan session ID kabul etmez; yalnız authenticated bearer'dan çözülen current-session ID revoke edilir.
- Tenant bootstrap transaction'ı organization + owner membership + zorunlu ilk profil + audit event tamamlanmadan başarılı sayılmaz.
- TaxProfile create/update işlemi profil mutasyonu ve audit event tamamlanmadan başarılı sayılmaz.
- `tax_rate`, bracket, threshold veya actor/role override alanları TaxProfile HTTP payload'ına eklenemez.

## 7. Devralma sırası

Yeni geliştirici şu sırayla okumalıdır:

1. `README.md`
2. `AGENTS.md`
3. `docs/product-scope.md`
4. `docs/adr/0001-system-architecture.md`
5. İlgili sonraki ADR
6. `docs/engineering/pr-quality-gates.md`
7. İlgili açık PR'ın açıklaması ve yorumları
