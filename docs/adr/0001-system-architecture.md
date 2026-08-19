# ADR-0001: Sistem mimarisi ve bounded-context ayrımı

- Durum: Accepted
- Tarih: 2026-08-19

## Bağlam

Aynı hesaplama motoru SaaS arayüzü, widget, WordPress ve API üzerinden kullanılacak. Sektör kuralları ile Türkiye mevzuatının hızla değişebilmesi, hesaplama sonuçlarının tarihsel olarak yeniden üretilebilir olmasını gerektiriyor.

## Karar

Sistem modüler monolith ile başlayacak ve açık bounded-context sınırları kullanacaktır:

- Identity & Organizations
- Tax/Accounting Rules
- Costing Core
- Capital & Finance
- Sector Modules
- Calculation Ledger
- Reporting
- Integration/API

API katmanı FastAPI ile başlatılır. Web arayüzü bağımsız `apps/web` uygulaması olarak Next.js App Router kullanacaktır. PostgreSQL kalıcı veri deposu olacaktır. API ve web doğrudan birbirlerinin internal domain koduna bağlanmayacak; sözleşmeler OpenAPI/JSON Schema üzerinden paylaşılacaktır.

## Gerekçe

Mikroservisleri ilk günden kullanmak operasyonel yükü gereksiz artırır. Tek modüler servis ise transaction, audit ve mevzuat tutarlılığını ilk sürümde daha kolay korur. Bounded-context sınırları daha sonra gerekirse servis ayrıştırmasına izin verir.

## Finansal doğruluk kararı

Para ve oran hesapları decimal/fixed-precision temellidir. Vergi ve SGK oranları tarihçeli rules-engine kayıtlarıdır; kod sabiti değildir. Hesaplama ledger'ı input/rule/engine snapshot kimliklerini saklar.

## Sonuçlar

- Domain mantığı HTTP route'larından bağımsız tutulmalıdır.
- Sector modülleri ortak çekirdeği kopyalamamalı, yalnız kendi sürücülerini/kurallarını sağlamalıdır.
- Widget/partner API hiçbir zaman organization-internal maliyet alanlarını varsayılan response'a dahil etmemelidir.
