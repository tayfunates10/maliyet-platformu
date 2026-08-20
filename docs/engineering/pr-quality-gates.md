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
- Alembic revision kimliği en fazla 32 karakter olmalı ve migration history tek head kalmalıdır.
- Beklenen uygulama tablo seti elle güncellenen sabit liste olmamalı; SQLAlchemy metadata'dan türetilmelidir.
- Çapraz-tenant okuma uygulama seviyesinde fail-closed test edilmelidir.
- Çapraz-tenant foreign-key/ownership ilişkileri veritabanı seviyesinde reddedilmelidir.
- Testler gerçek PostgreSQL üzerinde çalışmalıdır.

## HTTP/API integration testlerinde ek kapılar

- FastAPI veritabanı dependency override'ları ortak transaction-bound pytest fixture'ı üzerinden yapılmalıdır.
- Generator dependency, `lambda: generator()` biçiminde generator nesnesi döndürecek şekilde override edilmemelidir.
- HTTP JSON yanıtları UUID, tarih ve benzeri typed alanlarla karşılaştırılmadan önce Pydantic response model ile parse edilmelidir.
- Yetkilendirme testleri authentication, membership, role ve cross-tenant sınırlarını ayrı ayrı kapsamalıdır.
- Liste endpoint'leri sınırsız sonuç döndürmemeli; server-side üst sınırla pagination uygulamalıdır.

## CI çalışma disiplini

- GitHub Actions aynı PR/ref için `cancel-in-progress: true` kullanır; eski run'lar son head'in önüne geçmemelidir.
- Birbirine bağlı çoklu dosya değişiklikleri mümkün olduğunda tek bütünlüklü committe hazırlanır; her dosya için ayrı CI run tetiklemekten kaçınılır.
- CI kırıldığında hata mesajı/traceback kök nedene kadar okunur; yalnız semptomu kapatan eşik gevşetmesi veya skip eklenmez.
- Aynı hata sınıfı ikinci kez ortaya çıkabilecekse regression guard veya ortak fixture/helper eklenmeden iş tamamlanmış sayılmaz.

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
