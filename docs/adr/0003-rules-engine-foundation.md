# ADR 0003 — Tarihçeli Mevzuat Rules Engine ve Kaynak Provenance

- Durum: Kabul edildi
- Tarih: 2026-08-19

## Bağlam

Türkiye'deki vergi, sosyal güvenlik ve sektör yükümlülükleri yalnız bir oran
listesi değildir. Kuralın yürürlük tarihi, mükellef/statü kapsamı, resmi kaynak
ve sonradan değişen düzenlemeler hesap sonucunu etkiler. Geçmiş bir hesabın yeni
bir oranla sessizce yeniden hesaplanması kabul edilemez.

## Karar

1. Mantıksal kural kimliği `RuleDefinition` ile sabit tutulur.
2. Her değişiklik yeni bir `RuleVersion` kaydıdır; eski version üzerine yazılmaz.
3. `effective_from` dahildir, `effective_to` hariçtir. `effective_to = NULL`
   açık uçlu geçerlilik anlamına gelir.
4. Bir tarih için sıfır aktif version varsa resolution fail-closed olur.
5. Aynı tarih için birden fazla aktif version varsa sistem birini tahmin ederek
   seçmez; configuration error ile fail-closed olur.
6. Her version bir `RuleSource` kaydına bağlanır. Kaynak; kurum, tür, başlık,
   canonical URL, resmi referans, yayın tarihi, erişim zamanı ve SHA-256 içerir.
7. Rule payload içindeki oran ve parasal değerler decimal string olarak taşınır.
   Binary floating point payload kabul edilmez.
8. Payload deterministik JSON üzerinden SHA-256 ile mühürlenir.
9. Calculation tarafı canlı/current kural kimliği saklamakla yetinmez; seçilen
   rule version + payload + source provenance snapshot'ını saklar.
10. Bu PR gerçek vergi oranı yüklemez. Test oranları açıkça sentetiktir.

## Applicability

`RuleVersion.applicability`, ileride mükellef türü, sektör, işlem türü, mal/hizmet
sınıfı ve teşvik gibi koşulları ifade edecek yapılandırılmış JSON alanıdır.
Foundation aşamasında alan saklanır ve Decimal-safe doğrulanır; kapsam eşleştirme
algoritması gerçek mevzuat paketleriyle birlikte ayrı PR'da genişletilecektir.

## Çakışma güvenliği

Normal kayıt yolu çakışan effective-range oluşturmayı reddeder. Buna rağmen
veritabanına başka bir yoldan çakışan kayıt girerse resolver birden çok candidate
gördüğünde fail-closed olur. Veritabanı seviyesinde exclusion constraint daha
sonraki concurrency hardening aşamasında değerlendirilecektir.

## Sonuç

- Güncel mevzuat güncellemesi geçmiş hesapları değiştirmez.
- Her hesap sonucu hangi resmi kaynaktan geldiğini gösterebilir.
- Tarih sınırları deterministik test edilebilir.
- Yanlış/çakışan mevzuat verisi sessizce hesap sonucuna dönüşmez.
