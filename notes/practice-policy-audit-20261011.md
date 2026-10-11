# Practice B v3 — yerel politika ve extraction sözleşmesi denetimi

İncelenen otomatik artifact:
`traces/20261011T152310Z-practice-b/candidate-0.json` ve aynı koşunun
`workflow.json` dosyası. Kaynaklar başlangıç kitinin `brief-a.md`, `brief-b.md`,
`public-test-set.json` ve platform belgeleri. Candidate içindeki evaluator kodu
ile assemble edilmiş workflow içindeki kod aynı; JSON yerleşimleri farklı.

Uzak servis çağrılmadı, sırlar incelenmedi, üretilmiş ajan/artifact değiştirilmedi.
Aşağıdaki karşı örnekler gerçek kodu, belirtilmiş extraction değerleriyle yerelde
çalıştırır. Gerçek telefon modelinin mutlaka bu değerleri çıkaracağını veya canlı
görüşmenin başarısız olduğunu kanıtlamaz. Ancak extraction açıklamalarının izin
verdiği çıktılarla evaluator arasındaki uyuşmazlığı ve kodun davranışını gösterir.

## Önceki PUB-12 tekrarının sınırı

`results/20261011-local-replay-pub12.json` DOB bir kez, telefon iki kez,
bir taahhüt, iki not ve bir kapanış yolunu doğruluyor. Telefonun yanlış yanıtından
sonra tekrar yalnız telefon sorulması kod/hook düzeyinde korunmuş. Bu tekrar
ödeme ürününü `product_scope=p1` olarak doğrudan verdi. Müşterinin konuştuğu ürün
adının extraction tarafından nasıl çıkarılıp çözüleceğini, konuşma node girişini,
LLM yönlendirmesini ve gerekli sesli ifadeleri sınamadı. Bu nedenle doğal ürün
adının tüketilemediği bir hata bu başarılı tekrarda görünmeyebilir.

## Somut karşı örnekler

1. **Konuşulan kısa ürün adı çözülemiyor.** PUB-12 müşterisi kredi kartını
   yarın ödeyeceğini söylüyor. Extraction açıklaması konuşmada belirtilen ürün
   adını ister; `product_scope=credit card`, `date_text=tomorrow` geçerli bir
   doğal çıktı. `resolve_scope` yalnız ürün ID'sine veya tam etikete eşitliği
   kabul ediyor. Tam etiket `credit card ending 9015` olduğu için müşteri tekrar
   `credit card` dese de “Does that apply to all the products or to one product?”
   sorusu yineleniyor; tüm ürünler açık kalıyor. Kaynak: B4/B7/B8 ve PUB-12
   script. Candidate yolları: `/workflow/nodes/collection/extraction_schema/3/description`
   ve `/workflow/nodes/evaluate/code`, `resolve_scope`.
   Kanıt: `results/20261011-b-policy-audit-pub12-spoken-scope.json`.

2. **Belirsiz ödeme yanıtı deneme bütçesine girmiyor.** Collection extraction
   açıklaması “Empty/unclear is none” diyor. Evaluator'ın ret/deneme dalı yalnız
   `refuse`, `nonanswer`, `stop` içeriyor. `phase=all` sırasında iki `event=none`
   yanıtı tam borç duyurusunu ve bugün sorusunu tekrar ediyor; denemeler sıfırda
   kalıyor. Kaynak: A30/A31 ve B4. Candidate yolları:
   `/workflow/nodes/collection/extraction_schema/0/description`,
   `/workflow/nodes/evaluate/code`, sondaki ret dalı.
   Kanıt: `results/20261011-b-policy-audit-probes.json`, `unclear_nonanswer_*`.

3. **İlk toplu sorudan sonra tutar yetersizliği yanlış başlangıç teklifine
   gidiyor.** İlk tüm ürünleri bugün ödeme sorusuna `event=too_much`,
   `product_scope=all` verildiğinde her ürünün taban tutarı bugün tarihine
   konuyor; denemeler sıfır. B4 her ürünün A30 deneme 1'den başlamasını ister.
   Kaynak çağrı tarihi 14 Ekim iken bu teklifin günü 16 Ekim olmalı; mevcut
   kod 14 Ekim sunuyor. A26 taban tutarını açıklıyor, B4'ün başlangıç gününü
   değiştirmiyor. Candidate yolu: `/workflow/nodes/evaluate/code`, proposal
   tarihinin varsayılanı ve `too_much` dalı.
   Kanıt: `results/20261011-b-policy-audit-probes.json`, `full_amount_too_much_for_all`.

4. **Doğal belirsiz tarih dili açıklama sınırını aşabiliyor.** PUB-07'deki
   “the week after next” ifadesi `vague` yerine `missing` sayılıyor; bu nedenle
   bir kez açıklama isteme sayacı ilerlemiyor. Ardından “Monday the 26th” de
   `missing` kalıyor. Açık testin beklediği tatil sonrası 27 Ekim teklifine
   ulaşılmıyor. Sonraki “when my salary comes” başka bir exact-day sorusu
   çıkarıyor. Kaynak: A20/A21 ve PUB-07. B, bu A kurallarını devralıyor.
   Candidate yolu: `/workflow/nodes/evaluate/code`, `parse_day` içindeki kısa
   ifade listesi ve proposal quality dalları.
   Kanıt: `results/20261011-b-policy-audit-pub07.json`.

5. **Müşterinin ilk mesajıyla başlayan görüşme sorulmamış bir ad sorusunu
   sayabiliyor.** Identity prompt yalnız önceki ad sorusu olmadan gelen selamı
   özel işler; diğer anlamlı ilk mesajı evaluator'a verir. `name_asks` başta
   1 olarak varsayılıyor. İlk “Who is this?” sonrası yalnız bir gerçek ad
   sorusu söylenir; sonraki belirsiz yanıt `not_reached/unclear` kapatır.
   A3 iki gerçek ad sorusu gerektirir. Candidate yolları:
   `/workflow/nodes/identity/task_message`, `/workflow/nodes/evaluate/code`.
   Kanıt: `results/20261011-b-policy-audit-probes.json`, `first_caller_message_*`
   ve `unclear_after_only_one_actual_name_ask`.

6. **Yardım teklifine yanıt vermemek insan isteğinde ısrar sayılıyor.** Kimlik
   doğrulama öncesi insan isteği yardım teklifini çıkarıyor. Ardından
   `phase=identity_human`, `event=nonanswer` doğrudan `general` aktarımı
   seçiyor. A42 aktarımı müşterinin ısrarına bağlar; yanıt vermemek tek başına
   bu koşulu karşılamaz. Candidate yolu: `/workflow/nodes/evaluate/code`,
   identity human dalı. Kanıt: `results/20261011-b-policy-audit-probes-extra.json`.

Assemble edilmiş evaluator JSON yolu tüm kod bulguları için
`/nodes/evaluate/pre_actions/0/function/parameters/properties/code/default`.

## Daha düşük kesinlikli teklif döngüsü

Taban altı yeni tutarlar aynı gün için art arda verildiğinde aynı taban/gün
teklifi tekrar sorulabiliyor ve denemeler sıfır kalıyor. A27 tabanı bir kez
teklif etmeyi, A29 ise önerilen tutarı ret saymamayı gerektirir. Bu kurallar
birlikte değerlendirilmelidir; her yeni öneriyi otomatik ret saymak da yanlış
olur. Mevcut audit'in `a29_revised_below_floor_proposal_consumes_no_persuasion_attempt`
kontrolü farklı gün için yeniden taban sorusunu geçerli kabul etmiş. Yeni
geçerli öneri, aynı taban sorusunun tekrarı ve açıkça reddedilmiş aynı teklif
ayrı sınanmalı. Kanıt: `results/20261011-b-policy-audit-probes.json`,
`first_below_floor`, `second_below_floor_same_day`, `third_below_floor_same_day`.

## Genel derleyici ve denetçi değişikliği

`builder/compile_prompt.md` ve `builder/audit_prompt.md` güncellendi. Eklenen
talimatlar hiçbir practice banka adı, tutarı, tarihi, kodu veya politika kuralını
final için varsayılan yapmıyor. Genel dersler:

- Extraction şemasının izin verdiği bütün enum/temsil biçimleri evaluator'da
  tüketilmeli; doğal ve tek anlamlı ürün adları runtime ürünlerle çözülebilmeli.
- Belirsiz/boş/yanıtsız sınıfları kaynak politikanın açıklama, deneme ve bitirme
  sınırlarını atlamamalı; sayaçlar gerçekten söylenmiş soruları saymalı.
- Yeni müşteri yanıtı ile araç sonucu sonrası yeniden giriş ayrılmalı; gecikmiş
  yönlendirme yeni cevabı kaybetmemeli.
- İlk soru ile istisna kuralları birlikte incelenmeli. Yeni öneri ile reddedilmiş
  teklif ayrılmalı; kaynak kuralının tekrar sınırı korunmalı.
- Tarih açıklama sayacı ifade listesinden bağımsız olmalı; farklı söyleyişler
  sınırı sıfırlamamalı; yalnız kaynak ve çağrı girdilerinin desteklediği tarih
  çözülmeli.
- Kaynaktan bağımsız beklenen değerlerle adversarial kontroller türetilmeli.
  Tam node/sonuç/konuşma/sonraki yanıt yolu gerçekçi extraction değerleriyle
  izlenmeli; extractor'ın göremediği ID'ler başarı kanıtı olarak kullanılmamalı.

Yeni kimlik öncesi borç açıklaması, onaysız taahhüt yazımı, başarılı taahhüdün
ikinci yazımı veya başarılı aktarım sonrası not üretimi hatası bulunmadı. Bu,
canlı konuşma başarısı garantisi değildir. Prompt ve not değişiklikleri için
`git diff --check` uygulandı; banka servislerine veya telefon modeline yeni test
isteği gönderilmedi.

## Yeni taslak: kaynak üzerinden üç kalan bulgu

İncelenen yeni otomatik taslak:
`traces/20261011T161213Z-practice-b/model-01.answer.json`.
Bu bölüm yalnız kaynak kodu ve prompt okumasına dayanır. Taslak validator'dan
henüz geçmediği için hiçbir workflow kodu çalıştırılmadı; bu bulgular yerel
çalıştırma veya canlı telefon testi sonucu değildir. Otomatik model-02 denetimi
bu inceleme sırasında sürüyordu; aşağıdakiler model-01 bulgularıdır ve sonraki
patch için yeniden kontrol edilmelidir. Üretilen artifact değiştirilmedi.

Üç bulgunun JSON yolu `/workflow/nodes/evaluate/code`.
Kural kaynakları:
`build-the-builder-v3/build-the-builder/briefs/brief-a.md` ve
`build-the-builder-v3/build-the-builder/briefs/brief-b.md`.

1. **Onay sırasında düzeltme eski müzakere ürününe uygulanabiliyor.**
   `readback()` yalnız `phase=confirm` yapıyor; önceki `mode/index` korunuyor.
   `selection()` ürün adı verilmediğinde `mode=product` için eski index'i
   döndürüyor. İlk ürünün taahhüdü beklerken sonraki ürünler reddedilmişse,
   toplu okuma yalnız bekleyen taahhüdü içerir ama adsız bir tarih düzeltmesi
   son reddedilmiş ürüne yönelir. Proposal döngüsü o ürünün `done` durumunu
   atlar ve eski taahhüdü değişmeden tekrar okur. Kaynak: A35; toplu okuma
   bağlamı için B7. Kod noktaları: `selection`, `readback`, proposal döngüsündeki
   `status == 'done'` kontrolü. Onay kapsamı gerçekten okunan taahhütlerden
   türetilmeli; birden fazla olası hedef varsa kaynak kurallarına göre sorulmalı.

2. **Ortak tarih önerisinin kapsamı açıklama sorusunda kayboluyor.**
   Müşterinin tüm ürünler için belirsiz bir dönem önermesi ilk seçilen üründe
   `date_clarifications` dalına girer. Dal `index` ve `mode=product` atayıp
   döngüden çıkar; ilk önerinin ürün kümesini veya ortak tarih bağlamını
   saklamaz. Sonraki kesin gün yanıtı yalnız ilk ürüne uygulanır; `progress()`
   sonraki üründe yeniden müzakere başlatır. Kaynak: A21 ve B6. Kod noktaları:
   proposal döngüsündeki `common`, `day is None` açıklama dalı ve `progress`.
   Açıklama yanıtı eksik parçayı tamamlamalı, önerinin diğer ürünlerini veya
   şartlarını düşürmemeli.

3. **İlk toplu soruya tutar yetersizliği yanıtı hâlâ yanlış teklife gidiyor.**
   Sayısal tutar veya tarih içermeyen `kind == 'too_much'` dalı yalnız ilk
   seçilen ürünü alır; `offered_date` yoksa bugünü seçer ve `offer_adjustment`
   ile tabanı sorar. Deneme sayacı ilerlemez. B4, ilk toplu bugün sorusunun
   olumsuz yanıtından sonra her ürüne A30 deneme 1 ile başlamayı gerektirir.
   Kaynak: B4 ve A30; taban seçimi için A26. Genel ilk-soru/istisna talimatı
   bu dersi zaten kapsadığı için promptlara aynı talimat yeniden eklenmedi.

Bu taslakta doğal kısa ürün adları için alias çözümü ve `nonanswer` yanıtının
deneme yoluna girmesi önceki artifact'a göre iyileşmiş görünüyor; bu tespit de
yalnız kaynak okumasıdır. Yeni genel prompt ekleri yalnız onayda gerçekten
okunan kapsamı kullanmayı ve açıklama boyunca öneri bağlamını korumayı ister;
practice banka adı, değeri veya kuralını gelecekteki vakalara taşımıyor.
