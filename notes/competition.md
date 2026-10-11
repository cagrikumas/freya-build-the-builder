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
- Kullanıcının 19.33'te paylaştığı Freya/Tuna Bayrak mesajı, teslim adresinin
  veya formunun final senaryosuyla birlikte paylaşılacağını belirtiyor. Kanal
  20.00 duyurusuyla doğrulanacak; dev@ adresi teslim adresi olarak varsayılmadı.
- Önceki iki hidden-brief biçimi ve 30 dakikalık sınır güncel sayfada yok.
  Builder’ın güncel yerel süre sınırı tüm koşular için 60 dakika; gerekirse --max-seconds ile değişir.
- Final belgelerinden hiçbir kural/değer/isim builder koduna veya promptlarına
  elle yazılamaz; ajan elle düzenlenemez. Genel hata düzeltmesi yapılabilir.
- Değerlendirme: gizli müşteriler ve workflow incelemesi; ağırlıklar açıklanmıyor.
  Trace puanlanmıyor, üretimin dürüstlüğünü doğrulamak için okunuyor.
- Kişisel Cloudflare hesabı bilgisi kullanıcıya soruldu; henüz giriş/deploy yok.
- Son tamamlanan B testi sürüm 4 ile 1/3: PUB11'de üç taahhüt doğru kaydedildi;
  PUB12/13 kimlik aşamasında kaldı. Şema çakışmaları düzeldi, ancak hesaplanan
  soru ile gerçek konuşma hâlâ ayrışıyor. Genel giriş talimatı düzeltildi.
  Önceki sürümdeki 2/3 küçük örneklem, güncel veya kararlı başarı oranı değildir.

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

## 18.24 İstanbul durum kaydı

- A yeni otomatik koşusu tamamlandı: 1165.29 saniye, 68 üretilmiş yerel kontrol,
  Freya dry-run başarılı, practice-a sürüm 2 dışa aktarıldı.
- Ardından 10 konuşmanın tamamı ilk asistan mesajı oluşmadan kapandı: 0/10,
  hiçbir banka aracı çağrılmadı, judge sonuçları yok. Bu davranışı politika
  başarısızlığı diye tek başına yorumlamıyoruz. A doğrudan chat de 504 verdi.
- Kontrol olarak daha önce 2/3 geçen B sürümüne tek chat gönderildi; o da 504.
  Hesap kredisi yeterli. Yeni simülasyon açılmıyor; kontrol API’leri yanıt veriyor.
- Ayrı B derlemesi 720 saniyelik model çağrısı sınırında kesildi. Güncel sayfada
  eski 30 dakika sınırı kalktığı için yerel toplam 3600 saniye; ilk model çağrısı
  1500, denetim 1200 saniyeye kadar, tümü gerçek toplam süreye dahil.
  18.23’te yeni B derlemesi başladı; kendi başına konuşma simülasyonu açmayacak.
- 38 yerel test geçti. Açılış chat API’sinde atlanabildiği için gerekli girişin
  ilk node task_message içinde de geçmişe bağlı olarak sağlanması isteniyor.
- Cloudflare için Node 22 ve Wrangler proje içine kuruldu; deploy --dry-run
  geçti. Hesap kimlik bilgileri ayrı private/cloudflare dizininde tutulacak.
  Kişisel hesap bilgisi bekleniyor; login, hesap seçimi veya deploy yapılmadı.

## 18.32 İstanbul — final örneklerini otomatik sınama

- Builder, belge klasöründeki örnek konuşmalardan müşteri senaryoları ve bağımsız
  başarı ölçütleri üretebiliyor. Freya simülasyonu, görüşme kayıtları, otomatik
  düzeltme ve aynı senaryolarla tekrar kontrol tek builder koşusuna dahil.
- Düzeltme mevcut senaryo/başarı ölçütlerini veya yerel kontrolleri gevşetemez.
  Eksik konuşma ya da değerlendirme sonucu belirsiz sayılır; politika hatası
  diye otomatik düzeltilmez. Belirsiz/kötüleşen tekrar eski workflow'a döner.
- 47 yerel test başarılı. Bu sayı canlı müşteri başarı oranı değildir; yeni
  final testi hattı henüz gerçek Freya konuşmasıyla çalıştırılmadı.
- Kullanıcı birincilik hedefini açıkça vurguladı. Düşük panel oranları soruldu;
  gerçek ajan hataları ile başlamayan görüşmelerin ayrımı açıklandı. Yeni B
  derlemesi sürüyor, canlı sonuç henüz yok. Cloudflare hesabı yanıtı bekleniyor.

## 18.46 İstanbul — B sürüm 3 ve belge denemesi tamamlandı

- Yeni B koşusu `20261011T152310Z-practice-b` 1039.53 saniyede tamamlandı.
  İlk üretim 624.87, bağımsız denetim 411.2 saniye sürdü. Denetim 12 sorun
  bulup otomatik düzeltti; 58 kod kontrolü ve Freya dry-run geçti.
  11 node / 8 araç; practice-b sürüm 3 etkinleştirildi ve dışa aktarıldı.
- Denetlenmiş B artifact'ına PUB-12 girdilerini yerelde sıralı uygulayan kod
  tekrarında DOB bir kez, telefon iki kez doğrulandı. Sonra yalnız p1 için
  510 / 2026-10-15 taahhüdü, p2/p3 refused notları ve tek kapanış oluştu.
  `results/20261011-local-replay-pub12.json` bu kontrollü kod tekrarını içerir;
  LLM konuşmasını veya gerçek bank API'sini çalıştırmaz, canlı puan değildir.
- Değiştirilmemiş temel ajan da 18.35'te 504 verdi. Model ayarı doğrulandı:
  experimental-5. Olay kanıtı `notes/platform-incident-20261011.md`.
- Yeni B v3 tek açılış kontrolü de 18.46'da 504: sonuç belirsiz, yeni üç
  müşterilik simülasyon başlatılmadı. Panelde v3'e ait yeni canlı başarı yok.
- Word tablosu, Excel (baştaki sıfırlar), görsel PDF ve sonradan gelen değişiklik
  içeren sentetik klasör gerçek modelle derlendi. `20261011T153340Z-reader-check`
  607.28 saniyede ve 35 kod kontrolüyle tamamlandı. Görsel akış ve 16.00'a
  değişen pencere doğru okundu. Bu offline deney Freya ajanı oluşturmadı.
  Girdiler `tests/fixtures/reader-case` altında korundu.
- Yerel suite 49 test geçti. Genel iyileştirmeler: 502/503/504 konuşma testi
  hatası belirsiz kaydedilir ve doğrulanmış workflow yine dışa aktarılır;
  kimlik doğrulama/şema hataları saklanmaz. Klasör modu modele açıkça belirtilir.
- Cloudflare kişisel hesap yanıtı bekleniyor. Hesap girişi veya deploy yapılmadı.
  Final belgeleri 20.00 İstanbul'da açılacak; final ajanı ve teslim henüz yok.


## 19.00 İstanbul — çoklu ajan denetimi ve genel düzeltmeler

- Kullanıcının izniyle üç yan ajan GPT-6.1/high ile çalıştı. B v3 için doğal
  ürün adları, belirsiz yanıt sayaçları ve tarih dili gibi somut yerel karşı
  örnekler bulundu. Önceki PUB-12 tekrarındaki p1 girdisinin extraction
  aşamasını atladığı açıkça kaydedildi; kanıtlar results altında hash ile saklandı.
  Üretilmiş B ajanı elle değiştirilmedi; genel derleyici/audit talimatı güçlendi.
- Bütün post-audit onarımlar eski testleri korur; güvenlik doğrulaması reddedilen
  kod yerelde çalıştırılmaz. Smoke ve örnek tekrarları başarısız/belirsizse
  önceki sürüm geri yüklenir. Simülasyonun ayrı süre sınırı export için pay bırakır.
- Global node/lifecycle/terminal eylemleri doğrulanır. OpenAPI primitive
  path/query/header girdileri schema'dan türetilir, URI değerleri kodlanır;
  eksik/geçersiz parametre istek URL'sini boşaltır. Karmaşık zorunlu parametre
  biçimleri açık hata verir. Bu yeni adapter henüz canlı Freya URI çağrısı
  ile sınanmadı; public kit POST-body araçlarının davranışı korunuyor.
- Excel yüzde ve format bilgileri, Word SmartArt metni/bağlantıları korunur.
  Desteklenmeyen yerel Word grafikleri sessizce kaybolmaz, açık hata verir.
- Build sonunda tam trace artifact manifesti oluşturulur. Paketleyici kaynak,
  export ve tüm trace dosyalarını HEAD baytlarıyla karşılaştırır. Eski manifest
  içermeyen koşular final için kullanılamaz. Girdi hash'leri de doğrulanır.
- Cloudflare sarmalayıcısı config/env/account override'larını sınırlar. Yerel
  --version ve deploy --dry-run başarılı; hesap girişi veya gerçek deploy yok.
- Birleşik suite: 94 test geçti, diff kontrolü ve değişen dosyalarda gerçek
  anahtar taraması temiz. Bunlar canlı müşteri başarısı veya yarışma puanı değil.
- Kişisel Cloudflare hesabı yanıtı hâlâ bekleniyor. Final dosyaları henüz açılmadı.


## 19.16 İstanbul — B v3 gerçek görüşmelerde 0/3

- Freya konuşma servisi tekrar yanıt verdi. Mevcut Bv3 üç resmi müşteriyle
  32 saniyede 0/3: bu kez asistan konuştu ve her çağrıda close_call yapıldı.
  En yavaş tur medyanı2s; bu sonuç kesinti diye sınıflandırılmıyor.
- PUB11/12'de kimlik için belgelerde olmayan SSN soruları; PUB13'te doğum
  tarihi ardından anne kızlık soyadı soruldu. Üçü de erken unclear kapandı.
- İsim onayında extraction event=confirm üretmiş; identity enum'unda name_yes
  var, collection aynı event adını farklı enum ile yeniden kullanıyor.
  Code_exec ayrıca event/answer_replaces/amount_scope alanlarını enum dışı
  boş metne temizlemeyi reddetti; eski değerler değişken tablosunda kaldı.
  Gerçek konuşma ve kısa olay kanıtı results/20261011-b-v3-live-diagnostics.json.
- 19.12'de başlayan yeni B derlemesi sürerken bu yeni kanıt geldi. Genel
  audit talimatına stage-specific extraction adları, geçerli enum temizliği
  ve konuşma node'larında kaynak kimlik alanlarının açık yazılması eklendi.
  Bu public koşunun başlangıçtan sonra kaynakları değiştiği için final trace'i
  olarak kullanılamaz; final zaten ayrı, taze ve dondurulmuş koşu gerektirir.


## 19.25 İstanbul — konuşma arızasını ayıran başlangıç kontrolü

- Değiştirilmemiş başlangıç ajanı tek PUB01 müşterisinde iki doğru güvenlik
  sorusu, iki verify, hesap sorgusu, taahhüt ve kapanışı tamamladı. Resmi sonuç
  0/1: konuşmada taahhüt sonrası SMS bildirim cümlesi eksik. Dolayısıyla tam
  politika başarısı değil, temel telefon/araç akışının çalıştığına dair kontrol.
- Genel extraction şema/enum durum kontrolleri ve konuşma bağlamı talimatları
  tamamlandı; birleşik suite101test geçti. Bv3'ün gerçek enum sorunu yeni
  validator ile1yapısalhata ve58kontrolün41'inde geçersiz değer olarak yakalandı.
- Yeni B koşusunun ilk üretimi19.23'te bitti;9node/44yerelkontrol. İlk taslakta
  yine iki paylaşılan extraction adı çakışması var. Sürmekte olan otomatik
  bağımsız audit yeni genel dersleri içeriyor; henüz yeni canlı sürüm yok.


## 19.35–19.38 İstanbul — yedi sekme ve B sürüm 4

- Resmi sayfa yeniden indirildi; Overview, Data, Evaluation, Submit, Leaderboard,
  Rules ve FAQ ayrı ayrı okundu. 19.28 kopyasıyla bölüm metinleri aynı. Final ZIP
  henüz yok; kit v3. Sayfadaki13case, kittekilerle identity alanının web görünümünde
  çıkarılması dışında aynı. Güncel tek Türkçe vaka/Cloudflare/20.00–23.00 biçimi
  korunuyor. Kullanıcının paylaştığı mesaj nedeniyle kesin teslim adresi/formu
  final duyurusundan doğrulanacak.
- B v4 otomatik koşu1215.99s; yeni validator ile65kodkontrolü geçti. Resmi canlı
  skor1/3,136s: PUB11üçtaahhüt kaydetti; PUB12/13kimlikte kaldı. Sonuç dosyası
  results/20261011-b-v4-live.json. Ayrıntılı gerçek konuşma/devlet kanıtı ayrı
  live-diagnostics.json içinde; rendered model promptu elde değil.
- Şema hataları görülmedi. Kod doğru kimlik sorusunu hazırlarken identity
  konuşması başka sorular soruyor veya hesap erişimini reddediyor. Üç açılış da
  gerekli banka/kayıt cümlesini atlıyor; PUB11'in dar case ölçütünü geçmesi tam
  brief uyumu demek değil. Özel on_enter.prompt yalnız değişken adını anıyor,
  değerini interpolate etmiyor; entry context kaybı güçlü çıkarım, kanıtlanmış
  platform kusuru değil. Genel talimat, özel girişleri gerçek değişken değeri ve
  kaynak açılış/fallback ile kendi başına yeterli hale getirecek şekilde güçlendi.
- Üç taslak scope/attempt hatası otomatik audit tarafından düzeltildi. Hedefli
  yerel tekrarlar bunları doğruladı; doğal weekday+ordinal tarih biçiminde ayrı
  parser açığı kaldı. Genel locale/context tarih rehberi eklendi. Bu yerel
  sonuçlar telefon modelinin extraction veya konuşmasını kanıtlamıyor.
- Otomatik örnek onarımına gönderilen model girdisi sınırlı bir projeksiyon;
  tam system/kod/variable-table tekrarları sonuç dosyasında korunur. Projeksiyon
  konuşma, araç sonucu, validation hataları ve promptta referans verilen
  hesaplanmış değerleri sınırlı biçimde taşır; tüm kesilmeler işaretlenir.
