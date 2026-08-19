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

## PR boyutu

PR tek bir amaç taşımalıdır. Büyük değişiklikler stacked PR'lara bölünür. Alt PR, bağımlı olduğu branch'i base alabilir; üst PR merge edilince alt PR `main`e retarget edilir.

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
