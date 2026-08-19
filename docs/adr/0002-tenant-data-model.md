# ADR 0002 — Tenant Veri Modeli ve Veritabanı İzolasyonu

- Durum: Kabul edildi
- Tarih: 2026-08-19

## Bağlam

Maliyet Platformu aynı veritabanında birden fazla işletmenin maliyet, vergi,
sermaye ve hesaplama verisini tutacaktır. Bir tenant kimliğinin uygulama
katmanında yanlış filtrelenmesi başka bir işletmenin ticari sırlarını açığa
çıkarabilir. Bu nedenle tenant izolasyonu yalnız route veya repository
filtrelerine bırakılamaz.

## Karar

1. Tenant sınırı `organizations.id` ile temsil edilir.
2. Tenant-owned hesaplamalar `organization_id` taşır.
3. Kullanıcının tenant içinde işlem yapabilmesi
   `organization_memberships(organization_id, user_id)` ilişkisiyle kanıtlanır.
4. `calculations` oluşturucusu veritabanında composite foreign key ile aynı
   tenant üyeliğine bağlanır.
5. `calculation_versions` hem hesaplama kimliği hem `organization_id` üzerinden
   composite foreign key kullanır. Başka tenant'a ait hesaplama kimliğiyle
   version oluşturulamaz.
6. Uygulama sorguları tenant-owned kaynağı yalnız kimlikle değil
   `(organization_id, resource_id)` çiftiyle çözer.
7. Başka tenant'a ait kaynak ile var olmayan kaynak aynı `not found` sonucu
   üretir; resource-id ownership oracle oluşturulmaz.
8. Hesaplama version'ları input, ruleset, engine ve output snapshot'larını
   immutable kayıt olarak taşır.
9. Migration'lar Alembic ile açık ve geri alınabilir tutulur.
10. CI gerçek PostgreSQL üzerinde migration round-trip, metadata drift ve
    cross-tenant constraint testleri çalıştırır.

## İlk tablolar

- `users`
- `organizations`
- `organization_memberships`
- `business_profiles`
- `tax_profiles`
- `calculations`
- `calculation_versions`
- `audit_events`

## Bilinçli kapsam dışı

- Authentication sağlayıcısı
- Session/token yönetimi
- PostgreSQL Row Level Security policy'leri
- Kişisel/vergi kimlik numaralarının saklanması
- Rules engine
- Finans formülleri

RLS daha sonraki güvenlik aşamasında defense-in-depth olarak değerlendirilecek;
bu ADR'deki composite ownership constraint'lerinin yerine geçmeyecektir.

## Sonuçlar

- Tenant-owned relation hataları veritabanı tarafından da reddedilir.
- Hesaplama version zinciri geçmiş sonuçların yeniden üretilebilirliğine temel
  sağlar.
- Migration drift'i CI'de yakalanır.
- Tenant sorguları için organization scope zorunlu hale gelir.
