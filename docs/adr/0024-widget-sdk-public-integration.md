# ADR 0024: Widget SDK public integration contract

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

ADR 0023 ve PR #24 browser widget erişimi için server-side güvenlik sınırını kurdu: exact HTTPS origin allowlist, customer-safe public projection ve PostgreSQL üzerinde atomik kota. Sıradaki ihtiyaç, üçüncü taraf işletme sitelerinin bu sınırı bozmadan yükleyebileceği küçük ve versioned bir browser SDK'dır.

Browser bundle'ı finansal hesaplama otoritesi olamaz. Third-party sayfaya gönderilen JavaScript kullanıcı tarafından okunabilir/değiştirilebilir; bu nedenle formül, vergi kuralı, tenant secret veya private hesap snapshot'ı hiçbir zaman SDK içine taşınamaz.

## Decision

### Versioned immutable asset

İlk loader exact olarak `/widget/v1.0.0/loader.js` yolunda yayınlanır. Bu path release edildikten sonra immutable kabul edilir. Davranışsal değişiklik yeni semver path gerektirir.

### Public SDK surface

SDK classic external script olarak yüklenir ve tek global yüzey oluşturur:

- `MaliyetWidget.version`
- `MaliyetWidget.mount(target, options)`
- `MaliyetWidget.mountAll(root?)`

Aynı element için başarılı mount sonucu memoize edilir; tekrarlanan mount çağrısı ikinci quota reservation üretmez.

### Bootstrap data

Auto-mount hedefi `[data-maliyet-widget]` elemanıdır. Public deployment UUID `data-deployment-id` üzerinden, API base ise script veya element `data-maliyet-api-base` üzerinden sağlanabilir.

Deployment ID ve API base secret değildir. API key, OAuth credential, bearer token veya tenant secret browser'a verilmez.

### Network boundary

SDK yalnız PR #24'ün customer-safe projection endpoint'ine basit CORS `GET` yapar. İstek body/custom auth header içermez ve `credentials: omit` kullanır. Redirect reddedilir, referrer gönderilmez ve response browser cache'ine bırakılmaz.

Bu karar browser'ın gerçek page `Origin` header'ını göndermesine izin verir ve unnecessary preflight/auth katmanı eklemeden ADR 0023 exact-origin kontrolünü korur.

### Static asset CORS vs API CORS

Loader public, secretsiz ve cacheable bir static asset'tir. Yalnız `/widget/v1.0.0/loader.js` response'u cross-origin distribution için `Access-Control-Allow-Origin: *` kullanabilir.

Bu wildcard bir API authorization politikası değildir. Public projection API'si ADR 0023'teki exact `Access-Control-Allow-Origin` davranışını korur; API üzerinde wildcard yasaktır.

Static loader ayrıca:

- `Cross-Origin-Resource-Policy: cross-origin`
- `X-Content-Type-Options: nosniff`
- `Cache-Control: public, max-age=31536000, immutable`

header'larıyla servis edilir.

### Safe rendering

SDK public projection response'undan yalnız `title`, `currency`, `estimate_min`, `estimate_max` alanlarını kabul eder. Tanınmayan response alanları düşürülür.

Server text'i yalnız DOM `textContent` ile yazılır. HTML injection, dynamic code compilation ve executable template mekanizmaları kullanılmaz.

SDK public hata event'lerine server error body, stack trace, tenant ID veya internal alan taşımaz.

### CSP compatibility

SDK host site üzerinde external script + fetch dışında yürütme primitive'i gerektirmez. Entegratör gerçek CDN origin'ini `script-src`, gerçek API origin'ini `connect-src` içinde allowlist eder. SDK inline style/script veya dynamic code execution gerektirmez.

## Consequences

- Formül ve private finans verisi browser bundle'ına taşınmadan üçüncü taraf siteler embed yapabilir.
- Browser exact-origin kontrolü doğal `Origin` header ile çalışmaya devam eder.
- Aynı elementin tekrar mount edilmesi gereksiz quota tüketmez.
- Public asset uzun süre immutable cache edilebilir; yeni davranış sürüm yolunu değiştirir.
- Host site CSS class'larını biçimlendirebilir; SDK inline style dayatmaz.
- Loader hostname/CDN henüz production deployment kararı değildir; bu PR yalnız public integration contract'ı kurar.

## Deferred

- Production CDN hostname ve deployment pipeline.
- Subresource Integrity manifest/release signing.
- Theme/config schema.
- Lead/quote capture.
- React/Vue wrapper'ları.
- WordPress/WooCommerce plugin.
- Custom domain/white-label loader aliases.
