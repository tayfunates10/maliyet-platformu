# TR 2026 Core Baseline

`baseline.json` production rules-engine için ilk doğrulanmış çekirdek veri paketidir. Oranlar uygulama kodunda değildir.

`source_captures/` dosyaları resmi GİB/SGK kaynaklarında doğrulanan, yalnız bu baseline'ın kullandığı gerçeklerin normalize edilmiş evidence capture'larıdır. Dosyalar remote web/PDF'nin birebir kopyası değildir ve hash'leri de remote byte hash'i olarak yorumlanamaz.

Bir değeri değiştirmek için mevcut revision üzerine yazmayın. Resmi kaynağı yeniden doğrulayın, yeni evidence capture/source revision üretin ve effective-date regression testlerini ekleyin.
