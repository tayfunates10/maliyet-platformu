# Widget v1.2 entegrasyonu

Widget v1.2, immutable server-published branding snapshot'ını aynı public projection GET yanıtından güvenli şekilde tüketir. Finansal hesap, mevzuat kuralı, secret veya private tenant alanı browser'a taşınmaz.

## Assetler

```html
<link rel="stylesheet" href="https://CDN_HOST/widget/v1.2.0/styles.css">
<script
  src="https://CDN_HOST/widget/v1.2.0/loader.js"
  data-maliyet-api-base="https://API_HOST"
  defer
></script>
```

`v1.0.0`, `v1.1.0` ve `v1.2.0` published semver path'leri immutable kabul edilir. Yeni davranış eski dosyalar değiştirilerek yayınlanmaz.

## Server-published presentation

API, deployment için presentation yayınlanmışsa mevcut projection JSON'una `presentation` alanı ekler. SDK yalnız şu allowlist'i kabul eder: `theme`, `locale`, `density`, `show_title`, yedi `#RRGGBB` renk token'ı, `border_radius_px` ve `font_family`.

Eksik olmayan ama malformed bir `presentation` objesi `invalid_response` ile fail-closed sonuçlanır. `presentation` alanının hiç bulunmaması geçerlidir ve eski default davranışı korur.

## Precedence

Görsel seçeneklerde sıra şöyledir:

1. programmatic mount option
2. HTML dataset option
3. server-published presentation
4. SDK default

Örneğin server `theme=dark` yayınlamış olsa bile embed `theme: "light"` ile açıkça override edebilir. Renk, radius ve font için programmatic/dataset API yoktur; yayınlanmış snapshot varsa SDK bunları uygular.

## Güvenli CSS token eşleme

Server renkleri yalnız uppercase `#RRGGBB`, radius yalnız `0..32` integer ve font yalnız `system | sans | serif | monospace` olabilir. Loader bu değerleri sabit CSS custom property isimlerine `style.setProperty` ile yazar. Payload CSS selector, CSS property adı, class name, HTML, JavaScript, URL, `url(...)` veya `@import` üretemez.

Font token'ları doğrudan CSS olarak kullanılmaz; SDK içindeki sabit font stack'lerine eşlenir.

## Decimal gösterimi

`estimate_min` ve `estimate_max` decimal string olarak kalır. SDK browser-side finansal dönüşüm veya hesaplama için `Number`, `parseFloat` ya da `Intl.NumberFormat` kullanmaz.

## Request sözleşmesi

Projection request'i tek istek olarak kalır:

- `GET`
- `mode: "cors"`
- `credentials: "omit"`
- `cache: "no-store"`
- `redirect: "error"`
- `referrerPolicy: "no-referrer"`

Authorization, API key, cookie veya request body eklenmez. Branding için ikinci request ve ikinci quota rezervasyonu yoktur.

## CSP

Örnek politika:

```text
Content-Security-Policy:
  default-src 'self';
  script-src 'self' https://CDN_HOST;
  style-src 'self' https://CDN_HOST;
  connect-src 'self' https://API_HOST;
```

SDK `innerHTML`, `eval`, `Function`, generated `<style>` veya `setAttribute("style", ...)` kullanmaz. `unsafe-eval` gerekli değildir.

## Güvenlik sınırı

- Exact Origin kararı yalnız API tarafındadır; Origin authentication değildir.
- Quota PostgreSQL atomic reservation otoritesinde kalır.
- Public response içindeki ekstra/private alanlar render edilmez.
- Malformed server presentation güvenli default'a sessizce düşmez; fail-closed olur.
- SDK finansal formül, vergi oranı, marj, ruleset veya tenant secret işlemez.
