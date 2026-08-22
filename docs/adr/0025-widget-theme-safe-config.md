# ADR 0025 — Widget theme + safe configuration contract

## Durum

Accepted.

## Bağlam

PR #25 ile `/widget/v1.0.0/loader.js` public browser SDK sözleşmesi yayımlandı. Bu asset immutable kabul edilir ve üçüncü taraf siteler yalnız customer-safe public projection endpoint'ini tüketebilir.

İşletmeler widget'ın görünümünü kendi sitelerine uyarlamak ister. Bu özelleştirme finansal hesap, tenant yetkisi, Origin kontrolü, quota veya private response alanları üzerinde hiçbir etki yaratmamalıdır.

## Karar

Yeni davranış `/widget/v1.1.0/loader.js` ve `/widget/v1.1.0/styles.css` ile yayımlanır. `v1.0.0` değiştirilmez.

SDK yalnız şu presentation seçeneklerini kabul eder:

- `theme`: `auto | light | dark`
- `locale`: `tr | en`
- `density`: `comfortable | compact`
- `showTitle`: boolean

Bunların dışındaki değerler network/quota işleminden önce `invalid_configuration` ile fail-closed olur.

Marka renkleri ve tipografi JavaScript config string'i olarak alınmaz. Host site yalnız belgelenmiş CSS custom property değerlerini kendi stylesheet'inde tanımlar. SDK inline style, arbitrary CSS, HTML veya JavaScript çalıştırmaz.

Para aralığı server'ın doğrulanmış decimal string değerleriyle render edilir. Browser tarafında `Number`, `parseFloat`, `Intl.NumberFormat` veya yeniden hesaplama uygulanmaz.

## Güvenlik etkisi

- API request contract PR #25 ile aynıdır: basit GET, CORS, `credentials: "omit"`, no-referrer.
- Deployment UUID public identifier olmaya devam eder; credential değildir.
- Exact Origin enforcement ve persistent quota authority PR #24 API katmanında kalır.
- Unknown/private response alanları render edilmez.
- Hata response body'leri DOM'a taşınmaz.
- Published semver asset path'leri immutable'dır.

## CSP

`script-src` loader origin'ini, `style-src` stylesheet origin'ini, `connect-src` public API origin'ini allowlist eder. SDK `unsafe-inline` veya `unsafe-eval` gerektirmez.

## Test

CI şu davranışları kilitler:

- v1.0.0 loader byte-level SHA-256 immutability;
- v1.1 loader/CSS boyut sınırları;
- dynamic code/executable HTML yasağı;
- auth header/credential yasağı;
- decimal string preservation;
- allowlisted theme/locale/density/showTitle;
- invalid config'in network öncesi reddi;
- private sentinel leak regression;
- repeated mount quota regression;
- CSP ve immutable asset header sözleşmesi.

## Kapsam dışı

- Tenant-persisted branding profile;
- logo/media upload;
- white-label custom domains;
- server-side public config resource;
- billing/plan entitlements;
- WordPress/WooCommerce plugin.

## Sonraki adım

PR #27 tenant-owned Widget Branding Profile persistence ve publishable public presentation snapshot.
