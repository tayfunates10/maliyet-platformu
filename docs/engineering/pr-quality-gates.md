# Pull Request Kalite Kapıları

## Zorunlu kapılar

Her PR için, kapsam uygunsa:

- Unit tests
- Integration tests
- Lint
- Format check
- Static type check
- Build/package doğrulaması
- Repository contract check
- Güvenlik etkisi incelemesi
- Mevzuat etkisi incelemesi

## Finans/mevzuat değişikliklerinde ek kapılar

- Resmi kaynak URL/kurum adı PR açıklamasında bulunmalıdır.
- Kuralın `effective_from`/`effective_to` dönemi tanımlanmalıdır.
- Sınır değer testleri (`eşik-0.01`, `eşik`, `eşik+0.01`) eklenmelidir.
- Eski hesaplamaların yeniden üretilebilirliği regression testiyle korunmalıdır.
- Kalite eşiğini gevşeterek test geçirme kabul edilmez.

## Veritabanı/tenant değişikliklerinde ek kapılar

- Migration `upgrade -> downgrade -> upgrade` round-trip testinden geçmelidir.
- Alembic metadata drift kontrolü PASS olmalıdır.
- Çapraz-tenant okuma uygulama seviyesinde fail-closed test edilmelidir.
- Çapraz-tenant foreign-key/ownership ilişkileri veritabanı seviyesinde reddedilmelidir.
- Testler gerçek PostgreSQL üzerinde çalışmalıdır.

## PR boyutu ve merge sırası

PR tek bir amaç taşımalıdır. Büyük işler birbirini takip eden küçük PR'lara bölünür.
Her PR güncel `main` dalından açılır. Önceki PR tüm zorunlu kapılar yeşil olup
`main`e merge edilmeden sonraki PR başlatılmaz. Yeşil PR'lar squash merge ile
`main`e alınır; kırmızı PR merge edilmez.

## Teslim raporu şablonu

PR body şu başlıkları içermelidir:

- Amaç
- Kapsam
- Kapsam dışı
- Mimari kararlar
- Değişen dosyalar
- Test kanıtı
- Güvenlik etkisi
- Mevzuat/veri etkisi
- Migration/deployment etkisi
- Riskler/açık işler
- Sonraki PR
