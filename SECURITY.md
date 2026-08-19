# Security Policy

Maliyet Platformu finansal ve ticari açıdan hassas veri işleyeceği için güvenlik hataları normal ürün hatalarından ayrı ele alınır.

## İlkeler

- Secret veya kişisel veri repository'ye commit edilmez.
- Tenant izolasyonu ihlalleri kritik güvenlik açığı kabul edilir.
- Yetkisiz şekilde gerçek maliyet, çalışan, sermaye veya hesaplama geçmişi açığa çıkarılamaz.
- Finansal sonuçların yetkisiz/manipüle edilebilir olması güvenlik olayıdır.
- Audit log kayıtları sessizce değiştirilemez veya silinemez.

## Raporlama

Repository public issue alanına gerçek müşteri verisi, token, parola veya güvenlik açığının sömürü ayrıntılarını koymayın. Güvenli özel bildirim kanalı production öncesi güvenlik PR'ında tanımlanacaktır.
