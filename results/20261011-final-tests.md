# Final vaka — canlı Freya sonuçları

Bu kayıtlar belge kaynaklı iç testlerdir; organizatörün gizli puanı değildir.

## İlk üretilen sürüm (v1)

11 görüşme: 2 başarılı, 9 başarısız.

[Freya görüşme grubu](https://staging-app.freyavoice.ai/simulations/b1bc357b-62b3-40b9-8e97-d566a7f7efa2/iterations/5025a1c1-1b13-4f7b-b9f3-7b8994d1b511?workspaceId=f22d7c29-2569-4a74-b8fc-b626c80454a5)

| Senaryo | Sonuç |
|---|---|
| Melis — asgari altında ödeme | fail |
| Kerem — üçüncü haftaya değişiklik | fail |
| Elif — tüm kartlarda iki kez ısrar | fail |
| Ece — eski dönemden son ekstreye düzeltme | fail |
| Zeynep — ilk on iki ve ilk altı hane talebi | fail |
| Cem — teklif öncesi adres servisi hatası | pass |
| Selin — mevcut hafta servisi hatası | fail |
| Bora — başarısız önizleme yazmayı engeller | fail |
| Duru — bulunamayan PDF gönderildi sayılmaz | fail |
| Tuna — on iki saniyelik başarılı bakiye | fail |
| Arda — henüz kesilmemiş ekstre | pass |

Gerçek kayıtlarla doğrulanan nedenler: tüketilmiş olayların kalıcı durumdan silinmemesi nedeniyle eski servis olayının boş verilerle tekrar çalışması; normal ekstre isteğinin toplam borç isteği diye çözümlenmesi; genel kart sözcüklerinin belirli kart seçimi sayılması. HTTP servis cevapları bu incelenen kayıtlarda doğruydu.

Önceki oturum ve bu canlı kanıtlar korunarak otomatik düzeltme çalışması 18:53 UTC’de başladı.

## Otomatik düzeltme (v2)

`traces/20261011T185315Z-final` çalışması 19:12:07 UTC’de tamamlandı. Önceki
üretim oturumları ve canlı görüşme kanıtları değiştirilmeden içeri alındı;
modelin ürettiği düzeltmeler uygulandı. Ajan elle düzenlenmedi.

60 yerel kontrol, platform doğrulaması ve açılış kontrolü geçti. Bunlar tam
görüşme başarısı değildir. Eski 41 kontrol ve 12 senaryo aynen korundu.
Tam üretim kaydı 10.599.629 bayttır. Kaynak ve çıktı hashleri, tüm oturum
kayıtları ve 39 iz dosyası doğrulandı; mevcut iki anahtar için taranan 362
dosyada eşleşme bulunmadı.

Yeniden çalıştırma kaydı:

```sh
python3 builder/build.py {case_folder} {mock_url} \
  --refine-run traces/20261011T183700Z-final \
  --repair-feedback traces/20261011T185315Z-final/refinement-evidence.json \
  --max-seconds 3000
```

Üretimin kendi süre kapısı 12 görüşme için gereken üst sınırı karşılamadığı
için bu testleri atladı. Aynı değişmemiş v2 üzerinde bağımsız gerçek Freya
testi 19:12:49 UTC’de başlatıldı.

V2 üzerindeki üç grup tamamlandı:

| Grup | Geçen | Toplam | Ham sonuç dosyası |
|---|---:|---:|---|
| Korunan temel senaryolar | 10 | 12 | `20261011-final-v2-baseline.json` |
| Farklı müşteri ve hata durumları | 10 | 12 | `20261011-final-v2-stress.json` |
| Onay, para birimi, kart değişimi ve kaynak açıklığı | 10 | 12 | `20261011-final-v2-remaining.json` |
| Toplam | 30 | 36 | Tüm sonuçlar ve görüşmeler aynen saklandı |

Ham altı başarısız sonucun dördünde gerçek neden doğrulandı: HTTP404 uyarısının
normal cevap işleyicisi dışında kalması, konu dışı deturdan geçerli kart
seçimine dönememe, doğru çıkarılan kart adının güven eşiğinde elenmesi ve
seçili kartı anan açık onayın yeni kart seçimi sayılarak silinmesi.

Diğer iki ham başarısızlığın kaynak ve gerçek konuşma incelemeleri
`20261011-final-v2-melis-judge-review.md` ve
`20261011-final-v2-kerem-judge-review.md` dosyalarındadır. Sonuçlar yeniden
etiketlenmedi. İletişim servisi sorgusunu açıkça adlandıran ek Melis testi ve
bankanın örneğindeki ayrı onay/işlem sonucu/üçüncü kişi sırasını koruyan ek
Kerem testi geçti. Eski senaryolar değiştirilmedi.

Son gruptaki iki görüşme bir süre hiç mesaj üretmeden `initiating` durumunda
kaldı; platform daha sonra yeni görüşme denemeleriyle grubu tamamladı. Grup
durdurulmadı ve tamamlanmamış görüşmeler başarılı sayılmadı.

## İkinci otomatik düzeltme (v3)

`traces/20261011T192924Z-final` çalışması 19:29:24 UTC’de başladı. Tamamlanan
v2 üretimi ve dört gerçek başarısız görüşmenin 298 özgün mesajı girdi olarak
kullanıldı. Kaynak kod değiştirilmedi; mevcut 60 yerel kontrol ve 12 temel
senaryo korundu. Üretim 19:37:02 UTC’de tamamlandı; 79 yerel kontrol,
platform doğrulaması ve açılış kontrolü geçti. Önceki 60 kontrol değişmeden
korundu, 19 yeni kontrol eklendi. Tam oturum kaydı 13.319.968 bayttır.

12 öncelikli gerçek Freya senaryosu 19:37:09 UTC’de başlatıldı. İlk sonuçlar,
konu dışı yanıttan kart seçimine dönüşün düzeldiğini, HTTP404 uygun kart yok
uyarısının ise hâlâ teknik hata sayıldığını gösterdi. Gerçek platform cevabı
tek tırnaklı Python sözlük metni; v3 normalleştiricisi yalnız JSON okuyordu.
Bu fark hem özgün mesajlarla yerel olarak hem sürüm3 canlı görüşmesinde
`335b4dec-e1a0-4d98-a446-34f5698edef6` doğrulandı.

## Üçüncü otomatik düzeltme (v4, sürüyor)

`traces/20261011T193910Z-final` çalışması 19:39:10 UTC’de başladı.
Değişmemiş v3 üretimini, 79 kontrolü, 12 temel senaryoyu ve tek gerçek
v3 HTTP404 başarısız görüşmesinin özgün mesajlarını kullanır. İstenen
onarım hata metninin güvenli biçim normalleştirmesiyle sınırlıdır; HTTP
kodları, uyarı kodu/türü, güncellik koşulları ve teknik hata ayrımı korunur.

Gerçek artımlı üretim komutu:

```sh
python3 builder/build.py {case_folder} {mock_url} \
  --refine-run traces/20261011T192924Z-final \
  --repair-feedback traces/20261011T193910Z-final/refinement-evidence.json \
  --max-seconds 1200
```

Teslim formundaki sıfırdan üretim komutu 5400 saniyelik bütçe kullanır;
yukarıdaki 1200 saniyelik süre yalnız önceki tamamlanmış üretimi içeri alan
artımlı düzeltmeye aittir. Tam oturum kaydı tüm önceki model çağrılarını ve
yeni düzeltme oturumunu birlikte saklar.
