# Freya × Y Combinator — çalışma kaydı

Kaynak: https://www.freyavoice.ai/hackathon — 11 Ekim 2026, başlangıç kiti v3.

## Yedi sekme

- Overview: Banka şartnamesini okuyup Freya telefon ajanı üreten program geliştiriliyor. Teslim edilen ajan tamamen bu programdan çıkmalı.
- Data: Brief A (47 kural), Brief B (çoklu ürün değişiklikleri), yedi araçlı OpenAPI, 13 sentetik müşteri, API ve workflow belgeleri. Yerel kit README ve belgeler okundu.
- Evaluation: İki gizli şartname × 30 müşteri. Her müşteri üç kez; üçü de geçerse puan. Banka kayıtları, konuşma politikası ve dürüstlük birlikte aranır. Eşitlik: geçen müşterilerde taahhüt toplamı, derleme süresi, teslim zamanı.
- Submit: GitHub depo URL’si, commit, tek komut, iki dışa aktarılmış workflow JSON, iki builder izi. Organizatörün formu e-posta adresine gönderiliyor. İlk on çözüm yeniden çalıştırılıyor.
- Leaderboard: Henüz sonuç yok.
- Rules: En fazla iki kişilik takım. Ajan elle düzenlenemez. Telefon ajanı yalnızca verilen bank API’sini çağırır. Freya modeli değiştirilemez. Platforma sondalama/yük testi yok. Takım başına tek key; aynı anda tek simülasyon. Bir build en fazla 30 dakika.
- FAQ: Gizli brief başına bir Markdown ve bir OpenAPI dosyası, hazır test yok. Mock banka yalnız PUB-01…PUB-13 destekler. Gizli kurallar kod/prompt içine elle eklenemez. Hata düzeltmesi serbest. Stil testleri ve üç tekrar gerekli.

## Zaman (11 Ekim 2026, İstanbul)

- 20.00: Gizli şartnameler açılır (17.00 UTC).
- 23.00: Teslim kapanır (20.00 UTC).

## Teslim koşulları

Kod girdilerden politika çıkarmalı; banka adı, kimlik alanları, takvim, eşikler, sonuç kodları ve araç şeması giriş dosyalarından alınmalı. Gizli brief açılmadan önce genel mimari ve promptlar tamamlanmalı. Sonrasında yalnız genel hata düzeltmeleri yapılabilir.

İz: Başlama/bitiş saati, her model çağrısının modeli ve amacı, workflow/agent kimlikleri ve node/tool sayıları, build içindeki testler ve sonuçları. Anahtarlar commit edilmez.

## Başlangıç durumu

- Hazır v3 kit çalışma alanında mevcut; değiştirilmeden referans olarak tutuluyor.
- Freya workspace bağlantısı doğrulandı; tek API anahtarı oluşturuldu.
- Builder mevcut Codex CLI ile çalışıyor. İlk Brief A ajanı 43 yerel kontrolden
  geçti; 10 müşterilik resmi simülasyon başladı. Henüz tamamlanmış puan yok.
- Kişisel depo: https://github.com/cagrikumas/freya-build-the-builder (hazırlık
  sırasında özel). Şirket organizasyonunda işlem yapılmadı. Depo erişim anahtarı
  yalnızca bu kişisel depoya bağlı.
- Freya bağlantısında urllib çağrıları 504 verirken aynı istekler curl ile
  başarıyla çalıştı. Adapter curl kullanıyor ve workspaceId ekliyor; kit ve
  telefon modeli değiştirilmedi.
- İlk Brief B derlemesinin tüm çıktıyı yeniden yazan denetimi süre sınırına
  takıldı. Denetim artık yalnız gereken JSON düzeltmelerini döndürüyor.
- 14.25 civarında kullanıcı, Freya ekibinin platform hatasını doğruladığını ve
  yaklaşık 10 dakika içinde düzeltmeyi beklediğini bildirdi. Yerel builder
  Freya isteklerini durdurmak için bekletildi; mevcut simülasyon tekrar açılmadı.
  Derleme süresi sıfırlanmadı; bakım süresi de gerçek toplam sürede kalıyor.
- Gizli şartnameler henüz yayımlanmadı; final teslimi yapılmadı.
