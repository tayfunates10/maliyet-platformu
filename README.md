# Maliyet Platformu

Türkiye'deki işletmeler için sektör bazlı maliyet, kârlılık, sermaye ve finansal karar destek platformu.

## Ürün kapsamı

İlk sürüm sekiz faaliyet alanını destekleyecek:

- İmalat: gıda ürünleri, tekstil ürünleri, ana metal.
- Hizmet/ticaret: e-ticaret, ticaret, ulaştırma, konaklama, turizm.

Platform tek bir hesaplama çekirdeğini SaaS web uygulaması, gömülebilir widget, API, WordPress entegrasyonu ve ileride white-label dağıtım kanalları üzerinden sunacaktır.

## Temel mühendislik ilkeleri

1. Vergi, SGK, KDV veya diğer mevzuat oranları uygulama koduna sabit yazılmaz; tarihçeli kural kayıtlarından çözülür.
2. Parasal hesaplarda binary floating-point kullanılmaz. Finansal hesaplar `Decimal`/fixed-precision yaklaşımıyla yapılır.
3. Geçmiş hesaplamalar, hesaplandıkları kural sürümü ve girdi snapshot'ı ile yeniden üretilebilir olmalıdır.
4. Tenant verisi birbirinden izole edilir. Müşteriye gösterilen sonuç ile işletmenin iç maliyet sonucu ayrı yetki katmanlarında tutulur.
5. Her değişiklik pull request üzerinden ilerler; CI başarısızsa PR tamamlanmış sayılmaz.

## Repository yapısı

```text
.
├── services/api/          # FastAPI tabanlı hesaplama/API servisi
├── docs/                  # Mimari, ürün kapsamı ve ADR kayıtları
├── scripts/               # Repository kalite kontrolleri
├── .github/workflows/     # CI kalite kapıları
└── AGENTS.md              # İnsan ve AI geliştiriciler için devralma sözleşmesi
```

Web uygulaması ayrı bir stacked PR ile `apps/web` altında eklenecektir.

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

Repository yapısal sözleşmesini doğrulamak için:

```bash
python scripts/check_repository_contract.py
```

## Pull request politikası

PR'lar küçük, tek amaçlı ve bağımsız incelenebilir olmalıdır. Her PR açıklamasında kapsam, mimari etkiler, değişen dosyalar, test sonuçları, güvenlik/mevzuat etkileri, bilinen eksikler ve sonraki adım bulunmalıdır. Ayrıntılar için `docs/engineering/pr-quality-gates.md` dosyasına bakın.

## Durum

Foundation geliştirmesi devam ediyor. Bu repository henüz production kullanıma hazır değildir.
