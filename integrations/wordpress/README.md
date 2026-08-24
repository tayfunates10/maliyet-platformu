# Maliyet Platformu WordPress Widget

İlk sürüm WordPress entegrasyonu, mevcut immutable public Widget SDK `v1.2.0` yüzeyini shortcode üzerinden tüketir. Plugin finansal hesaplama yapmaz, API key/bearer/client secret taşımaz ve tenant-private response alanlarını WordPress sunucusuna proxy etmez.

## Kurulum

`maliyet-platformu-widget.php` dosyasını WordPress plugin klasörüne yerleştirin ve eklentiyi etkinleştirin.

## Shortcode

```text
[maliyet_widget deployment_id="8e8d7c2b-6a0b-4d2e-9a48-9a3115d6f44b" api_base="https://api.example.com" cdn_base="https://app.example.com"]
```

- `deployment_id`: public widget deployment UUID'sidir; secret değildir.
- `api_base`: exact HTTPS API origin'idir. Credential, path, query veya fragment kabul edilmez.
- `cdn_base`: immutable widget assetlerinin geldiği exact HTTPS origin'dir. Credential, path, query veya fragment kabul edilmez.

Aynı sayfada birden fazla shortcode kullanılabilir ancak hepsi aynı `api_base` ve `cdn_base` değerlerini kullanmalıdır. İkinci farklı origin kombinasyonu fail-closed olarak render edilmez.

## Güvenlik sınırı

Plugin yalnız şu assetleri yükler:

- `/widget/v1.2.0/styles.css`
- `/widget/v1.2.0/loader.js`

WordPress tarafında `wp_remote_get`/`wp_remote_post`, Authorization header, API key, bearer token veya tenant secret yoktur. Browser projection isteği mevcut Widget SDK tarafından `credentials: omit` ve exact Origin kontrolüyle yapılır. Gerçek WordPress site origin'i ilgili widget deployment allowlist'inde ayrıca kayıtlı olmalıdır.

SDK'nın server-side Decimal, mevzuat, quota ve public/private projection sınırları değişmez.
