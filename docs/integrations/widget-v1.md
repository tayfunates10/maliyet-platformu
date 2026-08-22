# Widget SDK v1 entegrasyon sözleşmesi

Bu belge public hesaplama widget'ının `1.0.0` browser sözleşmesini tanımlar. SDK yalnız daha önce yayımlanmış customer-safe `PublicCalculationProjection` verisini gösterir; maliyet motoru, vergi formülü, işletme içi maliyet, kâr/marj detayı veya tenant kimlik bilgisi browser bundle'ına taşınmaz.

## Sabit sürüm yolu

İlk public loader yolu:

```text
/widget/v1.0.0/loader.js
```

Bu yol yayımlandıktan sonra immutable kabul edilir. Davranış değişikliği veya hata düzeltmesi yeni bir semver yolu ile çıkarılır. Aynı sürüm yolunun içeriği sessizce değiştirilmez.

## Temel embed

Production CDN ve API hostname'leri release/deployment aşamasında belirlenecektir. Entegrasyon biçimi şöyledir:

```html
<div
  data-maliyet-widget
  data-deployment-id="8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b"
></div>
<script
  src="https://cdn.example.com/widget/v1.0.0/loader.js"
  data-maliyet-api-base="https://api.example.com"
  defer
></script>
```

`data-deployment-id` public bir deployment kimliğidir; secret değildir. `data-maliyet-api-base` de public API origin/path bilgisidir. Browser'a API key, bearer token, client secret veya tenant credential verilmez.

## Manuel mount

SDK `window.MaliyetWidget` altında immutable bir yüzey sunar:

```js
await MaliyetWidget.mount("#teklif", {
  deploymentId: "8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b",
  apiBase: "https://api.example.com",
});
```

Public API:

- `MaliyetWidget.version` → `"1.0.0"`
- `MaliyetWidget.mount(target, options)`
- `MaliyetWidget.mountAll(root?)`

Aynı DOM elemanına başarılı ikinci `mount()` çağrısı yeni network isteği üretmez; bu davranış aynı widget'ın kotayı yanlışlıkla iki kez tüketmesini engeller.

## Network sözleşmesi

SDK yalnız şu customer-safe endpoint'e `GET` yapar:

```text
{apiBase}/organizations/widget/deployments/{deploymentId}/projection
```

İstek:

- `GET` metodudur;
- custom authorization header göndermez;
- request body göndermez;
- browser credential/cookie göndermez (`credentials: omit`);
- CORS modunda çalışır;
- redirect takip etmez;
- referrer göndermez;
- browser cache kullanmaz.

Bu basit GET tasarımı PR #24'teki exact `Origin` güvenlik sınırını korur. API'nin `Access-Control-Allow-Origin` davranışı exact allowlist olmaya devam eder. Loader dosyasının kendisi public ve secretsiz bir static asset olduğundan cross-origin yüklenebilmesi için asset response'u `Access-Control-Allow-Origin: *` kullanabilir; bu wildcard finansal API endpoint'lerine uygulanmaz.

## Render edilen alanlar

Loader yalnız şu alanları kullanır:

- `title`
- `currency`
- `estimate_min`
- `estimate_max`

Sunucudan gelen metin DOM'a `textContent` ile yazılır. Ham HTML yorumlanmaz. Response'taki tanınmayan alanlar render edilmez ve event payload'ına taşınmaz.

Host site şu class'ları kendi CSS'iyle biçimlendirebilir:

- `.maliyet-widget__card`
- `.maliyet-widget__title`
- `.maliyet-widget__range`
- `.maliyet-widget__error`

SDK inline style üretmez.

## CSP

Host site, kendi CSP politikasında gerçek CDN ve API origin'lerini açıkça allowlist etmelidir. Örnek:

```text
Content-Security-Policy: script-src 'self' https://cdn.example.com; connect-src 'self' https://api.example.com;
```

Loader dinamik kod derleme veya inline script enjeksiyonu gerektirmez. `script-src` yalnız loader'ın geldiği origin'i, `connect-src` yalnız public projection API origin'ini kapsamalıdır.

## Origin kaydı

Widget'ın çalışacağı gerçek site origin'i tenant yönetim API'sinde exact HTTPS origin olarak kaydedilmiş olmalıdır. Örneğin `https://shop.example.com` kaydı `https://sub.shop.example.com` veya `http://shop.example.com` için yetki vermez.

Internationalized hostname'ler PR #24'ün browser-compatible non-transitional UTS #46 canonicalization kuralına göre eşleştirilir.

## Browser eventleri

Başarılı mount:

```text
maliyet:ready
```

Detail yalnız SDK sürümünü taşır.

Başarısız mount:

```text
maliyet:error
```

Detail yalnız stabil bir public error code taşır. Sunucunun ham hata body/subsystem detayları event'e veya DOM'a aktarılmaz.

Public error code'lar:

- `invalid_configuration`
- `invalid_target`
- `invalid_response`
- `origin_denied`
- `not_found`
- `quota_exceeded`
- `request_failed`

## Kapsam dışı

Bu ilk SDK sözleşmesi theme configuration, lead formu, quote akışı, framework wrapper'ları, WordPress plugin, custom domain, SRI release manifesti ve CDN deployment otomasyonunu kapsamaz. Bunlar ayrı PR'larda eklenir; server-side calculation authority ve public/private veri sınırı değişmez.
