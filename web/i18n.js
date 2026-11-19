// The page's text, in the ten languages the desktop app offers.
//
// `data-i18n` sets textContent; `data-i18n-html` sets innerHTML and is used only
// for the four sentences that carry a link or a code sample. Both read this
// dictionary, never user input.

export const LANGUAGES = ["en", "fr", "zh", "ar", "tr", "de", "it", "es", "pt", "nl"];
export const RTL = new Set(["ar"]);

// Each language's name in itself, so the picker stays recognisable whatever the
// page is showing.
export const NAMES = {
  en: "English",
  fr: "Français",
  zh: "中文",
  ar: "العربية",
  tr: "Türkçe",
  de: "Deutsch",
  it: "Italiano",
  es: "Español",
  pt: "Português",
  nl: "Nederlands",
};

export const UI = {
  en: {
    tagline:
      "Drop a DAISY 2.02 audiobook pack, get a Telmi story folder. Nothing is uploaded: the conversion runs in this tab.",
    drop_title: "Drop a DAISY pack here",
    drop_hint: "a .zip pack",
    pick_zip: "Choose a zip",
    pick_folder: "Choose a folder",
    convert: "Convert",
    download: "Download the story zip",
    language: "Language",
    cover_title: "Cover image",
    cover_hint: "Optional. Without one the cards show the chapter number on a plain background.",
    cover_pick: "Choose an image",
    cover_url: "or paste an image link",
    cover_use: "Use this link",
    cover_search: "Search Google Images",
    cover_clear: "Remove",
    what_title: "What you get",
    what_p1:
      "One Telmi chapter per top-level DAISY chapter, plus a menu card before each one so the story is navigable with the Telmi buttons. The pack's spoken title becomes title.mp3.",
    what_p2:
      'The zip is named the way Telmi Sync names stories, <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>, and imports straight from the <em>Import &rarr; zip</em> menu.',
    before_title: "Before you convert",
    before_1:
      "Audio is kept at the source rate instead of being re-encoded. Telmi's player resamples to 44100 Hz itself, so it plays, but the quality stays where the DAISY pack left it.",
    before_2:
      "Clips are taken as whole files. A pack that trims inside a file keeps the whole file.",
    before_3: "Only audio books are handled. Synchronised text and TTS are not.",
    before_4: "Scene images are the cover, or a placeholder showing the chapter number.",    desktop_title: "The desktop app does more",
    desktop_p1:
      "The desktop app speaks the cards with any voice installed on your computer, re-encodes audio to Telmi's exact spec, trims clips inside a file, and lets you listen to each chapter before converting. Its window shows in English, French, Chinese, Arabic, Turkish, German, Italian, Spanish, Portuguese or Dutch.",
    desktop_line:
      'Get it from the <a href="https://github.com/berthy456/daisy2telmi/releases">releases page</a> for Windows, Debian, Ubuntu, macOS or as an AppImage.',
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">source</a>',
    card_label: "Chapter {n}/{total}",
    log_loaded: "loaded {name}",
    log_files: "reading {n} file(s)",
    log_ready: "ready: {name}",
    log_error: "error: {message}",
    log_card_silent: "chapter {n} has no recorded announcement; its card stays silent",
    log_drop_zip: "drop a .zip pack, or use the folder button",
    log_chapters: "{n} chapter(s)",
    log_cover_set: "cover set: {w} x {h}",
    log_cover_url: "the site refused the image, so the browser could not read it. Download it and choose the file instead.",
    log_cover_bad: "this file is not an image the browser can read",
    prog_title_audio: "title audio",
    prog_title_images: "title images",
    prog_metadata: "story metadata",
  },
  fr: {
    tagline:
      "Déposez un livre audio DAISY 2.02, obtenez un dossier d'histoire Telmi. Rien n'est envoyé : la conversion se fait dans cet onglet.",
    drop_title: "Déposez un pack DAISY ici",
    drop_hint: "un pack .zip",
    pick_zip: "Choisir un zip",
    pick_folder: "Choisir un dossier",
    convert: "Convertir",
    download: "Télécharger le zip",
    language: "Langue",
    cover_title: "Image de couverture",
    cover_hint: "Facultatif. Sans couverture, les cartes affichent le numéro du chapitre sur fond uni.",
    cover_pick: "Choisir une image",
    cover_url: "ou coller un lien d'image",
    cover_use: "Utiliser ce lien",
    cover_search: "Chercher sur Google Images",
    cover_clear: "Retirer",
    what_title: "Ce que vous obtenez",
    what_p1:
      "Un chapitre Telmi par chapitre DAISY de premier niveau, plus une carte de menu avant chacun pour naviguer avec les boutons Telmi. Le titre parlé du pack devient title.mp3.",
    what_p2:
      "Le zip est nommé comme Telmi Sync nomme les histoires, <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>, et s'importe directement depuis le menu <em>Import &rarr; zip</em>.",
    before_title: "Avant de convertir",
    before_1:
      "L'audio garde le débit de la source au lieu d'être ré-encodé. Le lecteur Telmi ré-échantillonne lui-même à 44100 Hz, donc il lit, mais la qualité reste celle du pack DAISY.",
    before_2:
      "Les extraits sont pris comme des fichiers entiers. Un pack qui coupe dans un fichier garde le fichier entier.",
    before_3: "Seuls les livres audio sont traités. Le texte synchronisé et la synthèse vocale ne le sont pas.",
    before_4: "Les images de scène reprennent la couverture, ou un pastillage avec le numéro du chapitre.",    desktop_title: "L'application de bureau fait plus",
    desktop_p1:
      "L'application de bureau fait parler les cartes avec n'importe quelle voix installée sur l'ordinateur, ré-encode l'audio aux spécifications exactes de Telmi, coupe les extraits dans un fichier et permet d'écouter chaque chapitre avant la conversion. Sa fenêtre s'affiche en anglais, français, chinois, arabe, turc, allemand, italien, espagnol, portugais ou néerlandais.",
    desktop_line:
      'Téléchargez-le depuis la <a href="https://github.com/berthy456/daisy2telmi/releases">page des versions</a> pour Windows, Debian, Ubuntu, macOS ou en AppImage.',
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">source</a>',
    card_label: "Chapitre {n}/{total}",
    log_loaded: "chargé {name}",
    log_files: "lecture de {n} fichier(s)",
    log_ready: "prêt : {name}",
    log_error: "erreur : {message}",
    log_card_silent: "le chapitre {n} n'a pas d'annonce enregistrée ; sa carte reste muette",
    log_drop_zip: "déposez un pack .zip, ou utilisez le bouton dossier",
    log_chapters: "{n} chapitre(s)",
    log_cover_set: "couverture choisie : {w} x {h}",
    log_cover_url: "le site a refusé l'image, le navigateur n'a pas pu la lire. Téléchargez-la et choisissez le fichier.",
    log_cover_bad: "ce fichier n'est pas une image que le navigateur sait lire",
    prog_title_audio: "audio du titre",
    prog_title_images: "images du titre",
    prog_metadata: "métadonnées de l'histoire",
  },
  zh: {
    tagline: "放入 DAISY 2.02 有声书包，得到 Telmi 故事文件夹。不上传任何内容：转换在本页完成。",
    drop_title: "把 DAISY 包放到这里",
    drop_hint: "一个 .zip 包",
    pick_zip: "选择 zip",
    pick_folder: "选择文件夹",
    convert: "转换",
    download: "下载故事 zip",
    language: "语言",
    cover_title: "封面图片",
    cover_hint: "可选。没有封面时，卡片在纯色背景上显示章节号。",
    cover_pick: "选择图片",
    cover_url: "或粘贴图片链接",
    cover_use: "使用此链接",
    cover_search: "谷歌图片搜索",
    cover_clear: "移除",
    what_title: "你会得到什么",
    what_p1: "每个 DAISY 顶层章节对应一个 Telmi 章节，每章前加一张菜单卡，方便用 Telmi 按钮导航。包里的口述标题成为 title.mp3。",
    what_p2:
      'zip 的命名方式与 Telmi Sync 相同：<code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>，可直接从 <em>导入 &rarr; zip</em> 菜单导入。',
    before_title: "转换之前",
    before_1: "音频保留源码率，不重新编码。Telmi 播放器自己重采样到 44100 Hz，所以能播放，但音质取决于 DAISY 包。",
    before_2: "片段按整个文件取出。若包在文件内部剪切，这里仍保留整个文件。",
    before_3: "只处理有声书，不处理同步文本和语音合成。",
    before_4: "场景图片使用封面，或用显示章节号的占位图。",    desktop_title: "桌面版功能更多",
    desktop_p1:
      "桌面版用电脑上安装的任意语音让卡片说话，按 Telmi 规格重新编码音频，可在文件内部剪切片段，并能在转换前试听每个章节。窗口界面可用英语、法语、中文、阿拉伯语、土耳其语、德语、意大利语、西班牙语、葡萄牙语和荷兰语显示。",
    desktop_line:
      "从<a href=\"https://github.com/berthy456/daisy2telmi/releases\">发布页</a>下载，支持 Windows、Debian、Ubuntu、macOS 和 AppImage。",
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">源代码</a>',
    card_label: "第 {n}/{total} 章",
    log_loaded: "已载入 {name}",
    log_files: "正在读取 {n} 个文件",
    log_ready: "完成：{name}",
    log_error: "错误：{message}",
    log_card_silent: "没有第 {n} 章的录音；该卡片保持静音",
    log_drop_zip: "请放入 .zip 包，或使用文件夹按钮",
    log_chapters: "{n} 章",
    log_cover_set: "已选封面：{w} x {h}",
    log_cover_url: "该网站拒绝提供图片，浏览器无法读取。请先下载，再选择文件。",
    log_cover_bad: "这个文件不是浏览器能读取的图片",
    prog_title_audio: "标题音频",
    prog_title_images: "标题图片",
    prog_metadata: "故事元数据",
  },
  ar: {
    tagline: "ضع حزمة كتاب صوتي DAISY 2.02 لتحصل على مجلد قصة Telmi. لا يُرفع شيء: التحويل يجري في هذه الصفحة.",
    drop_title: "ضع حزمة DAISY هنا",
    drop_hint: "حزمة بامتداد zip",
    pick_zip: "اختر ملف zip",
    pick_folder: "اختر مجلداً",
    convert: "تحويل",
    download: "تنزيل ملف القصة",
    language: "اللغة",
    cover_title: "صورة الغلاف",
    cover_hint: "اختياري. بدون غلاف تعرض البطاقات رقم الفصل على خلفية سادة.",
    cover_pick: "اختر صورة",
    cover_url: "أو الصق رابط صورة",
    cover_use: "استخدم هذا الرابط",
    cover_search: "بحث في صور جوجل",
    cover_clear: "إزالة",
    what_title: "ماذا تحصل",
    what_p1: "فصل Telmi واحد لكل فصل رئيسي في DAISY، مع بطاقة قائمة قبل كل فصل لتسهيل التنقل بأزرار Telmi. العنوان المنطوق في الحزمة يصبح title.mp3.",
    what_p2:
      'يُسمّى ملف zip كما يسمّي Telmi Sync القصص: <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>، ويُستورد مباشرة من قائمة <em>استيراد &rarr; zip</em>.',
    before_title: "قبل التحويل",
    before_1: "يبقى الصوت بمعدل المصدر دون إعادة ترميز. مشغل Telmi يعيد التردد إلى 44100 هرتز بنفسه، فيعمل الصوت، لكن الجودة تبقى كما تركتها الحزمة.",
    before_2: "تؤخذ المقاطع كملفات كاملة. الحزمة التي تقطع داخل ملف تبقى ملفها كاملاً.",
    before_3: "تُعالج الكتب الصوتية فقط، لا النص المتزامن ولا تحويل النص إلى كلام.",
    before_4: "صور المشاهد هي الغلاف، أو صورة مؤقتة تعرض رقم الفصل.",    desktop_title: "تطبيق سطح المكتب أوسع",
    desktop_p1:
      "تطبيق سطح المكتب ينطق البطاقات بأي صوت مثبّت على الحاسوب، ويعيد ترميز الصوت إلى مواصفات Telmi بدقة، ويقص المقاطع داخل الملف، ويسمح بالاستماع إلى كل فصل قبل التحويل. وتُعرض نافذته بالإنجليزية والفرنسية والصينية والعربية والتركية والألمانية والإيطالية والإسبانية والبرتغالية والهولندية.",
    desktop_line:
      'نزّله من <a href="https://github.com/berthy456/daisy2telmi/releases">صفحة الإصدارات</a> لويندوز وديبيان وأوبونتو وmacOS أو كملف AppImage.',
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">المصدر</a>',
    card_label: "الفصل {n}/{total}",
    log_loaded: "تم تحميل {name}",
    log_files: "قراءة {n} ملف",
    log_ready: "جاهز: {name}",
    log_error: "خطأ: {message}",
    log_card_silent: "لا يوجد إعلان مسجّل للفصل {n}؛ تبقى بطاقته صامتة",
    log_drop_zip: "ضع حزمة zip أو استخدم زر المجلد",
    log_chapters: "{n} فصل",
    log_cover_set: "الغلاف: {w} x {h}",
    log_cover_url: "رفض الموقع الصورة فلم يستطع المتصفح قراءتها. نزّلها ثم اختر الملف.",
    log_cover_bad: "هذا الملف ليس صورة يستطيع المتصفح قراءتها",
    prog_title_audio: "صوت العنوان",
    prog_title_images: "صور العنوان",
    prog_metadata: "بيانات القصة",
  },
  tr: {
    tagline:
      "Bir DAISY 2.02 sesli kitap paketi bırakın, Telmi hikâye klasörü alın. Hiçbir şey yüklenmez: dönüşüm bu sekmede yapılır.",
    drop_title: "Bir DAISY paketini buraya bırakın",
    drop_hint: "bir .zip paketi",
    pick_zip: "zip seçin",
    pick_folder: "klasör seçin",
    convert: "Dönüştür",
    download: "Hikâye zip'ini indir",
    language: "Dil",
    cover_title: "Kapak resmi",
    cover_hint: "Zorunlu değil. Kapak yoksa kartlar bölüm numarasını düz bir zeminde gösterir.",
    cover_pick: "resim seçin",
    cover_url: "ya da bir resim bağlantısı yapıştırın",
    cover_use: "Bu bağlantıyı kullan",
    cover_search: "Google Görseller'de ara",
    cover_clear: "Kaldır",
    what_title: "Ne elde edersiniz",
    what_p1:
      "Her üst düzey DAISY bölümü için bir Telmi bölümü, ayrıca her bölümden önce Telmi düğmeleriyle gezinmeyi sağlayan bir menü kartı. Paketin sesli başlığı title.mp3 olur.",
    what_p2:
      "Zip, Telmi Sync'in hikâyeleri adlandırdığı gibi adlandırılır ve <em>İçe aktar &rarr; zip</em> menüsünden doğrudan aktarılır.",
    before_title: "Dönüştürmeden önce",
    before_1:
      "Ses yeniden kodlanmaz, kaynak hızında kalır. Telmi oynatıcısı kendisi 44100 Hz'e çevirdiği için çalar, ama kalite paketin bıraktığı yerde kalır.",
    before_2:
      "Kırpıntılar bütün dosya olarak alınır. Bir dosyanın içinde kesim yapan paket dosyanın tamamını korur.",
    before_3: "Yalnızca sesli kitaplar işlenir. Eşzamanlı metin ve ses sentezi işlenmez.",
    before_4: "Sahne resimleri kapaktır, ya da bölüm numarasını gösteren bir yer tutucudur.",    desktop_title: "Masaüstü uygulaması daha fazlasını yapar",
    desktop_p1:
      "Masaüstü uygulaması kartları bilgisayarda kurulu herhangi bir sesle konuşturur, sesi Telmi'nin tam ölçütlerine göre yeniden kodlar, kırpımları dosyanın içinde keser ve dönüştürmeden önce her bölümü dinletir. Penceresi İngilizce, Fransızca, Çince, Arapça, Türkçe, Almanca, İtalyanca, İspanyolca, Portekizce ve Felemenkçe gösterilir.",
    desktop_line:
      "<a href=\"https://github.com/berthy456/daisy2telmi/releases\">Sürümler sayfasından</a> Windows, Debian, Ubuntu, macOS veya AppImage olarak edinin.",
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">kaynak</a>',
    card_label: "Bölüm {n}/{total}",
    log_loaded: "{name} yüklendi",
    log_files: "{n} dosya okunuyor",
    log_ready: "hazır: {name}",
    log_error: "hata: {message}",
    log_card_silent: "bolum {n} icin kayit yok; karti sessiz kalir",
    log_drop_zip: "bir .zip paketi bırakın ya da klasör düğmesini kullanın",
    log_chapters: "{n} bölüm",
    log_cover_set: "kapak seçildi: {w} x {h}",
    log_cover_url: "site resmi reddetti, tarayıcı okuyamadı. İndirip dosyayı seçin.",
    log_cover_bad: "bu dosya tarayıcının okuyabildiği bir resim değil",
    prog_title_audio: "başlık sesi",
    prog_title_images: "başlık resimleri",
    prog_metadata: "hikâye üst verisi",
  },
  de: {
    tagline:
      "DAISY-2.02-Hörbuchpaket ablegen, Telmi-Geschichtenordner erhalten. Nichts wird hochgeladen: die Umwandlung läuft in diesem Tab.",
    drop_title: "Ein DAISY-Paket hier ablegen",
    drop_hint: "ein .zip-Paket",
    pick_zip: "Zip wählen",
    pick_folder: "Ordner wählen",
    convert: "Umwandeln",
    download: "Geschichten-Zip herunterladen",
    language: "Sprache",
    cover_title: "Coverbild",
    cover_hint: "Optional. Ohne Cover zeigen die Karten die Kapitelzahl auf einfarbigem Grund.",
    cover_pick: "Bild wählen",
    cover_url: "oder einen Bildlink einfügen",
    cover_use: "Diesen Link benutzen",
    cover_search: "Bei Google Bilder suchen",
    cover_clear: "Entfernen",
    what_title: "Was Sie erhalten",
    what_p1:
      "Ein Telmi-Kapitel je DAISY-Kapitel der obersten Ebene, dazu vor jedem eine Menükarte, damit die Geschichte mit den Telmi-Knöpfen navigierbar ist. Der gesprochene Titel des Pakets wird title.mp3.",
    what_p2:
      'Das Zip heisst so, wie Telmi Sync Geschichten benennt, <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>, und wird direkt über <em>Importieren &rarr; zip</em> importiert.',
    before_title: "Vor dem Umwandeln",
    before_1:
      "Audio bleibt in der Quellrate statt neu kodiert zu werden. Der Telmi-Spieler sampelt selbst auf 44100 Hz um, es läuft also, aber die Qualität bleibt, wo das DAISY-Paket sie hinterlassen hat.",
    before_2:
      "Ausschnitte werden als ganze Dateien übernommen. Ein Paket, das innerhalb einer Datei schneidet, behält die ganze Datei.",
    before_3: "Nur Hörbücher werden verarbeitet. Synchronisierter Text und Sprachausgabe nicht.",
    before_4: "Die Szenenbilder sind das Cover oder ein Platzhalter mit der Kapitelzahl.",    desktop_title: "Die Desktop-App kann mehr",
    desktop_p1:
      "Die Desktop-App lässt die Karten mit jeder auf dem Rechner installierten Stimme sprechen, kodiert Audio nach Telmis genauer Vorgabe neu, schneidet Ausschnitte innerhalb einer Datei und erlaubt es, jedes Kapitel vor der Konvertierung zu hören. Ihr Fenster ist auf Englisch, Französisch, Chinesisch, Arabisch, Türkisch, Deutsch, Italienisch, Spanisch, Portugiesisch und Niederländisch möglich.",
    desktop_line:
      "Aus der <a href=\"https://github.com/berthy456/daisy2telmi/releases\">Versionsseite</a> für Windows, Debian, Ubuntu, macOS oder als AppImage holen.",
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">Quellcode</a>',
    card_label: "Kapitel {n}/{total}",
    log_loaded: "{name} geladen",
    log_files: "{n} Datei(en) werden gelesen",
    log_ready: "bereit: {name}",
    log_error: "Fehler: {message}",
    log_card_silent: "Kapitel {n} hat keine Aufnahme; die Karte bleibt stumm",
    log_drop_zip: "ein .zip-Paket ablegen oder das Ordner-Knöpfchen benutzen",
    log_chapters: "{n} Kapitel",
    log_cover_set: "Cover gesetzt: {w} x {h}",
    log_cover_url: "Die Seite hat das Bild abgelehnt, der Browser konnte es nicht lesen. Herunterladen und die Datei wählen.",
    log_cover_bad: "Diese Datei ist kein Bild, das der Browser lesen kann",
    prog_title_audio: "Titel-Audio",
    prog_title_images: "Titelbilder",
    prog_metadata: "Geschichten-Metadaten",
  },
  it: {
    tagline:
      "Trascina un pacchetto audiolibro DAISY 2.02, ottieni una cartella storia Telmi. Non viene caricato nulla: la conversione avviene in questa scheda.",
    drop_title: "Trascina qui un pacchetto DAISY",
    drop_hint: "un pacchetto .zip",
    pick_zip: "Scegli uno zip",
    pick_folder: "Scegli una cartella",
    convert: "Converti",
    download: "Scarica lo zip della storia",
    language: "Lingua",
    cover_title: "Immagine di copertina",
    cover_hint: "Facoltativa. Senza copertina le carte mostrano il numero del capitolo su sfondo uniforme.",
    cover_pick: "Scegli un'immagine",
    cover_url: "o incolla un link all'immagine",
    cover_use: "Usa questo link",
    cover_search: "Cerca su Google Immagini",
    cover_clear: "Rimuovi",
    what_title: "Cosa ottieni",
    what_p1:
      "Un capitolo Telmi per ogni capitolo DAISY di primo livello, più una carta menu prima di ciascuno, così la storia si naviga con i tasti Telmi. Il titolo parlato del pacchetto diventa title.mp3.",
    what_p2:
      'Lo zip è nominato come Telmi Sync nomina le storie, <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>, e si importa dal menu <em>Importa &rarr; zip</em>.',
    before_title: "Prima di convertire",
    before_1:
      "L'audio resta alla velocità della fonte invece di essere ricodificato. Il lettore Telmi ricampiona da sé a 44100 Hz, quindi funziona, ma la qualità resta quella del pacchetto DAISY.",
    before_2:
      "Le clip sono prese come file interi. Un pacchetto che taglia dentro un file mantiene il file intero.",
    before_3: "Solo gli audiolibri sono gestiti. Il testo sincronizzato e la sintesi vocale no.",
    before_4: "Le immagini di scena sono la copertina, o un segnaposto con il numero del capitolo.",    desktop_title: "L'app per desktop fa di più",
    desktop_p1:
      "L'app per desktop fa parlare le carte con qualsiasi voce installata sul computer, ricodifica l'audio alle specifiche esatte di Telmi, taglia le clip dentro un file e permette di ascoltare ogni capitolo prima della conversione. La sua finestra si mostra in inglese, francese, cinese, arabo, turco, tedesco, italiano, spagnolo, portoghese o neerlandese.",
    desktop_line:
      "Prendilo dalla <a href=\"https://github.com/berthy456/daisy2telmi/releases\">pagina delle versioni</a> per Windows, Debian, Ubuntu, macOS o come AppImage.",
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">sorgente</a>',
    card_label: "Capitolo {n}/{total}",
    log_loaded: "caricato {name}",
    log_files: "lettura di {n} file",
    log_ready: "pronto: {name}",
    log_error: "errore: {message}",
    log_card_silent: "il capitolo {n} non ha annuncio registrato; la scheda resta silenziosa",
    log_drop_zip: "trascina un pacchetto .zip o usa il pulsante cartella",
    log_chapters: "{n} capitolo/i",
    log_cover_set: "copertina scelta: {w} x {h}",
    log_cover_url: "il sito ha rifiutato l'immagine, il browser non ha potuto leggerla. Scaricala e scegli il file.",
    log_cover_bad: "questo file non è un'immagine che il browser sa leggere",
    prog_title_audio: "audio del titolo",
    prog_title_images: "immagini del titolo",
    prog_metadata: "metadati della storia",
  },
  es: {
    tagline:
      "Suelta un paquete de audiolibro DAISY 2.02 y obtén una carpeta de cuento Telmi. No se sube nada: la conversión ocurre en esta pestaña.",
    drop_title: "Suelta un paquete DAISY aquí",
    drop_hint: "un paquete .zip",
    pick_zip: "Elegir un zip",
    pick_folder: "Elegir una carpeta",
    convert: "Convertir",
    download: "Descargar el zip del cuento",
    language: "Idioma",
    cover_title: "Imagen de portada",
    cover_hint: "Opcional. Sin portada, las tarjetas muestran el número de capítulo sobre un fondo liso.",
    cover_pick: "Elegir una imagen",
    cover_url: "o pegar un enlace de imagen",
    cover_use: "Usar este enlace",
    cover_search: "Buscar en Google Imágenes",
    cover_clear: "Quitar",
    what_title: "Qué obtienes",
    what_p1:
      "Un capítulo Telmi por cada capítulo DAISY de primer nivel, más una tarjeta de menú antes de cada uno para navegar con los botones Telmi. El título hablado del paquete pasa a ser title.mp3.",
    what_p2:
      'El zip se nombra como Telmi Sync nombra los cuentos, <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>, y se importa directo desde <em>Importar &rarr; zip</em>.',
    before_title: "Antes de convertir",
    before_1:
      "El audio conserva la tasa de origen en vez de recodificarse. El reproductor Telmi remuestrea él mismo a 44100 Hz, así que suena, pero la calidad queda donde la dejó el paquete DAISY.",
    before_2:
      "Los fragmentos se toman como archivos completos. Un paquete que recorta dentro de un archivo conserva el archivo entero.",
    before_3: "Solo se procesan audiolibros. El texto sincronizado y la síntesis de voz no.",
    before_4: "Las imágenes de escena son la portada, o un marcador con el número de capítulo.",    desktop_title: "La aplicación de escritorio hace más",
    desktop_p1:
      "La aplicación de escritorio hace hablar las tarjetas con cualquier voz instalada en el ordenador, recodifica el audio a la especificación exacta de Telmi, recorta fragmentos dentro de un archivo y permite escuchar cada capítulo antes de convertir. Su ventana se muestra en inglés, francés, chino, árabe, turco, alemán, italiano, español, portugués y neerlandés.",
    desktop_line:
      "Bájalo de la <a href=\"https://github.com/berthy456/daisy2telmi/releases\">página de versiones</a> para Windows, Debian, Ubuntu, macOS o como AppImage.",
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">código fuente</a>',
    card_label: "Capítulo {n}/{total}",
    log_loaded: "cargado {name}",
    log_files: "leyendo {n} archivo(s)",
    log_ready: "listo: {name}",
    log_error: "error: {message}",
    log_card_silent: "el capítulo {n} no tiene anuncio grabado; su ficha queda en silencio",
    log_drop_zip: "suelta un paquete .zip o usa el botón de carpeta",
    log_chapters: "{n} capítulo(s)",
    log_cover_set: "portada elegida: {w} x {h}",
    log_cover_url: "el sitio rechazó la imagen y el navegador no pudo leerla. Descárgala y elige el archivo.",
    log_cover_bad: "este archivo no es una imagen que el navegador pueda leer",
    prog_title_audio: "audio del título",
    prog_title_images: "imágenes del título",
    prog_metadata: "metadatos del cuento",
  },
  pt: {
    tagline:
      "Solte um pacote de audiobook DAISY 2.02 e receba uma pasta de história Telmi. Nada é enviado: a conversão roda nesta aba.",
    drop_title: "Solte um pacote DAISY aqui",
    drop_hint: "um pacote .zip",
    pick_zip: "Escolher um zip",
    pick_folder: "Escolher uma pasta",
    convert: "Converter",
    download: "Baixar o zip da história",
    language: "Idioma",
    cover_title: "Imagem de capa",
    cover_hint: "Opcional. Sem capa, os cartões mostram o número do capítulo sobre fundo liso.",
    cover_pick: "Escolher uma imagem",
    cover_url: "ou colar um link de imagem",
    cover_use: "Usar este link",
    cover_search: "Pesquisar no Google Imagens",
    cover_clear: "Remover",
    what_title: "O que você recebe",
    what_p1:
      "Um capítulo Telmi para cada capítulo DAISY de nível superior, mais um cartão de menu antes de cada um, para navegar com os botões Telmi. O título falado do pacote vira title.mp3.",
    what_p2:
      'O zip é nomeado como o Telmi Sync nomeia as histórias, <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>, e importa direto do menu <em>Importar &rarr; zip</em>.',
    before_title: "Antes de converter",
    before_1:
      "O áudio mantém a taxa de origem em vez de ser recodificado. O leitor Telmi reamostra sozinho para 44100 Hz, então toca, mas a qualidade fica onde o pacote DAISY a deixou.",
    before_2:
      "Os trechos são pegos como arquivos inteiros. Um pacote que corta dentro de um arquivo mantém o arquivo inteiro.",
    before_3: "Só audiobooks são tratados. Texto sincronizado e síntese de voz não.",
    before_4: "As imagens de cena são a capa, ou um marcador com o número do capítulo.",    desktop_title: "O aplicativo de desktop faz mais",
    desktop_p1:
      "O aplicativo de desktop faz os cartões falarem com qualquer voz instalada no computador, recodifica o áudio à especificação exata do Telmi, corta trechos dentro de um arquivo e permite ouvir cada capítulo antes de converter. Sua janela aparece em inglês, francês, chinês, árabe, turco, alemão, italiano, espanhol, português e holandês.",
    desktop_line:
      "Baixe da <a href=\"https://github.com/berthy456/daisy2telmi/releases\">página de versões</a> para Windows, Debian, Ubuntu, macOS ou como AppImage.",
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">código fonte</a>',
    card_label: "Capítulo {n}/{total}",
    log_loaded: "carregado {name}",
    log_files: "lendo {n} arquivo(s)",
    log_ready: "pronto: {name}",
    log_error: "erro: {message}",
    log_card_silent: "o capítulo {n} não tem anúncio gravado; seu cartão fica silencioso",
    log_drop_zip: "solte um pacote .zip ou use o botão de pasta",
    log_chapters: "{n} capítulo(s)",
    log_cover_set: "capa escolhida: {w} x {h}",
    log_cover_url: "o site recusou a imagem e o navegador não conseguiu lê-la. Baixe-a e escolha o arquivo.",
    log_cover_bad: "este arquivo não é uma imagem que o navegador sabe ler",
    prog_title_audio: "áudio do título",
    prog_title_images: "imagens do título",
    prog_metadata: "metadados da história",
  },
  nl: {
    tagline:
      "Zet een DAISY 2.02 audioboekpakket hier neer, krijg een Telmi-verhalenmap. Er wordt niets geüpload: de omzetting gebeurt in dit tabblad.",
    drop_title: "Zet een DAISY-pakket hier neer",
    drop_hint: "een .zip-pakket",
    pick_zip: "Kies een zip",
    pick_folder: "Kies een map",
    convert: "Omzetten",
    download: "Verhaal-zip downloaden",
    language: "Taal",
    cover_title: "Omslagafbeelding",
    cover_hint: "Optioneel. Zonder omslag tonen de kaarten het hoofdstuknummer op een effen achtergrond.",
    cover_pick: "Kies een afbeelding",
    cover_url: "of plak een afbeeldingslink",
    cover_use: "Deze link gebruiken",
    cover_search: "Zoeken op Google Afbeeldingen",
    cover_clear: "Verwijderen",
    what_title: "Wat je krijgt",
    what_p1:
      "Een Telmi-hoofdstuk per DAISY-hoofdstuk op het hoogste niveau, plus een menukaart ervoor, zodat het verhaal met de Telmi-knoppen te navigeren is. De gesproken titel van het pakket wordt title.mp3.",
    what_p2:
      'De zip krijgt dezelfde naam als Telmi Sync verhalen geeft, <code>&lt;category&gt;_&lt;age&gt;_&lt;title&gt;_&lt;uuid&gt;</code>, en importeert vanuit <em>Importeren &rarr; zip</em>.',
    before_title: "Voordat je omzet",
    before_1:
      "Audio blijft op de bronbitsnelheid in plaats van hercodeerd te worden. De Telmi-speler samplet zelf naar 44100 Hz, dus het speelt, maar de kwaliteit blijft waar het DAISY-pakket haar liet.",
    before_2:
      "Fragmenten worden als hele bestanden genomen. Een pakket dat binnen een bestand knipt, houdt het hele bestand.",
    before_3: "Alleen audioboeken worden verwerkt. Gesynchroniseerde tekst en TTS niet.",
    before_4: "De scèneafbeeldingen zijn het omslag, of een placeholder met het hoofdstuknummer.",    desktop_title: "De desktop-app kan meer",
    desktop_p1:
      "De desktop-app laat de kaarten spreken met elke stem die op de computer is geïnstalleerd, hercodeert audio naar Telmis exacte specificatie, knipt fragmenten binnen een bestand en laat je elk hoofdstuk voor de omzetting beluisteren. Zijn venster is in het Engels, Frans, Chinees, Arabisch, Turks, Duits, Italiaans, Spaans, Portugees en Nederlands te tonen.",
    desktop_line:
      "Haal hem van de <a href=\"https://github.com/berthy456/daisy2telmi/releases\">uitgavenpagina</a> voor Windows, Debian, Ubuntu, macOS of als AppImage.",
    footer_line: 'GPL-3.0-or-later &middot; <a href="https://github.com/berthy456/daisy2telmi">broncode</a>',
    card_label: "Hoofdstuk {n}/{total}",
    log_loaded: "{name} geladen",
    log_files: "{n} bestand(en) lezen",
    log_ready: "klaar: {name}",
    log_error: "fout: {message}",
    log_card_silent: "hoofdstuk {n} heeft geen opgesproken melding; de kaart blijft stil",
    log_drop_zip: "zet een .zip-pakket neer, of gebruik de mapknop",
    log_chapters: "{n} hoofdstuk(ken)",
    log_cover_set: "omslag gekozen: {w} x {h}",
    log_cover_url: "de site weigerde de afbeelding, dus de browser kon hem niet lezen. Download hem en kies het bestand.",
    log_cover_bad: "dit bestand is geen afbeelding die de browser kan lezen",
    prog_title_audio: "titelaudio",
    prog_title_images: "titelafbeeldingen",
    prog_metadata: "verhaalmetadata",
  },
};

/** The saved choice wins, then the browser's language, then English. */
export function pickLanguage(preferred, browserLanguage) {
  if (LANGUAGES.includes(preferred)) return preferred;
  const base = String(browserLanguage || "").toLowerCase().split("-")[0];
  return LANGUAGES.includes(base) ? base : "en";
}

export function text(lang, key, values = {}) {
  const table = UI[lang] || UI.en;
  const template = table[key] ?? UI.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => (values[name] ?? ""));
}

export function apply(lang) {
  const chosen = LANGUAGES.includes(lang) ? lang : "en";
  document.documentElement.lang = chosen;
  document.documentElement.dir = RTL.has(chosen) ? "rtl" : "ltr";
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = text(chosen, node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-html]")) {
    node.innerHTML = text(chosen, node.dataset.i18nHtml);
  }
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    node.placeholder = text(chosen, node.dataset.i18nPlaceholder);
  }
  return chosen;
}
