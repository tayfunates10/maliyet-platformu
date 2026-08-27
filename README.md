# Maliyet Platformu

Türkiye'deki işletmeler için sektör bazlı maliyet, kârlılık, sermaye ve finansal karar destek platformu.

## Ürün kapsamı

İlk sürüm sekiz faaliyet alanını destekler:

- İmalat: gıda ürünleri, tekstil ürünleri, ana metal.
- Hizmet/ticaret: e-ticaret, ticaret, ulaştırma, konaklama, turizm.

Platform aynı güvenli hesaplama ve provenance sınırlarını SaaS web uygulaması, gömülebilir widget, Partner API ve WordPress entegrasyonu üzerinden sunar. White-label dağıtım ilk sürüm sonrası genişleme alanıdır.

## Temel mühendislik ilkeleri

1. Vergi, SGK, KDV veya diğer mevzuat oranları uygulama koduna sabit yazılmaz; tarihçeli kural kayıtlarından çözülür.
2. Parasal hesaplarda binary floating-point kullanılmaz. Finansal hesaplar `Decimal`/fixed-precision yaklaşımıyla yapılır.
3. Geçmiş hesaplamalar, hesaplandıkları kural sürümü ve girdi snapshot'ı ile yeniden üretilebilir olmalıdır.
4. Tenant verisi birbirinden izole edilir. Müşteriye gösterilen sonuç ile işletmenin iç maliyet sonucu ayrı yetki katmanlarında tutulur.
5. Her değişiklik pull request üzerinden ilerler; CI başarısızsa PR tamamlanmış sayılmaz.

## Repository yapısı

```text
.
├── apps/web/              # Next.js SaaS web uygulaması ve immutable Widget SDK
├── services/api/          # FastAPI hesaplama, tenant, rapor ve partner API servisi
├── data/tr/2026/          # Kaynak-hash doğrulamalı TR-2026 mevzuat baseline'ı
├── integrations/          # WordPress entegrasyonu
├── docs/                  # Mimari, ürün kapsamı ve operasyon sözleşmeleri
├── scripts/               # Repository ve production kalite kontrolleri
├── .github/workflows/     # CI ve provenance'lı production release
└── AGENTS.md              # İnsan ve AI geliştiriciler için devralma sözleşmesi
```

## Yerel geliştirme

API geliştirme ortamı Python 3.14 hedefler.

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy app
pytest
```

Repository ve ilk sürüm sözleşmelerini doğrulamak için repository kökünde:

```bash
python scripts/check_repository_contract.py
python scripts/check_first_release_scope.py
```

## Pull request politikası

PR'lar küçük, tek amaçlı ve bağımsız incelenebilir olmalıdır. Her PR açıklamasında kapsam, mimari etkiler, değişen dosyalar, test sonuçları, güvenlik/mevzuat etkileri, bilinen eksikler ve sonraki adım bulunmalıdır. Ayrıntılar için `docs/engineering/pr-quality-gates.md` dosyasına bakın.

## Durum

Kanonik ilk sürüm kapsamı: **TAMAM**.

Repository; sekiz sektör motoru, ortak finansal karar yetenekleri, rule-resolved personel/mevzuat sınırları, immutable calculation provenance, tenant izolasyonu, SaaS web, Widget SDK, Partner API, WordPress, CSV/XLSX/DOCX/PDF raporları, production container'ları, migration + regulatory-baseline + readiness rollout zinciri ve provenance/SBOM üretimli release workflow'unu içerir.

Bu durum kod ve repository kapsamının tamamlandığını ifade eder; canlı production yayını ayrıca gerçek registry digest'leri, production `DATABASE_URL`, `API_BASE_URL`, TLS/reverse proxy ve operatör rollout ceremony'si gerektirir. Bu dış ortam girdileri repository içine gömülmez veya CI'da sahte production kanıtı olarak kullanılmaz.
