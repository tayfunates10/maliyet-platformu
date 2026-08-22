# Widget v1.1 entegrasyonu

Widget v1.1, PR #25'in güvenli public projection sözleşmesini korur ve yalnız görünüm ayarları ekler.

## Assetler

```html
<link rel="stylesheet" href="https://CDN_HOST/widget/v1.1.0/styles.css">
<script
  src="https://CDN_HOST/widget/v1.1.0/loader.js"
  data-maliyet-api-base="https://API_HOST"
  defer
></script>
```

Yayımlanmış semver asset path'i immutable'dır. `v1.0.0` dosyası geriye dönük kullanıcılar için değiştirilmez.

## HTML bootstrap

```html
<div
  data-maliyet-widget
  data-deployment-id="8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b"
  data-maliyet-theme="auto"
  data-maliyet-locale="tr"
  data-maliyet-density="comfortable"
  data-maliyet-show-title="true"
></div>
```

## Güvenli config allowlist

`theme` yalnız `auto`, `light`, `dark`.

`locale` yalnız `tr`, `en`.

`density` yalnız `comfortable`, `compact`.

`showTitle` yalnız boolean veya HTML dataset için `true` / `false`.

Başka değerler API request'i ve quota rezervasyonu oluşmadan önce reddedilir. Config finansal formül, oran, fiyat, marj, vergi, tenant kimliği veya API request hedefi üretmez.

## Programmatic mount

```js
await MaliyetWidget.mount("#teklif", {
  deploymentId: "8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b",
  apiBase: "https://API_HOST",
  theme: "dark",
  locale: "tr",
  density: "compact",
  showTitle: true,
});
```

`apiBase` HTTPS olmak zorundadır. Browser request'i basit GET olarak kalır; Authorization, API key, body veya cookie gönderilmez.

## CSS custom properties

Marka görünümü host sitenin kendi stylesheet'inde tanımlanır:

```css
[data-maliyet-widget] {
  --maliyet-widget-bg: #ffffff;
  --maliyet-widget-text: #17202a;
  --maliyet-widget-border: #d7dce3;
  --maliyet-widget-radius: 14px;
  --maliyet-widget-font-family: system-ui, sans-serif;
  --maliyet-widget-title-size: 1rem;
  --maliyet-widget-range-size: 1.25rem;
  --maliyet-widget-bg-dark: #151a21;
  --maliyet-widget-text-dark: #f5f7fa;
  --maliyet-widget-border-dark: #343b46;
  --maliyet-widget-error: #8b1e1e;
}
```

SDK arbitrary CSS string, class name, HTML veya JavaScript config kabul etmez ve inline style üretmez.

## Decimal gösterimi

`estimate_min` ve `estimate_max` server tarafından decimal string olarak gelir ve aynen gösterilir. SDK `Number`, `parseFloat` veya `Intl.NumberFormat` ile browser-side yeniden hesaplama yapmaz.

## CSP

Örnek politika:

```text
Content-Security-Policy:
  default-src 'self';
  script-src 'self' https://CDN_HOST;
  style-src 'self' https://CDN_HOST;
  connect-src 'self' https://API_HOST;
```

`unsafe-inline` ve `unsafe-eval` gerekli değildir.

## Güvenlik sınırı

- `Origin` authentication değildir.
- Exact-origin kararı API katmanındadır.
- Deployment UUID public identifier'dır.
- Widget yalnız customer-safe projection allowlist alanlarını render eder.
- Private maliyet, kâr, marj, ruleset veya internal snapshot alanları SDK tarafından okunmaz/render edilmez.
- `429`, `403`, `404` gibi hata body'leri kullanıcı DOM'una taşınmaz.
