# Güncel final kuralları — 11 Ekim 2026, 18.00 İstanbul kontrolü

Resmi sayfa bugün değiştirildi: https://www.freyavoice.ai/hackathon

- Tek Türkçe final vakası; 20.00 İstanbul’da Submit sekmesinde ve e-postada ZIP.
- Girdi bir klasör: Markdown, Word, PDF, Excel; analiz, akış çizimi, duyurular,
  servis sözleşmesi, test müşterileri, soru-cevap ve altı örnek görüşme.
- Banka servisleri Cloudflare Workers üzerinde katılımcının kendi mock’u olmalı.
  Servis sözleşmesi ve test müşterileri esas alınacak, sonuçlar açıklanana kadar
  çalışır tutulacak. Final ajanı yalnız bu mock’u çağırabilir.
- Teslim 23.00 İstanbul: tek workflow JSON, onu üreten tek trace, repo/commit,
  üyelerin ad/e-postası ve mock_url. Komut: case_folder + mock_url.
- Önceki iki hidden-brief biçimi ve 30 dakikalık sınır güncel sayfada yok.
  Builder’ın yerel süre sınırı klasör için 60 dakika; pratik için 29 dakika.
- Final belgelerinden hiçbir kural/değer/isim builder koduna veya promptlarına
  elle yazılamaz; ajan elle düzenlenemez. Genel hata düzeltmesi yapılabilir.
- Değerlendirme: gizli müşteriler ve workflow incelemesi; ağırlıklar açıklanmıyor.
  Trace puanlanmıyor, üretimin dürüstlüğünü doğrulamak için okunuyor.
- Kişisel Cloudflare hesabı bilgisi kullanıcıya soruldu; henüz giriş/deploy yok.
- Güncel B testi 2/3: PUB-11 ve PUB-13 geçti; PUB-12’de güvenlik adımı ile
  ortak işlem adımı arasındaki gecikmiş geçiş yeni yanıtı işleyemedi. Bu gözlem
  genel derleyici/audit talimatına eklendi.

---
Aşağıdaki kayıtlar sayfa değişikliğinden önceki tarihsel çalışma notlarıdır.

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

## 17.46 sonrası devam

- Freya duraklatma isteğini daha önce kabul etmişti; yeniden bağlanıldığında
  simülasyonu completed olarak bildirdi. Eksik yargı sonuçlarıyla kurtarılan
  değerlendirme 1/10. Kesinti dönemindeki bu koşu güvenilir nihai ölçüm değil.
- Gerçek görüşmede hesap yanıtı `lookup_response.data.products.0.*` altında
  görüldü, buna karşılık ürün listesi eşlenen değişkende oluşmamıştı.
  Builder artık ilan edilmiş response_mapping değerlerini post-hook içinde
  vars'a da geçiriyor. Banka kuralları veya üretilmiş ajan metinleri elle
  değiştirilmedi. Aynı gerçek yanıtla yerel tekrar ödeme yoluna geçti.
- Platformun string istediği test_variables alanları assembler tarafından
  JSON metnine çevriliyor. 30 birim testi, A için 43 ve B için 59 üretilmiş
  yerel kontrol geçti.
- B için yeni üç müşterilik simülasyon; A için sıfırdan yeni builder koşusu
  başlatıldı. Final teslimi yapılmadı.
