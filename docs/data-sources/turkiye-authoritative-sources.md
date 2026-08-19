# Türkiye Resmi Veri ve Mevzuat Kaynakları

Bu belge veri ingest çalışmalarında kullanılacak kaynak sınıflarını tanımlar.
Burada oran/eşik kopyalanmaz; gerçek değerler ayrı, review edilebilir veri PR'ları
ile source hash ve yürürlük dönemi birlikte yüklenir.

## Gelir İdaresi Başkanlığı (GİB)

Ana vergi mevzuatı için birincil uygulama kaynağı:

- `https://gib.gov.tr/mevzuat/arama`
- `https://www.gib.gov.tr/vergi-takvimi`

Mevzuat araması Gelir Vergisi, Vergi Usul, Kurumlar Vergisi, KDV, ÖTV, MTV,
Damga Vergisi ve ilgili karar/tebliğ/sirküler kayıtlarını takip etmek için
kullanılır. Bir kuralın yalnız kanun numarası değil, onu değiştiren karar/tebliğ
ve yürürlük bilgileri de provenance kaydına bağlanmalıdır.

## Sosyal Güvenlik Kurumu (SGK)

Personel ve sosyal güvenlik maliyetleri için `https://www.sgk.gov.tr/` altındaki
resmi 4/a, 4/b, prime esas kazanç, prim oranı ve teşvik açıklamaları kullanılır.
SGK kayıtlarında sigortalı statüsü ve geçerlilik dönemi applicability alanının
parçasıdır.

## Ticaret Bakanlığı / ETBİS

E-ticaret yükümlülükleri için:

- `https://ticaret.gov.tr/ic-ticaret/elektronik-ticaret/mevzuat`
- `https://etbis.ticaret.gov.tr/tr/Legislation`

6563 sayılı Kanun ve ikincil düzenlemeler source provenance ile izlenir.

## TÜİK sınıflamaları

Sektör ve NACE bağlamı için TÜİK resmi sınıflama servisi kullanılır. NACE kodu
bir vergi oranı değildir; applicability/sector context üretmek için kullanılır.

## Ingest kuralı

Her production rule kaydı en az şunları taşımadan kabul edilmez:

- resmi kurum,
- canonical kaynak URL,
- source türü,
- resmi referans/kanun/karar/tebliğ bilgisi (varsa),
- yayın tarihi (varsa),
- erişim zamanı,
- kaynak içeriğinin SHA-256 değeri,
- `effective_from` ve gerektiğinde `effective_to`,
- applicability kapsamı,
- Decimal-safe payload,
- review/test kanıtı.
