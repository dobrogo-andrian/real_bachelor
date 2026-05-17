# КОНТЕКСТ БАКАЛАВРСЬКОЇ КВАЛІФІКАЦІЙНОЇ РОБОТИ

## 0. МЕТАДАНІ РОБОТИ

- Тема (UA): Прогнозування емоційної тональності текстових повідомлень у соціальних мережах
- Тема (EN): Predicting the emotional tone of social media text messages
- Спеціальність: F4 «Системний аналіз та наука про дані»
- ОПП: «Системний аналіз»
- Спеціалізація: Аналіз даних (Data Science)
- Університет: Національний університет «Львівська політехніка»
- Кафедра: Інформаційні системи та мережі
- Загальний обсяг: 70–90 сторінок
- Мова: українська (анотація також англійською)
- Робоча назва програмного засобу в репозиторії: `Comment Lab` (`templates/index.html:9`, `README.md:1-10`)
- Тип програмного засобу: веб-система на Flask для збору, збагачення, аналізу та візуалізації коментарів Instagram (`app.py:50-94`, `README.md:3-31`)

---

## 1. ВСТУП (2–3 сторінки)

### 1.1. Актуальність теми

Актуальність теми підтверджується як масштабом самої платформи Instagram, так і реальною архітектурою цього проекту. За офіційним повідомленням Meta від 18 вересня 2025 року Instagram має 3 млрд щомісячно активних користувачів, а Reels пересилаються понад 4.5 млрд разів на день у межах платформ Meta. Це означає, що соціальні мережі генерують масиви коротких, шумних, емоційно насичених текстів, де коментарі містять цінний сигнал для маркетингу, PR, brand monitoring і підтримки клієнтів.

Для бізнесу такі дані важливі щонайменше з чотирьох причин:

- маркетинг і SMM: проект прямо орієнтований на сторінки Instagram і пост-рівневий аналіз реакцій аудиторії (`static/backend/extract_data.py:847-1065`, `static/backend/explorer_analysis.py:473-526`);
- PR і brand monitoring: Explorer та Advanced Analysis дозволяють переглядати мовний склад, частки позитивних/нейтральних/негативних реакцій, топ-пости та тренди (`templates/explorer.html:68-135`, `templates/advanced_analysis.html:214-289`, `static/assets/js/explorer-page.js:503-756`);
- клієнтська підтримка: система дає змогу фільтрувати коментарі за текстом, часом, лайками, мовою і sentiment-міткою (`static/backend/db_connection.py:669-852`);
- аналітика контенту: код рахує `positive_share`, `avg_comment_length`, `language_breakdown`, `solidarity_score` та часові тренди по постах (`static/backend/explorer_analysis.py:292-554`).

Проект також демонструє типові проблеми існуючих рішень для sentiment analysis у соціальних мережах:

- багатомовність: у pipeline явно підтримуються `uk`, `ru`, `en`, а всі інші випадки зводяться до `other` або `symbols_only` (`static/backend/enrich_comments.py:22-33`, `89-103`);
- сленг, емодзі, символи: у репозиторії є генератор синтетичного slang/emoji/symbol dataset (`model_fine_tuning/symbols/generation.py:89-150`) і клас `symbols_only` для неалфавітних коментарів (`static/backend/enrich_comments.py:89-99`);
- короткі та шумні тексти: перед аналізом коментарі нормалізуються, URL зводяться до `http`, згадки користувачів до `@user`, а довжина тексту обрізається до `max_length=128` токенів (`static/backend/enrich_comments.py:61-68`, `132-139`);
- обмеження платформи Instagram: проект не використовує офіційний API, а працює через Selenium scraping, з обробкою `checkpoint/challenge` та ручним логіном (`static/backend/extract_data.py:256-295`, `901-1065`).

за допомогою різних модулів проєкт виконує збір Instagram-коментарів, багатомовне визначення мови, донавчений sentiment-модуль, захищене зберігання облікових даних та веб-візуалізацію результатів. Формальний ринковий огляд аналогів ми додамо окремо в підрозділ 2.2.

### 1.2. Мета і завдання дослідження

**Мета дослідження:** розробити та дослідити веб-систему для збору коментарів Instagram, визначення їхньої мови, класифікації емоційної тональності за допомогою донавченої багатомовної трансформерної моделі, збереження результатів у базі даних SQL Server і візуалізації підсумкової аналітики у веб-інтерфейсі.

**Завдання дослідження:**

1. Проаналізувати предметну область аналізу тональності коментарів соціальних мереж та визначити склад вхідних/вихідних даних на основі таблиць `Comments` і `EnrichedComments` (`ddl/Comments.sql:1-38`, `ddl/EnrichedComments.sql:1-71`).
2. Реалізувати автентифікацію користувачів, захищене зберігання паролів і Instagram-облікових даних у таблиці `Users` (`app.py:103-132`, `static/backend/db_connection.py:194-540`, `ddl/Users.sql:1-28`).
3. Реалізувати модуль збору коментарів Instagram через Selenium з підтримкою ручного входу, повторного використання cookies та фіксації platform restrictions (`static/backend/extract_data.py:110-1065`).
4. Реалізувати завантаження сирих коментарів у SQL Server із дедуплікацією на основі `CommentHash` і пакетною вставкою через staging table (`static/backend/load_to_db.py:40-216`).
5. Реалізувати модуль enrichment: нормалізацію тексту, визначення основної мови коментаря, sentiment classification і запис результатів до `EnrichedComments` (`static/backend/enrich_comments.py:61-568`).
6. Реалізувати веб-інтерфейс Explorer та Advanced Analysis для перегляду сторінок, попереднього перегляду даних, фільтрації та побудови графіків (`app.py:573-674`, `templates/explorer.html:68-135`, `templates/advanced_analysis.html:69-289`).
7. Підготувати об’єднаний збалансований датасет та виконати fine-tuning LoRA-адаптерів поверх `cardiffnlp/twitter-xlm-roberta-base-sentiment` (`model_fine_tuning/prepare_and_balance_data.py:1-395`, `model_fine_tuning/train_lora_sentiment.py:44-520`).

### 1.3. Об'єкт дослідження

Процес аналізу емоційної тональності текстових повідомлень у соціальних мережах, зокрема коментарів Instagram, які збираються, зберігаються, збагачуються мовними та sentiment-ознаками і подаються користувачу у вигляді аналітичних візуалізацій.

### 1.4. Предмет дослідження

Методи та алгоритми NLP для sentiment analysis багатомовних текстових даних із соціальних мереж, а також програмні засоби інтеграції таких моделей у веб-систему аналітики.

### 1.5. Методи дослідження

**Методи збору даних**

- браузерний scraping Instagram через Selenium WebDriver, Chrome/ChromeDriver (`static/backend/extract_data.py:110-133`);
- ручний вхід користувача у випадку відсутності валідної сесії (`static/backend/extract_data.py:273-295`, `1007-1038`);
- повторне використання збережених cookies з HMAC-підписом і DPAPI-захистом (`static/backend/extract_data.py:340-398`, `static/backend/db_connection.py:283-361`);


**Методи підготовки тексту**

- Unicode normalization (`normalize_unicode`) (`static/backend/enrich_comments.py:57-58`);
- нормалізація URL та user mentions (`normalize_comment_for_analysis`) (`static/backend/enrich_comments.py:61-68`);
- дедуплікація коментарів за SHA-256 hash (`static/backend/load_to_db.py:40-47`, `218-222`);
- дедуплікація фінального train dataset за полем `text` (`model_fine_tuning/prepare_and_balance_data.py:380-386`);
- strict balancing класів шляхом random undersampling (`model_fine_tuning/prepare_and_balance_data.py:313-330`);

**Методи NLP**

- автоматичне визначення мови через `lingua-language-detector` (`static/backend/enrich_comments.py:75-103`);
- токенізація через `AutoTokenizer.from_pretrained(...)` (`model_fine_tuning/train_lora_sentiment.py:314-322`, `static/backend/enrich_comments.py:111-116`);
- обрізання послідовностей до `max_length=128` (`model_fine_tuning/train_lora_sentiment.py:51`, `static/backend/enrich_comments.py:132-139`).

**Моделі ML/DL**

- базова модель: `cardiffnlp/twitter-xlm-roberta-base-sentiment` (`model_fine_tuning/train_lora_sentiment.py:44`, `static/backend/enrich_comments.py:24`);
- fine-tuning через LoRA adapters (`r=16`, `lora_alpha=32`, `lora_dropout=0.1`, `target_modules=["query","value"]`) (`model_fine_tuning/train_lora_sentiment.py:363-372`, `model_fine_tuning/sentiment_lora_adapters/adapter_config.json`);
- inference у веб-системі виконується через Hugging Face `pipeline("text-classification")` після `merge_and_unload()` LoRA-адаптерів (`static/backend/enrich_comments.py:106-139`).

**Методи оцінки якості**

- `accuracy` та `f1_macro` (`model_fine_tuning/train_lora_sentiment.py:379-388`);
- додатково збережені `eval_loss`, `eval_runtime`, `eval_samples_per_second`, `eval_steps_per_second` у `trainer_state.json`;
- `precision`, `recall`, `confusion matrix`, `ROC-AUC` обчислюються окремим скриптом порівняння baseline/fine-tuned моделей `model_fine_tuning/evaluate_sentiment_models.py`; JSON-звіт за замовчуванням зберігається в `model_fine_tuning/artifacts/evaluation/model_comparison.json`.

**Методи візуалізації**

- серверна підготовка chart-ready структур у Python (`static/backend/explorer_analysis.py:473-526`);
- фронтенд-рендеринг графіків через кастомний SVG у vanilla JavaScript (`static/assets/js/explorer-page.js:205-406`, `static/assets/js/advanced-analysis-page.js:299-531`);

### 1.6. Практичне значення

Практичне значення роботи полягає у створенні реального веб-застосунку, що збирає коментарі зі сторінок Instagram, зберігає сирі та enriched-дані у SQL Server, визначає мову коментарів, класифікує їх за трьома класами тональності і дає змогу користувачу переглядати результати у вигляді таблиць, KPI та графіків.

---

## 2. РОЗДІЛ 1: АНАЛІТИЧНИЙ ОГЛЯД (10–12% обсягу ≈ 7–10 стор.)

### 2.1. Аналіз сучасного стану в галузі sentiment analysis

[TODO: потрібно написати повноцінний огляд літератури з посиланнями на наукові джерела.]

Що вже можна зафіксувати на основі проекту:

- поточна реалізація проекту спирається не на словниковий підхід, а на трансформерну багатомовну модель `twitter-xlm-roberta-base-sentiment` з LoRA fine-tuning (`model_fine_tuning/train_lora_sentiment.py:44-49`, `static/backend/enrich_comments.py:24-26`);
- проект орієнтований на короткі соціально-медійні тексти, де є URL, user mentions, багатомовність, символи та емодзі (`static/backend/enrich_comments.py:61-68`, `model_fine_tuning/symbols/generation.py:89-120`);
- у проекті відсутні реалізації baseline-моделей на кшталт Naive Bayes, SVM, Logistic Regression, тому огляд альтернатив слід виконати теоретично.

Орієнтовний план літературного огляду:

- класичні підходи: VADER, TextBlob, SentiWordNet;
- ML-підходи: Naive Bayes, SVM, Logistic Regression;
- DL-підходи: CNN/LSTM для тексту;
- трансформери: BERT, RoBERTa, XLM-RoBERTa, multilingual sentiment models;
- специфіка соціальних мереж: емодзі, сленг, багатомовність, короткі репліки, sarcasm detection.

### 2.2. Порівняльний аналіз наявних рішень

[TODO: у репозиторії відсутній підготовлений огляд сторонніх сервісів/інструментів, тому цей підрозділ потрібно заповнити окремим ринковим аналізом.]

Що можна стверджувати вже зараз на підставі проекту:

- власне рішення інтегрує **збір Instagram-коментарів**;
- рішення підтримує **локальне розгортання** та роботу з власною SQL Server базою (`README.md:79-118`, `ddl/*.sql`);
- у проекті реалізовано **багатомовний analysis pipeline** для `uk`, `ru`, `en`, а також fallback-класи `other` і `symbols_only` (`static/backend/enrich_comments.py:22-33`);
- результати представлені не лише у вигляді label prediction, а й через окремі веб-сторінки Explorer / Advanced Analysis з preview, filters і графіками (`app.py:573-674`, `static/assets/js/explorer-page.js:503-756`, `static/assets/js/advanced-analysis-page.js:539-746`).

Шаблон таблиці для завершення підрозділу:

| Назва рішення | Підтримка мов | Точність | Підтримка Instagram | Наявність візуалізації | Ціна / ліцензія | Примітка |
|---|---|---|---|---|---|---|
| [TODO] | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] | Порівняти з `Comment Lab` |
| [TODO] | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] | Порівняти з `Comment Lab` |
| [TODO] | [TODO] | [TODO] | [TODO] | [TODO] | [TODO] | Порівняти з `Comment Lab` |
| Власне рішення `Comment Lab` | `uk`, `ru`, `en`, `other`, `symbols_only` | `eval_accuracy=0.7976`, `eval_f1_macro=0.7969` | Так, через Selenium scraping | Так | Локальний кодовий проект | Метрики взяті з training artifacts |

---

## 3. РОЗДІЛ 2: АНАЛІЗ ОБ'ЄКТА ДОСЛІДЖЕННЯ (20–25% ≈ 14–22 стор.)

### 3.1. Визначення проблемної області та постановка задачі

**Вхідні дані**

Фактична структура вхідних сирих даних задається таблицею `Comments`:

- `CommentHash` — унікальний хеш коментаря (`ddl/Comments.sql:2`);
- `PageName` — назва Instagram-сторінки (`ddl/Comments.sql:3`);
- `PageID` — ідентифікатор/handle сторінки (`ddl/Comments.sql:4`);
- `PostHref` — URL поста (`ddl/Comments.sql:5`);
- `PostTime` — час публікації поста (`ddl/Comments.sql:6`);
- `Comment` — текст коментаря (`ddl/Comments.sql:7`);
- `CommentTime` — час коментаря (`ddl/Comments.sql:8`);
- `CommentLikes` — кількість лайків коментаря (`ddl/Comments.sql:9`);
- `LoadTime` — час завантаження в БД (`ddl/Comments.sql:10`).

**Вихідні дані**

Після enrichment для кожного коментаря зберігаються `MainLanguage`, `NormalizedComment`, `Sentiment`, `ProcessedTime`, `Source`, `CommentOrder`. Ці поля визначені в `EnrichedComments` (`ddl/EnrichedComments.sql:8-14`) і реально заповнюються у `prepare_enriched_rows(...)` (`static/backend/enrich_comments.py:300-342`).

Підсумкова аналітика включає:

- summary KPI: `total_comments`, `distinct_posts`, `languages`, `positive_share`, `avg_comment_length`, `latest_processed_time` (`static/backend/explorer_analysis.py:528-537`);
- табличні breakdown-блоки: `language_breakdown`, `post_breakdown`, `solidarity_breakdown`, `solidarity_top_posts`, `sample_comments` (`static/backend/explorer_analysis.py:360-388`, `541-554`);
- графіки: 12 окремих chart datasets (`static/backend/explorer_analysis.py:473-526`).

**Функціональні вимоги до системи**

- реєстрація та логін користувачів (`app.py:361-406`, `695-714`);
- збереження та оновлення Instagram-облікових даних і cookies (`app.py:466-561`, `static/backend/db_connection.py:300-540`);
- збір коментарів зі сторінки Instagram (`app.py:717-761`, `static/backend/extract_data.py:901-1065`);
- запис сирих коментарів у БД (`static/backend/load_to_db.py:110-216`);
- enrichment для всієї БД, конкретної сторінки або дельти (`app.py:764-788`, `static/backend/enrich_comments.py:525-568`);
- побудова page-level analysis (`app.py:791-816`, `static/backend/explorer_analysis.py:557-564`);
- фільтрація enriched rows за кількома вимірами (`app.py:623-674`, `static/backend/db_connection.py:669-852`);
- візуалізація результатів у веб-інтерфейсі (`templates/explorer.html`, `templates/advanced_analysis.html`, `static/assets/js/*.js`).

**Нефункціональні вимоги**

- безпека: `scrypt`-hashing паролів, JWT cookies, CSRF protection, DPAPI encryption для Instagram secrets (`app.py:61-71`, `103-132`, `static/backend/db_connection.py:194-247`);
- керованість навантаженням: rate limiting для `/login`, `/process-data`, `/enrich-comments`, analysis API (`app.py:72-80`, `161-221`);
- масштабованість обробки: batch insertion, chunked DB reads, background jobs (`static/backend/load_to_db.py:225-266`, `static/backend/enrich_comments.py:259-568`, `static/backend/job_queue.py:7-62`);
- надійність до дублювання: `CommentHash` і `MERGE` upsert strategy (`static/backend/load_to_db.py:40-47`, `171-201`, `static/backend/enrich_comments.py:447-487`);
- зручність використання: окремі сторінки для extraction, guided exploration і direct filtering (`templates/index.html:47-127`).

### 3.2. Опис бізнес-процесу та визначення даних

| Крок | Опис | Відповідальні файли / функції | Які дані генеруються | Бібліотеки |
|---|---|---|---|---|
| 1 | Користувач вводить Instagram-сторінку і кількість постів | `templates/extractor.html:77-100`, `static/assets/js/extractor.js:281-328`, маршрут `/process-data` у `app.py:717-761` | JSON payload з `param1=target_page`, `param2=number_of_posts`, `headless_session_only` | Flask, vanilla JS |
| 2 | Система завантажує Instagram-сесію або чекає ручного логіну | `static/backend/extract_data.py:374-398`, `273-295`, `static/backend/db_connection.py:300-361` | payload cookies, статус ручного логіну, `aborted_reason` при блокуванні | Selenium, pyodbc, ctypes/DPAPI, hmac |
| 3 | Система знаходить потрібні пости і збирає коментарі | `static/backend/extract_data.py:847-899`, `745-769`, `512-647` | список `rows` для кожного поста, `PostHref`, `CommentTime`, `CommentLikes` | Selenium, pandas |
| 4 | Сирі коментарі зберігаються в таблицю `Comments` | `static/backend/load_to_db.py:77-107`, `110-216`, виклик через `comment_batch_handler` у `static/backend/extract_data.py:998-1000` | `CommentHash`, `PageName`, `PageID`, `PostHref`, `PostTime`, `Comment`, `CommentTime`, `CommentLikes`, `LoadTime` | pandas, pyodbc, hashlib |
| 5 | Виконується визначення мови та sentiment analysis | `static/backend/enrich_comments.py:89-103`, `106-160`, `300-342` | `MainLanguage`, `NormalizedComment`, `Sentiment`, `ProcessedTime`, `Source`, `CommentOrder` | lingua-language-detector, transformers, peft |
| 6 | Результати пишуться в `EnrichedComments` | `static/backend/enrich_comments.py:345-523` | `processed`, `added_count`, `updated_count` | pyodbc |
| 7 | Веб-інтерфейс будує summary, preview і charts | `static/backend/explorer_analysis.py:188-554`, `app.py:623-674`, `static/assets/js/explorer-page.js:503-756`, `static/assets/js/advanced-analysis-page.js:539-746` | KPI, preview rows, 12 chart datasets | Flask, vanilla JS |

**Текстовий опис процесу**

1. Користувач авторизується і відкриває сторінку `/extractor`.
2. Після надсилання форми маршрут `/process-data` перевіряє payload, дістає з БД Instagram credentials поточного користувача та наявні `PostHref` для обраної сторінки (`app.py:726-758`, `_run_process_data(...)` у `app.py:240-320`).
3. Модуль `extract_data(...)` запускає Chrome, намагається підвантажити cookies, а якщо це неможливо, переводить користувача у режим ручного логіну (`static/backend/extract_data.py:925-1038`).
4. Для кожного нового поста система скролить сторінку, відкриває коментарі, збирає текст/час/лайки й одразу перетворює їх на rows для БД (`static/backend/extract_data.py:401-510`, `512-647`, `static/backend/load_to_db.py:77-107`).
5. Після натискання enrichment-кнопки маршрут `/enrich-comments` запускає `enrich_comments(...)` в одному з режимів `page_name`, `page_id`, `whole_db`, `delta` (`app.py:773-785`, `static/backend/enrich_comments.py:525-568`).
6. Модуль enrichment нормалізує текст, визначає мову, обчислює sentiment і записує результат до `EnrichedComments` (`static/backend/enrich_comments.py:300-342`, `447-487`).
7. Explorer та Advanced Analysis звертаються вже не до сирих, а до enriched rows, будують summary та графіки, і рендерять їх як SVG на клієнті (`app.py:791-816`, `623-674`, `static/backend/explorer_analysis.py:473-554`).

### 3.3. Опис датасетів

#### Датасет 1

- Назва файлу / джерело: `model_fine_tuning/ukr-detect-ukr-emotions-binary/hf_saved_dataset/full_balanced_dataset.csv`; джерело вказане в downloader як `ukr-detect/ukr-emotions-binary` (`model_fine_tuning/ukr-detect-ukr-emotions-binary/download_dataset.py:2-26`)
- Кількість записів: `3465`
- Структура: `id, text, Joy, Fear, Anger, Sadness, Disgust, Surprise, label, sentiment_name`
- Призначення: зовнішній український датасет, перетворений із emotion labels у 3-класовий sentiment і збалансований (`download_dataset.py:54-108`)
- Мови: українська
- Розподіл класів: `0:1155; 1:1155; 2:1155`

#### Датасет 2

- Назва файлу / джерело: `model_fine_tuning/Sp1786-multiclass-sentiment-analysis-dataset/hf_saved_dataset/full_dataset.csv`; джерело вказане як `Sp1786/multiclass-sentiment-analysis-dataset` (`model_fine_tuning/Sp1786-multiclass-sentiment-analysis-dataset/download_dataset.py:2-25`)
- Кількість записів: `41643`
- Структура: `id, text, label, sentiment`
- Призначення: зовнішній sentiment dataset для об’єднання під час підготовки balanced dataset
- Мови: за вмістом перших рядків датасет англомовний; 
- Розподіл класів: `0:12168; 1:15507; 2:13968`

#### Датасет 3

- Назва файлу / джерело: `model_fine_tuning/sismetanin-rusentitweet-blob-main-rusentitweet-full/rusentitweet_full.csv`
- Кількість записів: `13392`
- Структура: фактичні колонки при імпорті `H1, text, label, id`; перша колонка в CSV має порожній заголовок
- Призначення: російськомовний твіттерний датасет sentiment-розмітки; `prepare_and_balance_data.py` уміє мапити `negative`, `neutral`, `positive`, а `speech/skip` відкидає (`model_fine_tuning/prepare_and_balance_data.py:208-243`, `284-287`)
- Мови: російська
- Розподіл label values у файлі: `negative:3298; neutral:5341; positive:2414; skip:1843; speech:496`

#### Додатковий локальний датасет

- Назва файлу: `model_fine_tuning/symbols/slang_data.csv`
- Кількість записів: `8617`
- Структура: `text, label`
- Призначення: синтетичний датасет для slang/emoji/symbol cases, який генерується скриптом `model_fine_tuning/symbols/generation.py:89-150`
- Мови: змішані короткі символьні/сленгові патерни; це не класичний природномовний корпус
- Розподіл класів: `0:3116; 1:2291; 2:3210`
- Примітка: у генераторі видно mojibake-рядки (`model_fine_tuning/symbols/generation.py:14-28`) 

#### Датасет 4: створений датасет для fine-tuning

- Назва файлу: `model_fine_tuning/balanced_sentiment_dataset/balanced_dataset.csv`
- Кількість записів: `59184`
- Структура: `text, label`
- Призначення: фінальний train/eval dataset для fine-tuning LoRA sentiment model (`model_fine_tuning/train_lora_sentiment.py:47`, `286-311`)
- Мови: змішаний multilingual corpus, сформований з локально знайдених файлів у `model_fine_tuning/` (`model_fine_tuning/prepare_and_balance_data.py:89-100`, `367-395`)
- Розмітка: три класи `0=negative`, `1=neutral`, `2=positive`
- Розподіл класів: `0:19728; 1:19728; 2:19728`
- Як створювався:
  - рекурсивний пошук `.csv/.json/.jsonl/.parquet` (`prepare_and_balance_data.py:89-100`);
  - автоматичне визна*чення `text` і `label` колонок (`prepare_and_balance_data.py:135-186`);
  - мапування різнорідних label values до 3-класової схеми (`prepare_and_balance_data.py:189-243`);
  - видалення порожніх/невірно розмічених рядків (`prepare_and_balance_data.py:284-287`);
  - видалення duplicate `text` (`prepare_and_balance_data.py:380-386`);
  - strict undersampling balancing (`prepare_and_balance_data.py:313-330`).
- Provenance для `balanced_dataset.csv` фіксується у `model_fine_tuning/balanced_sentiment_dataset/dataset_manifest.json`, який формується скриптом `model_fine_tuning/prepare_and_balance_data.py` і містить перелік source files, row counts до/після нормалізації, спосіб мапінгу label, class distribution, seed та параметри експорту.*

### 3.4. Конкретизація функціонування системи

#### Діаграма компонентів (текстовий опис)

1. **Presentation layer**
   - `templates/*.html` — HTML/Jinja-сторінки;
   - `static/assets/js/*.js` — логіка сторінок і кастомний SVG rendering;
   - `static/assets/css/*.css` — стилі.
2. **Web application layer**
   - `app.py` — Flask entrypoint, auth, orchestration, routes, rate limiting, background jobs;
   - `env_config.py` — зчитування `.env` і нормалізація конфігурації.
3. **Data acquisition layer**
   - `static/backend/extract_data.py` — Selenium scraping Instagram;
   - `static/backend/load_to_db.py` — пакетне завантаження сирих коментарів у SQL Server.
4. **Persistence / security layer**
   - `static/backend/db_connection.py` — ODBC connection, SQL query builders, DPAPI encryption, HMAC signing cookies;
   - `ddl/*.sql` — DDL для `Users`, `Comments`, `EnrichedComments`.
5. **NLP / analytics layer**
   - `static/backend/enrich_comments.py` — language detection + sentiment inference + upsert;
   - `static/backend/explorer_analysis.py` — агрегування rows у KPI, breakdowns та charts.
6. **Model training layer**
   - `model_fine_tuning/*.py` — підготовка датасетів, LoRA fine-tuning, локальні dataset download helpers.
7. **Quality assurance layer**
   - `tests/` — route tests, unit tests, smoke tests;
   - `run_tests.py` — test runner.

#### Потік даних (від вводу URL до відображення графіків)

`/extractor` form -> `/process-data` -> `extract_data(...)` -> `prepare_rows_from_comment_records(...)` -> `load_row_batches(...)` -> `Comments` -> `/enrich-comments` -> `detect_main_language(...)` + `analyze_sentiment_batch(...)` -> `EnrichedComments` -> `/page-analysis` або `/api/advanced-analysis/*` -> `build_analysis_from_rows(...)` -> JSON -> `explorer-page.js` / `advanced-analysis-page.js` -> SVG charts.

#### Структура бази даних

**Таблиця `Users`** (`ddl/Users.sql:1-28`)

- `UserID int identity` — PK
- `Username nvarchar(50)` — unique
- `PasswordHash nvarchar(512)`
- `Email nvarchar(100)` — unique
- `EmailVerified bit`
- `EmailVerifiedAt datetime2(0)`
- `InstagramLoginEncrypted varbinary(max)`
- `InstagramPasswordEncrypted varbinary(max)`
- `InstagramCookiesEncrypted varbinary(max)`
- `InstagramCookiesSignature varbinary(64)`
- `InstagramCookiesUpdatedAt datetime2(0)`
- `CreatedAt datetime2(0)`
- `PasswordChangedAt datetime2(0)`

**Таблиця `Comments`** (`ddl/Comments.sql:1-38`)

- `CommentHash char(64)` — PK
- `PageName nvarchar(100)`
- `PageID nvarchar(100)`
- `PostHref nvarchar(2048)`
- `PostTime datetime2(0)`
- `Comment nvarchar(max)`
- `CommentTime datetime2(0)`
- `CommentLikes int`
- `LoadTime datetime2(0)`

**Таблиця `EnrichedComments`** (`ddl/EnrichedComments.sql:1-71`)

- `CommentHash char(64)` — PK + FK на `Comments.CommentHash`
- `PageName nvarchar(100)`
- `PageID nvarchar(100)`
- `PostHref nvarchar(2048)`
- `PostTime datetime2(0)`
- `CommentTime datetime2(0)`
- `CommentOrder int`
- `CommentLikes int`
- `MainLanguage nvarchar(20)` з check: `uk`, `ru`, `en`, `symbols_only`, `other`
- `NormalizedComment nvarchar(max)`
- `Sentiment nvarchar(20)` з check: `positive`, `neutral`, `negative`
- `ProcessedTime datetime2(0)`
- `Source nvarchar(50)`

#### ER-діаграма (текстовий опис)

- `Users` — окрема сутність для автентифікації та захищеного зберігання Instagram credentials/cookies.
- `Comments` — центральне сховище сирих коментарів.
- `EnrichedComments` — one-to-one розширення `Comments` за ключем `CommentHash`.
- `Comments (1) -> (0..1) EnrichedComments`.
- `Users` не має зовнішнього ключа до `Comments` або `EnrichedComments`.

---






































## 4. РОЗДІЛ 3: МЕТОДИ ТА ПРОГРАМНІ ЗАСОБИ (10–15% ≈ 7–13 стор.)

``### 4.1. Обґрунтування вибору типу задачі та методу розв'язання

**Тип задачі**

Задача є задачею класифікації тексту на 3 класи тональності: `negative`, `neutral`, `positive`. Це безпосередньо видно з `Sentiment` check constraint у `ddl/EnrichedComments.sql:21-22`, `LABEL_MAP` у `static/backend/enrich_comments.py:47-54` та `ID2LABEL` / `LABEL2ID` у `model_fine_tuning/train_lora_sentiment.py:54-59`.

**Конкретна модель**

- базова модель: `cardiffnlp/twitter-xlm-roberta-base-sentiment` (`model_fine_tuning/train_lora_sentiment.py:44`, `static/backend/enrich_comments.py:24`);
- архітектура: transformer-based multilingual sequence classifier на основі XLM-RoBERTa;
- джерело: Hugging Face model hub, завантаження через `AutoModelForSequenceClassification` та `AutoTokenizer` (`model_fine_tuning/train_lora_sentiment.py:314-376`, `static/backend/enrich_comments.py:111-123`).

**Чому обрана саме ця модель**

- модель already multilingual, що узгоджується з підтримкою `uk/ru/en` у production pipeline;
- модель орієнтована на короткі соціально-медійні тексти;
- донавчання реалізоване через LoRA, тобто без повного retrain усіх ваг, що зменшує вимоги до пам’яті (`model_fine_tuning/train_lora_sentiment.py:363-375`);
- production inference використовує вже злиту base+adapter модель і batched processing (`static/backend/enrich_comments.py:124-139`, `142-160`).

Порівняння з альтернативами у репозиторії відсутнє. [TODO: додати теоретичне порівняння в текст розділу]

**Підхід до fine-tuning**

- вхідний датасет: `model_fine_tuning/balanced_sentiment_dataset/balanced_dataset.csv` (`model_fine_tuning/train_lora_sentiment.py:47`)
- split: `90% train / 10% validation` (`model_fine_tuning/train_lora_sentiment.py:286-294`)
- нормалізація соціального тексту: заміна URL та згадок (`model_fine_tuning/train_lora_sentiment.py:259-268`, `298-303`)
- `max_length=128` (`model_fine_tuning/train_lora_sentiment.py:51`, `330-337`)
- `num_train_epochs=3.0` (`model_fine_tuning/train_lora_sentiment.py:108`)
- `learning_rate=2e-4` (`model_fine_tuning/train_lora_sentiment.py:109`)
- `weight_decay=0.01` (`model_fine_tuning/train_lora_sentiment.py:110`)
- `per_device_train_batch_size=8` (`model_fine_tuning/train_lora_sentiment.py:111-116`)
- `per_device_eval_batch_size=8` (`model_fine_tuning/train_lora_sentiment.py:117-122`)
- `gradient_accumulation_steps=4` (`model_fine_tuning/train_lora_sentiment.py:123-128`)
- `warmup_ratio=0.05` (`model_fine_tuning/train_lora_sentiment.py:134`)
- `load_best_model_at_end=True`, `metric_for_best_model="f1_macro"` (`model_fine_tuning/train_lora_sentiment.py:414-417`)
- LoRA configuration: `r=16`, `lora_alpha=32`, `lora_dropout=0.1`, `target_modules=["query","value"]`, `modules_to_save=["classifier"]` (`model_fine_tuning/train_lora_sentiment.py:363-372`)

**Optimizer**

У коді optimizer явно не перевизначений, тому в `transformers==5.4.0` використовується стандартний optimizer `adamw_torch`, тобто `torch.optim.AdamW`. Базові параметри optimizer беруться з дефолтів `TrainingArguments`: `beta1=0.9`, `beta2=0.999`, `epsilon=1e-8`; параметр `weight_decay` у проекті явно встановлено як `0.01`.

**Метод визначення мови**

- бібліотека: `lingua-language-detector` (`static/backend/enrich_comments.py:11`)
- функції: `get_language_detector()`, `_detect_with_lingua()`, `detect_main_language()` (`static/backend/enrich_comments.py:75-103`)
- вихідні класи: `uk`, `ru`, `en`, `other`, `symbols_only`
``
### 4.2. Вибір та обґрунтування засобів розв'язання задачі

| Категорія | Засіб | Версія | Підтвердження | Примітка |
|---|---|---|---|---|
| Мова програмування | Python | `3.12` | `.idea/misc.xml:1-6`, `__pycache__/...cpython-312.pyc` | проектний SDK у PyCharm |
| Веб-фреймворк | Flask | `3.1.1` | `requirements.txt:1`, `app.py:18-19` | production app |
| CORS | `flask-cors` | `5.0.0` | `requirements.txt:2`, `app.py:42`, `89-93` | trusted origins |
| JWT auth | `flask-jwt-extended` | `4.7.1` | `app.py:43-47`, `requirements.txt:3` | auth через cookies |
| Password hashing | `werkzeug` | `3.1.3` | `requirements.txt:4`, `app.py:48`, `103-132` | `generate_password_hash(..., method="scrypt")` |
| БД | SQL Server + `pyodbc` | `pyodbc 5.2.0` | `requirements.txt:5`, `static/backend/db_connection.py:1-184` | не SQLite / не PostgreSQL |
| Data collection | Selenium | `4.31.0` | `requirements.txt:6`, `static/backend/extract_data.py:110-1065` | Instagram web scraping |
| Data prep | pandas | `2.2.2` | `requirements.txt:8`, `static/backend/load_to_db.py:6`, `model_fine_tuning/prepare_and_balance_data.py:30` | ETL і dataset prep |
| Language detection | `lingua-language-detector` | `2.2.0` | `requirements.txt:10`, `static/backend/enrich_comments.py:11` | multilingual language ID |
| NLP / inference | `transformers` | `5.4.0` | `requirements.txt:11`, `static/backend/enrich_comments.py:13`, `model_fine_tuning/train_lora_sentiment.py:33-40` | tokenizer + model + pipeline |
| PEFT / LoRA | `peft` | `0.18.1` | `requirements.txt:15`, `static/backend/enrich_comments.py:12`, `model_fine_tuning/sentiment_lora_adapters/adapter_config.json` | adapter loading / merging |
| HF datasets | `datasets` | `4.4.1` | `requirements.txt:16`, `model_fine_tuning/train_lora_sentiment.py:30`, `model_fine_tuning/*/download_dataset.py` | dataset loading / split |
| Numerical backend | `numpy` | `2.0.1` | `requirements.txt:17`, `model_fine_tuning/train_lora_sentiment.py:28`, `model_fine_tuning/evaluate_sentiment_models.py:26` | tensor/logit postprocessing |
| DL backend | `torch` | `2.5.1+cu121` у локальному середовищі, `2.5.1` у `requirements.txt` | `requirements.txt:18`, `model_fine_tuning/train_lora_sentiment.py:29`, `static/backend/enrich_comments.py:136` | training + inference backend |
| ML metrics | `scikit-learn` | `1.5.2` | `requirements.txt:19`, `model_fine_tuning/train_lora_sentiment.py:32`, `model_fine_tuning/evaluate_sentiment_models.py:29` | metrics / evaluation |
| Trainer runtime | `accelerate` | `1.13.0` | `requirements.txt:20`, використовується `transformers.Trainer` під час fine-tuning | runtime dependency для training |
| Frontend templating | Jinja2 (через Flask) | transitively via Flask | `templates/*.html`, `app.py:18` | server-rendered pages |
| Frontend layout | HTML5 UP Forty | n/a | `templates/index.html:2-5`, `LICENSE.txt` | theme base |
| Frontend JS | custom SVG + vanilla JS + jQuery | `jQuery 3.6.0`, `jquery.scrollex 0.2.1`, `jquery.scrolly 1.0.0-dev` | `static/assets/js/jquery.min.js:1`, `jquery.scrollex.min.js:1`, `jquery.scrolly.min.js:1`, `explorer-page.js`, `advanced-analysis-page.js`, `extractor.js` | без Chart.js/Plotly |
| Background jobs | `ThreadPoolExecutor` | stdlib | `static/backend/job_queue.py:1-62` | process-local queue |


**Конфігураційні особливості середовища**

- `env_config.py` реалізує власне зчитування `.env`, булевих, цілочисельних і list-параметрів (`env_config.py:8-97`);
- Flask app працює в режимах `development / production / staging / test` (`env_config.py:50-63`);
- cookies policy (`Lax/Strict/None`) нормалізується окремою функцією (`env_config.py:66-77`).

---

## 5. РОЗДІЛ 4: ПРАКТИЧНА РЕАЛІЗАЦІЯ (10–15% ≈ 7–13 стор.)

### 5.1. Опис створеного програмного засобу

#### Структура проекту

| Шлях | Призначення |
|---|---|
| `app.py` | Flask entrypoint, маршрути, auth, orchestration |
| `env_config.py` | зчитування `.env` і типізована конфігурація |
| `ddl/` | SQL Server DDL для трьох основних таблиць |
| `static/backend/` | backend-модулі Python для ETL, analytics та auth JS |
| `static/assets/` | CSS, JS, зображення, тема HTML5 UP |
| `templates/` | HTML/Jinja сторінки інтерфейсу |
| `model_fine_tuning/` | dataset prep, download helpers, LoRA training, adapters |
| `tests/` | unit, route, smoke tests |
| `run_tests.py` | запуск усієї test suite |
| `README.md` | технічний опис проекту |
| `PROJECT_STRUCTURE.md` | окремий опис структури |

#### Веб-інтерфейс (сторінки)

**1. Головна сторінка (`/`)**

- Шаблон: `templates/index.html`
- Показує hero-секцію, плитки навігації на `Extractor`, `Explorer`, `Advanced Analysis`, `FAQ`, `Sign Up`, `Log In` (`templates/index.html:43-118`)
- Призначення: точка входу в систему та навігація за сценаріями (`templates/index.html:121-133`)

**2. Extractor (`/extractor`)**

- Шаблон: `templates/extractor.html`
- Функціонал:
  - введення `instagram_page` і `number_of_posts` (`templates/extractor.html:79-83`);
  - запуск visible extraction (`templates/extractor.html:89`);
  - запуск headless extraction з уже збереженою сесією (`templates/extractor.html:96-100`);
  - відображення підказки для ручного логіну (`templates/extractor.html:90-95`);
  - вибір режиму enrichment: `page_name`, `page_id`, `whole_db`, `delta` (`templates/extractor.html:117-145`).

**3. Explorer (`/explorer`)**

- Шаблон: `templates/explorer.html`
- Функціонал:
  - вибір сторінки за `PageName` або `PageID` (`templates/explorer.html:74-101`);
  - завантаження page-level analysis з `EnrichedComments` (`templates/explorer.html:122-129`);
  - перегляд KPI, таблиць, прикладів коментарів і chart gallery через JS (`static/assets/js/explorer-page.js:671-756`).

**4. Advanced Analysis (`/advanced-analysis`)**

- Шаблон: `templates/advanced_analysis.html`
- Функціонал:
  - комбіновані фільтри за `page_name`, `page_id`, `source`, `language`, `sentiment`, `first_comment_sentiment`, `min_likes`, `post_time`, `comment_time`, `text_search` (`templates/advanced_analysis.html:86-194`);
  - preview matching rows (`templates/advanced_analysis.html:251-277`);
  - filtered charts (`templates/advanced_analysis.html:281-289`).

**5. FAQ (`/faq`)**

- Шаблон: `templates/faq.html`
- Показує опис сторінок, схеми колонок, pipeline steps, implementation notes і advanced filters (`templates/faq.html:67-157`)
- Дані наповнюються з `static/backend/faq_content.py:1-191`

**6. Sign Up / Log In / Account**

- `templates/signup.html` — реєстрація з полями username, email, app password, Instagram login/password (`templates/signup.html:16-34`)
- `templates/login.html` — логін за username/password (`templates/login.html:13-29`)
- `templates/account.html` — профіль, статистика, зміна пароля, верифікація email, оновлення Instagram credentials, очистка cookies (`templates/account.html:44-131`)

**7. Допоміжні сторінки**

- `templates/elements.html` — theme reference page
- `templates/test.html` — utility/test page

#### Маршрути Flask (routes)

| Route | Methods | Function | Access | Опис | Рядки |
|---|---|---|---|---|---|
| `/jobs/<job_id>` | GET | `job_status` | auth | статус background job | `app.py:231-237` |
| `/static/<path:filename>` | GET | `static_proxy` | public | видача статичних файлів | `app.py:339-341` |
| `/refresh` | POST | `refresh` | refresh cookie | оновлення access token | `app.py:351-358` |
| `/login` | GET, POST | `login` | public | рендер сторінки логіну / логін користувача | `app.py:361-406` |
| `/logout` | POST | `logout` | auth | очистка JWT cookies | `app.py:409-414` |
| `/user-info` | GET | `user_info` | optional auth | повертає user identity | `app.py:417-424` |
| `/` | GET | `index` | public | landing page | `app.py:427-429` |
| `/elements` | GET | `elements` | auth | theme reference | `app.py:432-437` |
| `/extractor` | GET | `extractor` | auth | extractor page | `app.py:440-445` |
| `/api/extractor/page-dimensions` | GET | `extractor_page_dimensions` | auth | distinct page names/ids з `Comments` | `app.py:448-455` |
| `/account` | GET | `account` | auth | account page | `app.py:458-463` |
| `/api/account` | GET | `account_details` | auth | profile + статистика | `app.py:466-479` |
| `/api/account/manual-login-hint` | GET | `account_manual_login_hint` | auth | маскована підказка для ручного Instagram login | `app.py:482-497` |
| `/api/account/change-password` | POST | `account_change_password` | auth | зміна app password | `app.py:500-516` |
| `/api/account/verify-email` | POST | `account_verify_email` | auth | локальна верифікація email flag | `app.py:519-531` |
| `/api/account/instagram-cookies/clear` | POST | `account_clear_instagram_cookies` | auth | очистка збережених cookies | `app.py:534-539` |
| `/api/account/instagram-credentials` | POST | `account_update_instagram_credentials` | auth | зберегти нові Instagram creds | `app.py:542-553` |
| `/api/account/instagram-credentials` | DELETE | `account_delete_instagram_credentials` | auth | видалити Instagram creds і cookies | `app.py:556-561` |
| `/submit-form` | POST | `submit_form` | auth | тестовий/заглушковий submit endpoint | `app.py:564-570` |
| `/explorer` | GET | `explorer` | auth | explorer page | `app.py:573-592` |
| `/advanced-analysis` | GET | `advanced_analysis` | auth | advanced analysis page | `app.py:595-620` |
| `/api/advanced-analysis/preview` | POST | `advanced_analysis_preview` | auth | row preview + analysis | `app.py:623-648` |
| `/api/advanced-analysis/analyze` | POST | `advanced_analysis_analyze` | auth | filtered charts only | `app.py:651-674` |
| `/faq` | GET | `faq` | auth | FAQ page | `app.py:677-687` |
| `/test` | GET | `test` | public | test page | `app.py:690-692` |
| `/signup` | GET, POST | `signup` | public | signup form / user creation | `app.py:695-714` |
| `/process-data` | POST | `process_data_endpoint` | auth | запуск extraction + load to DB | `app.py:717-761` |
| `/enrich-comments` | POST | `enrich_comments_endpoint` | auth | запуск enrichment | `app.py:764-788` |
| `/page-analysis` | POST | `page_analysis_endpoint` | auth | page-level analysis | `app.py:791-816` |

**Оновлення:** посилання відновлення пароля було прибрано з `templates/login.html`; замість нього використовується перехід на сторінку реєстрації `/signup`.

#### Основні функції / класи

| Модуль | Функція / клас | Призначення | Рядки |
|---|---|---|---|
| `app.py` | `hash_user_password` | хешування app password через `scrypt` | `103-104` |
| `app.py` | `verify_user_password` | перевірка `scrypt` і upgrade legacy SHA-256 | `111-121` |
| `app.py` | `limit_requests` | decorator для rate limiting | `198-221` |
| `app.py` | `_run_process_data` | orchestration extraction workflow | `240-320` |
| `app.py` | `_run_enrich_comments` | orchestration enrichment workflow | `323-336` |
| `static/backend/extract_data.py` | `extract_data` | повний scraping pipeline | `901-1065` |
| `static/backend/extract_data.py` | `load_all_posts` | завантаження href постів | `847-899` |
| `static/backend/extract_data.py` | `collect_comments_and_likes` | парсинг текстів, часу й лайків коментарів | `512-647` |
| `static/backend/load_to_db.py` | `compute_comment_hash` | SHA-256 ключ для дедуплікації | `40-47` |
| `static/backend/load_to_db.py` | `insert_rows` | MERGE у `Comments` через temp table | `110-216` |
| `static/backend/load_to_db.py` | `load_row_batches` | пакетна обробка batches/chunks | `233-266` |
| `static/backend/enrich_comments.py` | `detect_main_language` | визначення основної мови | `89-103` |
| `static/backend/enrich_comments.py` | `load_models` | завантаження tokenizer + base model + PEFT adapters | `106-140` |
| `static/backend/enrich_comments.py` | `analyze_sentiment_batch` | пакетний sentiment inference | `142-160` |
| `static/backend/enrich_comments.py` | `prepare_enriched_rows` | побудова enriched rows | `300-342` |
| `static/backend/enrich_comments.py` | `upsert_enriched_rows` | MERGE у `EnrichedComments` | `345-523` |
| `static/backend/enrich_comments.py` | `enrich_comments` | керування режимами `whole_db/page_id/page_name/delta` | `525-568` |
| `static/backend/explorer_analysis.py` | `build_analysis_from_rows` | summary, breakdowns, charts | `188-554` |
| `static/backend/db_connection.py` | `protect_secret` / `unprotect_secret` | DPAPI encryption/decryption | `194-247` |
| `static/backend/db_connection.py` | `fetch_enriched_comment_rows` | фільтрований select з `EnrichedComments` | `789-852` |
| `static/backend/db_connection.py` | `fetch_post_anchor_sentiments` | визначення sentiment першого коментаря поста | `903-975` |
| `static/backend/job_queue.py` | `InMemoryJobQueue` | process-local background jobs | `7-62` |
| `model_fine_tuning/train_lora_sentiment.py` | `build_model` | побудова LoRA model | `350-376` |
| `model_fine_tuning/train_lora_sentiment.py` | `compute_metrics` | `accuracy` + `f1_macro` | `379-388` |
| `model_fine_tuning/prepare_and_balance_data.py` | `standardize_dataframe` | стандартизація довільних датасетів до `text,label` | `246-299` |

#### Структура БД

Таблиці та поля наведені у підрозділі 3.4. Додатково:

- `Comments` має індекси `IX_Comments_PageName`, `IX_Comments_PageID_PostHref`, `IX_Comments_PageID_PostTime_CommentTime` (`ddl/Comments.sql:18-37`);
- `EnrichedComments` має індекси для page-level window, post anchor та source-language-sentiment filters (`ddl/EnrichedComments.sql:26-70`).

### 5.2. Графіки та візуалізації

У проекті реально генеруються 12 графіків. Дані для них формуються в `static/backend/explorer_analysis.py:473-526`, а рендеряться у `static/assets/js/explorer-page.js:531-656` та `static/assets/js/advanced-analysis-page.js:576-727`.

| Ключ графіка | Тип | Що відображає | Для яких мов | Де формується |
|---|---|---|---|---|
| `comments_by_post` | bar chart | кількість коментарів по постах | усі | `explorer_analysis.py:473-477` |
| `comments_by_language` | bar chart | кількість коментарів по мовах | `uk`, `ru`, `en`, `other`, `symbols_only` | `explorer_analysis.py:478-481` |
| `sentiment_by_language` | stacked bar chart | розподіл `positive/neutral/negative` по мовах | ті самі, що доступні в subset | `explorer_analysis.py:482-490` |
| `sentiment_by_post` | stacked bar chart | розподіл тональності по постах | language-agnostic | `explorer_analysis.py:491-503` |
| `comment_length_histogram` | histogram / bar chart | розподіл довжини нормалізованих коментарів | language-agnostic | `explorer_analysis.py:504-507` |
| `avg_length_by_sentiment` | bar chart | середня довжина коментаря для кожного sentiment | language-agnostic | `explorer_analysis.py:508-511` |
| `avg_length_by_language_sentiment` | grouped bar chart | середня довжина для пар `мова x sentiment` | топові мови, крім `other` | `explorer_analysis.py:512-520` |
| `solidarity_distribution_by_language` | bar chart | середній рівень збігу з anchor sentiment по мовах | мови, крім `other` | `explorer_analysis.py:521` |
| `positivity_trend_overall` | line chart | динаміка частки позитивних коментарів по постах | language-agnostic | `explorer_analysis.py:522` |
| `positivity_trend_by_language` | multi-line chart | динаміка positivity для топ-3 мов | топ-3 мови за кількістю, без `other` | `explorer_analysis.py:418-441`, `523` |
| `solidarity_trend_overall` | line chart | динаміка solidarity score по постах | language-agnostic | `explorer_analysis.py:410-416`, `524` |
| `solidarity_trend_by_language` | multi-line chart | динаміка solidarity для топ-3 мов | топ-3 мови за кількістю, без `other` | `explorer_analysis.py:443-460`, `525` |

**Додаткові візуальні елементи, які не є графіками**

- KPI cards: `Total comments`, `Distinct posts`, `Positive share`, `Avg length` (`static/assets/js/explorer-page.js:671-690`)
- таблиці `Language and sentiment mix`, `Top 5 posts by solidarity`, `Post breakdown`, `Sample comments` (`static/assets/js/explorer-page.js:695-756`)
- row preview table в Advanced Analysis (`templates/advanced_analysis.html:251-277`)

### 5.3. Аналіз контрольного прикладу

1. Користувач відкриває `/signup`, вводить `username`, `email`, `password`, `instagram_login`, `instagram_password` (`templates/signup.html:16-34`), а маршрут `signup()` хешує пароль через `scrypt` і викликає `insert_new_user(...)` (`app.py:700-713`, `static/backend/db_connection.py:250-280`).
2. Після входу через `/login` маршрут `login()` перевіряє пароль, оновлює legacy hash за потреби і встановлює JWT access/refresh cookies (`app.py:361-406`).
3. На сторінці `/extractor` користувач вводить сторінку та кількість постів (`templates/extractor.html:79-82`), а JS надсилає POST на `/process-data` (`static/assets/js/extractor.js:281-328`).
4. `/process-data` перевіряє параметри, дістає Instagram credentials, знаходить already-loaded `PostHref` і викликає `extract_data(...)` (`app.py:726-758`, `static/backend/db_connection.py:572-593`).
5. `extract_data(...)` запускає Selenium, підвантажує cookies або чекає ручного логіну, знаходить до `N` нових постів, збирає коментарі та лайки (`static/backend/extract_data.py:901-1065`).
6. Кожен зібраний batch перетворюється на rows з `CommentHash` і записується у `Comments` через `MERGE` (`static/backend/load_to_db.py:77-107`, `110-216`).
7. Користувач запускає `/enrich-comments`; `enrich_comments(...)` читає сирі rows, визначає `MainLanguage`, будує `NormalizedComment`, запускає batched transformer inference і записує `Sentiment` у `EnrichedComments` (`static/backend/enrich_comments.py:300-568`).
8. На сторінці `/explorer` користувач обирає сторінку за `PageName` або `PageID`; JS викликає `/page-analysis`, а сервер повертає summary + tables + charts (`app.py:791-816`, `static/backend/explorer_analysis.py:188-554`).
9. За потреби користувач відкриває `/advanced-analysis` і робить поглиблені фільтри по `EnrichedComments` (`app.py:623-674`).

### 5.4. Оцінка ефективності моделей

**Метрики, знайдені у коді**

- `accuracy`
- `f1_macro`
- `eval_loss`
- `eval_runtime`
- `eval_samples_per_second`
- `eval_steps_per_second`

**Фактичні результати на validation split**

За `model_fine_tuning/sentiment_lora_adapters/trainer_artifacts/checkpoint-4995/trainer_state.json`:

- `eval_accuracy = 0.7976009461057612`
- `eval_f1_macro = 0.7969292129967626`
- `eval_loss = 0.48382923007011414`
- `eval_runtime = 11.6007 s`
- `eval_samples_per_second = 510.227`
- `eval_steps_per_second = 63.789`
- `num_train_epochs = 3`
- `global_step = 4995`

За checkpoint після 2-ї епохи (`checkpoint-3330`):

- `eval_accuracy = 0.7938841020442642`
- `eval_f1_macro = 0.7916319786518186`

Різниця між 2-ю та 3-ю епохою:

- приріст accuracy: `+0.0037168441`
- приріст F1-macro: `+0.0052972343`

**Порівняння до/після fine-tuning**

У коді передбачено логування baseline metrics до fine-tuning і fine-tuned metrics після навчання (`model_fine_tuning/train_lora_sentiment.py:446-491`), але baseline values у репозиторії не збережені окремим файлом. Тому:

- до/після fine-tuning логічно підтримано кодом;
- 
**Час обробки одного коментаря**

Окремого production benchmark для одного Instagram-коментаря в коді не знайдено. Проте з `eval_samples_per_second = 510.227` можна зробити обережний висновок, що на validation benchmark модель обробляла приблизно `1 / 510.227 ≈ 0.00196 с` на один текст. Це інференція з логів тренування, а не прямий вимір у Flask pipeline.

**Обмеження та відомі проблеми**

- precision / recall / confusion matrix / ROC-AUC тепер доступні через `model_fine_tuning/evaluate_sentiment_models.py`, але збережений evaluation artifact ще потрібно сформувати й закомітити окремо;
- офіційний API Instagram не використовується, тому scraping чутливий до `challenge/checkpoint` (`static/backend/extract_data.py:256-270`);
- `headless` режим працює лише за наявності збереженої валідної сесії (`static/backend/extract_data.py:967-981`);
- підтримка явних мов обмежена `uk`, `ru`, `en`, решта переходить у `other` (`static/backend/enrich_comments.py:22-33`);
- перший коментар поста використовується як anchor sentiment; для нього `CommentLikes` примусово ставиться в `0` (`static/backend/enrich_comments.py:325-327`);
- `requirements.txt` неповний щодо реально імпортованих ML-залежностей;
- `model_fine_tuning/symbols/generation.py` містить проблеми кодування рядків;
- production snapshot БД у репозиторії відсутній, тому немає реальних statistics по кількості сторінок/коментарів у deployed system.

---

## 6. ВИСНОВКИ (2–3 сторінки)

1. Аналіз репозиторію показав, що для задачі sentiment analysis коментарів Instagram доцільно використовувати не лише загальні NLP-інструменти, а повний прикладний pipeline: автентифікацію користувача, захищене зберігання облікових даних, збір коментарів, enrichment і візуалізацію.
2. У межах роботи реалізовано веб-систему `Comment Lab` на Flask, що поєднує Selenium scraping Instagram, SQL Server-сховище, модуль визначення мови, донавчену transformer-модель sentiment analysis та два рівні аналітичного інтерфейсу: Explorer і Advanced Analysis.
3. Для збереження сирих даних використовується таблиця `Comments`, а для збагачених — `EnrichedComments`; зв’язок між ними реалізовано через `CommentHash`, що забезпечує дедуплікацію та стабільний upsert.
4. У проекті підготовлено кілька зовнішніх датасетів і сформовано власний збалансований fine-tuning dataset на `59184` записів, після чого виконано LoRA fine-tuning моделі `cardiffnlp/twitter-xlm-roberta-base-sentiment`.
5. За збереженими training artifacts fine-tuned checkpoint досяг `eval_accuracy=0.7976` і `eval_f1_macro=0.7969`, що підтверджує працездатність обраного підходу для 3-класової класифікації тональності.
6. Практична цінність рішення полягає у можливості локально збирати та аналізувати Instagram-коментарі, відфільтровувати їх за мовою, тональністю, часом, лайками та текстовими шаблонами, а також переглядати результати у вигляді графіків і таблиць.
7. Подальший розвиток системи доцільно спрямувати на: розширення мовної підтримки, додавання versioned evaluation artifacts, подальше покращення dataset provenance і контролю версій датасетів, перехід до асинхронних/розподілених job queues та усунення dependency/config drift у репозиторії.

---

## 7. ТЕХНІЧНИЙ ІНВЕНТАР ПРОЕКТУ

### 7.1. Повне дерево файлів проекту

```text
Folder PATH listing
Volume serial number is 7012-1F02
C:.
|   .env
|   .env.example
|   .gitignore
|   app.py
|   env_config.py
|   LICENSE.txt
|   PROJECT_STRUCTURE.md
|   README.md
|   requirements.txt
|   run_tests.py
|   
+---.idea
|   |   .gitignore
|   |   dataSources.local.xml
|   |   dataSources.xml
|   |   data_source_mapping.xml
|   |   db-forest-config.xml
|   |   misc.xml
|   |   modules.xml
|   |   pythonProject1.iml
|   |   sqldialects.xml
|   |   vcs.xml
|   |   workspace.xml
|   |   
|   +---dataSources
|   |   |   112b2d03-402f-423e-9431-90c5f53b1a2b.xml
|   |   |   ded23e7a-d5e3-4ea1-b8aa-37071c261af0.xml
|   |   |   
|   |   +---112b2d03-402f-423e-9431-90c5f53b1a2b
|   |   |   \---storage_v2
|   |   |       \---_src_
|   |   |           \---database
|   |   |               |   master.YiqNvw.meta
|   |   |               |   social-media-optimizer.LGzbdw.meta
|   |   |               |   
|   |   |               +---master.YiqNvw
|   |   |               |   \---schema
|   |   |               |           INFORMATION_SCHEMA.NBgcMw.meta
|   |   |               |           sys.zb4BAA.meta
|   |   |               |           
|   |   |               \---social-media-optimizer.LGzbdw
|   |   |                   \---schema
|   |   |                           INFORMATION_SCHEMA.NBgcMw.meta
|   |   |                           sys.zb4BAA.meta
|   |   |                           
|   |   \---ded23e7a-d5e3-4ea1-b8aa-37071c261af0
|   |       \---storage_v2
|   |           \---_src_
|   |               \---database
|   |                   |   master.YiqNvw.meta
|   |                   |   
|   |                   \---master.YiqNvw
|   |                       \---schema
|   |                               INFORMATION_SCHEMA.NBgcMw.meta
|   |                               sys.zb4BAA.meta
|   |                               
|   \---inspectionProfiles
|           profiles_settings.xml
|           Project_Default.xml
|           
+---ddl
|       Comments.sql
|       EnrichedComments.sql
|       Users.sql
|       
+---model_fine_tuning
|   |   common.py
|   |   prepare_and_balance_data.py
|   |   train_lora_sentiment.py
|   |   
|   +---balanced_sentiment_dataset
|   |       balanced_dataset.csv
|   |       
|   +---sentiment_lora_adapters
|   |   |   adapter_config.json
|   |   |   adapter_model.safetensors
|   |   |   README.md
|   |   |   tokenizer.json
|   |   |   tokenizer_config.json
|   |   |   
|   |   \---trainer_artifacts
|   |       +---checkpoint-3330
|   |       |       adapter_config.json
|   |       |       adapter_model.safetensors
|   |       |       optimizer.pt
|   |       |       README.md
|   |       |       rng_state.pth
|   |       |       scaler.pt
|   |       |       scheduler.pt
|   |       |       tokenizer.json
|   |       |       tokenizer_config.json
|   |       |       trainer_state.json
|   |       |       training_args.bin
|   |       |       
|   |       \---checkpoint-4995
|   |               adapter_config.json
|   |               adapter_model.safetensors
|   |               optimizer.pt
|   |               README.md
|   |               rng_state.pth
|   |               scaler.pt
|   |               scheduler.pt
|   |               tokenizer.json
|   |               tokenizer_config.json
|   |               trainer_state.json
|   |               training_args.bin
|   |               
|   +---sismetanin-rusentitweet-blob-main-rusentitweet-full
|   |       rusentitweet_full.csv
|   |       
|   +---Sp1786-multiclass-sentiment-analysis-dataset
|   |   |   download_dataset.py
|   |   |   
|   |   +---hf_saved_dataset
|   |   |       full_dataset.csv
|   |   |       
|   |   \---__pycache__
|   |           download_dataset.cpython-312.pyc
|   |           
|   +---symbols
|   |   |   generation.py
|   |   |   slang_data.csv
|   |   |   
|   |   \---__pycache__
|   |           generation.cpython-312.pyc
|   |           
|   +---ukr-detect-ukr-emotions-binary
|   |   |   download_dataset.py
|   |   |   
|   |   +---hf_saved_dataset
|   |   |       full_balanced_dataset.csv
|   |   |       
|   |   \---__pycache__
|   |           download_dataset.cpython-312.pyc
|   |           
|   \---__pycache__
|           common.cpython-312.pyc
|           prepare_and_balance_data.cpython-312.pyc
|           train_lora_sentiment.cpython-312.pyc
|           
+---static
|   +---assets
|   |   +---css
|   |   |       account.css
|   |   |       advanced-analysis-page.css
|   |   |       explorer-page.css
|   |   |       extractor.css
|   |   |       fontawesome-all.min.css
|   |   |       footer.css
|   |   |       generic.css
|   |   |       landing-dashboard.css
|   |   |       login.css
|   |   |       main.css
|   |   |       noscript.css
|   |   |       signup.css
|   |   |       
|   |   +---images
|   |   |       advanced_analisys_page.png
|   |   |       banner.png
|   |   |       explorer_page.png
|   |   |       extractor_image.png
|   |   |       extractor_page.png
|   |   |       FAQ_page.png
|   |   |       log_in_page.png
|   |   |       sign_up_page.png
|   |   |       
|   |   +---js
|   |   |       advanced-analysis-page.js
|   |   |       breakpoints.min.js
|   |   |       browser.min.js
|   |   |       explorer-page.js
|   |   |       extractor.js
|   |   |       jquery.min.js
|   |   |       jquery.scrollex.min.js
|   |   |       jquery.scrolly.min.js
|   |   |       main.js
|   |   |       util.js
|   |   |       
|   |   +---sass
|   |   |   |   main.scss
|   |   |   |   noscript.scss
|   |   |   |   
|   |   |   +---base
|   |   |   |       _page.scss
|   |   |   |       _reset.scss
|   |   |   |       _typography.scss
|   |   |   |       
|   |   |   +---components
|   |   |   |       _actions.scss
|   |   |   |       _box.scss
|   |   |   |       _button.scss
|   |   |   |       _contact-method.scss
|   |   |   |       _form.scss
|   |   |   |       _icon.scss
|   |   |   |       _icons.scss
|   |   |   |       _image.scss
|   |   |   |       _list.scss
|   |   |   |       _pagination.scss
|   |   |   |       _row.scss
|   |   |   |       _section.scss
|   |   |   |       _spotlights.scss
|   |   |   |       _table.scss
|   |   |   |       _tiles.scss
|   |   |   |       
|   |   |   +---layout
|   |   |   |       _banner.scss
|   |   |   |       _contact.scss
|   |   |   |       _footer.scss
|   |   |   |       _header.scss
|   |   |   |       _main.scss
|   |   |   |       _menu.scss
|   |   |   |       _wrapper.scss
|   |   |   |       
|   |   |   \---libs
|   |   |           _breakpoints.scss
|   |   |           _functions.scss
|   |   |           _html-grid.scss
|   |   |           _mixins.scss
|   |   |           _vars.scss
|   |   |           _vendor.scss
|   |   |           
|   |   \---webfonts
|   |           fa-brands-400.eot
|   |           fa-brands-400.svg
|   |           fa-brands-400.ttf
|   |           fa-brands-400.woff
|   |           fa-brands-400.woff2
|   |           fa-regular-400.eot
|   |           fa-regular-400.svg
|   |           fa-regular-400.ttf
|   |           fa-regular-400.woff
|   |           fa-regular-400.woff2
|   |           fa-solid-900.eot
|   |           fa-solid-900.svg
|   |           fa-solid-900.ttf
|   |           fa-solid-900.woff
|   |           fa-solid-900.woff2
|   |           
|   \---backend
|       |   common_utils.py
|       |   db_connection.py
|       |   enrich_comments.py
|       |   explorer_analysis.py
|       |   extract_data.py
|       |   faq_content.py
|       |   job_queue.py
|       |   load_to_db.py
|       |   
|       +---auth
|       |       account.js
|       |       faq.js
|       |       home.js
|       |       login.js
|       |       menu_auth.js
|       |       session.js
|       |       signup.js
|       |       
|       \---__pycache__
|               common_utils.cpython-312.pyc
|               db_connection.cpython-312.pyc
|               enrich_comments.cpython-312.pyc
|               explorer_analysis.cpython-312.pyc
|               extract_data.cpython-312.pyc
|               faq_content.cpython-312.pyc
|               job_queue.cpython-312.pyc
|               load_data.cpython-312.pyc
|               load_to_db.cpython-312.pyc
|               
+---templates
|       account.html
|       advanced_analysis.html
|       elements.html
|       explorer.html
|       extractor.html
|       faq.html
|       index.html
|       login.html
|       signup.html
|       test.html
|       
+---tests
|   |   __init__.py
|   |   
|   +---fixtures
|   |   |   comments_rows.py
|   |   |   csv_samples.py
|   |   |   enriched_rows.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           comments_rows.cpython-312.pyc
|   |           csv_samples.cpython-312.pyc
|   |           enriched_rows.cpython-312.pyc
|   |           __init__.cpython-312.pyc
|   |           
|   +---routes
|   |   |   test_auth_routes.py
|   |   |   test_process_flow_routes.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           test_auth_routes.cpython-312.pyc
|   |           test_process_flow_routes.cpython-312.pyc
|   |           __init__.cpython-312.pyc
|   |           
|   +---smoke
|   |   |   test_app_smoke.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           test_app_smoke.cpython-312.pyc
|   |           __init__.cpython-312.pyc
|   |           
|   +---support
|   |   |   app_test_case.py
|   |   |   app_test_loader.py
|   |   |   fake_db.py
|   |   |   fake_selenium.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           app_test_case.cpython-312.pyc
|   |           app_test_loader.cpython-312.pyc
|   |           fake_db.cpython-312.pyc
|   |           fake_selenium.cpython-312.pyc
|   |           __init__.cpython-312.pyc
|   |           
|   +---unit
|   |   |   test_common_utils.py
|   |   |   test_db_connection.py
|   |   |   test_enrich_comments.py
|   |   |   test_explorer_analysis.py
|   |   |   test_extract_data.py
|   |   |   test_load_to_db.py
|   |   |   test_model_fine_tuning_exports.py
|   |   |   test_model_fine_tuning_scripts.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           test_common_utils.cpython-312.pyc
|   |           test_db_connection.cpython-312.pyc
|   |           test_enrich_comments.cpython-312.pyc
|   |           test_explorer_analysis.cpython-312.pyc
|   |           test_extract_data.cpython-312.pyc
|   |           test_load_to_db.cpython-312.pyc
|   |           test_model_fine_tuning_exports.cpython-312.pyc
|   |           test_model_fine_tuning_scripts.cpython-312.pyc
|   |           __init__.cpython-312.pyc
|   |           
|   \---__pycache__
|           __init__.cpython-312.pyc
|           
\---__pycache__
        app.cpython-312.pyc
        env_config.cpython-312.pyc
        finetune_pipeline.cpython-312.pyc
```

### 7.2. Повний список залежностей

Вміст `requirements.txt`:

```text
accelerate==1.13.0
datasets==4.4.1
flask==3.1.1
flask-cors==5.0.0
flask-jwt-extended==4.7.1
lingua-language-detector==2.2.0
numpy==2.0.1
pandas==2.2.2
peft==0.18.1
pyodbc==5.2.0
scikit-learn==1.5.2
selenium==4.31.0
torch==2.5.1
transformers==5.4.0
werkzeug==3.1.3

```

### 7.3. Змінні середовища та конфігурація

#### Змінні з `.env.example`

- `JWT_SECRET_KEY`
- `APP_ENV`
- `DEBUG`
- `JWT_COOKIE_SECURE`
- `JWT_COOKIE_SAMESITE`
- `CORS_ALLOWED_ORIGINS`
- `TRUST_PROXY_HEADERS`
- `RATE_LIMIT_LOGIN_MAX_ATTEMPTS`
- `RATE_LIMIT_LOGIN_WINDOW_SECONDS`
- `RATE_LIMIT_PROCESS_DATA_MAX_ATTEMPTS`
- `RATE_LIMIT_PROCESS_DATA_WINDOW_SECONDS`
- `RATE_LIMIT_ENRICH_COMMENTS_MAX_ATTEMPTS`
- `RATE_LIMIT_ENRICH_COMMENTS_WINDOW_SECONDS`
- `RATE_LIMIT_ANALYSIS_MAX_ATTEMPTS`
- `RATE_LIMIT_ANALYSIS_WINDOW_SECONDS`
- `DB_DRIVER`
- `DB_SERVER`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `CHROMEDRIVER_PATH`
- `APP_USERNAME`
- `TARGET_PAGE`
- `NUMBER_OF_POSTS`

#### Додаткові ENV, які використовуються в коді

- `COOKIE_SIGNING_SECRET` (`static/backend/db_connection.py:60-61`, `README.md:100`)
- `DB_CONNECT_TIMEOUT_SECONDS` (`static/backend/db_connection.py:167`)
- `INFERENCE_BATCH_SIZE` (`static/backend/enrich_comments.py:27`)
- `ENRICH_DB_FETCH_BATCH_SIZE` (`static/backend/enrich_comments.py:28`)
- `INSTAGRAM_MANUAL_LOGIN_TIMEOUT_SECONDS` (`static/backend/extract_data.py:1009`)
- `ENABLE_BACKGROUND_JOBS` (`app.py:80`, `README.md:31`)
- `INPUT_FOLDER` (`static/backend/load_to_db.py:319-323`)

#### Внутрішні runtime overrides

- `HF_HUB_DISABLE_SYMLINKS_WARNING=1` (`app.py:10`)
- `TF_ENABLE_ONEDNN_OPTS=0` (`app.py:11`)
- `TF_CPP_MIN_LOG_LEVEL=2` (`app.py:12`)
- `TRANSFORMERS_NO_TF=1` (`static/backend/enrich_comments.py:37`)
- `USE_TF=0` (`static/backend/enrich_comments.py:38`)
- `USE_TORCH=1` (`static/backend/enrich_comments.py:39`)

#### Конфігураційні файли

- `.env`
- `.env.example`
- `.idea/misc.xml`
- `README.md`
- `PROJECT_STRUCTURE.md`

### 7.4. Інструкція запуску

1. Підготувати Python-середовище. За локальною IDE-конфігурацією проект орієнтований на Python 3.12 (`.idea/misc.xml:4-6`).
2. Створити та активувати virtual environment.
3. Встановити залежності:
   - базово: `pip install -r requirements.txt`
4. Створити `.env` на основі `.env.example`.
5. Налаштувати SQL Server і виконати DDL:
   - `ddl/Users.sql`
   - `ddl/Comments.sql`
   - `ddl/EnrichedComments.sql`
6. Переконатися, що встановлено:
   - ODBC Driver 17 for SQL Server
   - Google Chrome
   - ChromeDriver (або в PATH, або через `CHROMEDRIVER_PATH`)
7. Запустити застосунок:
   - `python app.py`
8. Відкрити `http://localhost:5000`.
9. Для запуску тестів:
   - `python run_tests.py`

**Важлива примітка:** для локального запуску слід орієнтуватися на фактично наявні `ddl/*.sql`: `Users.sql`, `Comments.sql`, `EnrichedComments.sql`.

---

## 8. ВІДПОВІДНІСТЬ ЗАДАЧАМ DATA SCIENCE (з методички)

### Задача 1 — Збір та підготовка даних

- Які файли проекту реалізують задачу:
  - `static/backend/extract_data.py`
  - `static/backend/load_to_db.py`
  - `model_fine_tuning/prepare_and_balance_data.py`
  - `model_fine_tuning/*/download_dataset.py`
- Які джерела даних:
  - Instagram Web через Selenium scraping, а не API;
  - локально збережені зовнішні датасети у `model_fine_tuning/`.
- Як відбувається очищення даних:
  - normalization URL/mentions (`static/backend/enrich_comments.py:61-68`);
  - видалення empty/unmapped rows (`prepare_and_balance_data.py:284-287`);
  - deduplication by hash / by text (`load_to_db.py:40-47`, `prepare_and_balance_data.py:380-386`);
  - label remapping to unified 3-class scheme (`prepare_and_balance_data.py:208-243`).

### Задача 2 — EDA (Exploratory Data Analysis)

- Які файли/функції реалізують аналіз:
  - `static/backend/explorer_analysis.py:188-554`
  - `static/assets/js/explorer-page.js`
  - `static/assets/js/advanced-analysis-page.js`
- Які візуалізації створюються:
  - comments by post / language
  - sentiment by language / post
  - comment length histogram
  - average length charts
  - solidarity charts
  - positivity trends
- Які закономірності виявлені:
  - код готовий виявляти `positive_share`, `language_breakdown`, `solidarity_score`, `avg_comment_length`, `top posts by solidarity`, часові тренди;
  - фактичні емпіричні закономірності на production dataset можна розглянути безпосередньо на сайті.

### Задача 3 — Моделювання та ML

- Яка модель використовується:
  - `cardiffnlp/twitter-xlm-roberta-base-sentiment` + LoRA adapters
- Як відбувається тренування/fine-tuning:
  - balanced multilingual dataset
  - 3 epochs
  - LR `2e-4`
  - batch `8`
  - grad accumulation `4`
  - optimization через стандартний `Trainer`
- Архітектура моделі:
  - transformer sequence classification
  - 3 output labels
  - LoRA на `query/value`

### Задача 4 — Інтерпретація результатів

- Як результати подаються користувачу:
  - Explorer page
  - Advanced Analysis page
  - KPI cards
  - preview rows
  - tabular breakdowns
- Дашборди та графіки:
  - 12 chart types, згенеровані в `explorer_analysis.py`
- Бізнес-цінність:
  - оцінка реакції аудиторії
  - виявлення негативу
  - пошук мовних і часових патернів
  - виявлення engagement-heavy коментарів через `min_likes`

### Задача 5 — Інтеграція у продукт

- Веб-система:
  - Flask (`app.py`)
- Як модель інтегрована у веб-додаток:
  - через `static/backend/enrich_comments.py`, який завантажує tokenizer/model і пише результати в БД
- Сторінки та функціонал:
  - Home, Login, Sign Up, Extractor, Explorer, Advanced Analysis, FAQ, Account

### Задача 6 — Оцінка ефективності

- Метрики:
  - `accuracy`, `f1_macro`, `eval_loss`, `eval_runtime`, `eval_samples_per_second`, `eval_steps_per_second`
- Порівняння моделей:
  - окремий скрипт `model_fine_tuning/evaluate_sentiment_models.py` виконує порівняння baseline/fine-tuned на однаковому validation split і зберігає JSON report
- Можливості оптимізації:
  - додати збереження evaluation report у versioned artifacts або CI;
  - versionувати `dataset_manifest.json` разом із конкретними snapshot-ами balanced dataset;
  - винести jobs у зовнішню чергу;
  - покращити dependency management;
  - розширити мовну підтримку.

---

## 9. ВИМОГИ ДО ОФОРМЛЕННЯ (нагадування)

- Шрифт: Times New Roman 14, інтервал 1.5
- Відступи: зверху 2.0, знизу 3.0, зліва 2.0, справа 1.0
- Перший рядок абзацу: відступ 1 см
- Рисунки: нумерація в межах розділу (Рис. 2.1, Рис. 2.2...)
- Таблиці: нумерація в межах розділу (Таблиця 3.1...)
- Формули: нумерація в межах розділу, формат Equation
- Кожен розділ починається з нової сторінки
- Кожен розділ завершується висновками
- Посилання у квадратних дужках [7, с. 34]
- Унікальність тексту: не менше 75%
- Обсяг: 70-90 сторінок (без додатків)

---

## 10. ПЕРЕЛІК ДІАГРАМ ДЛЯ РОБОТИ

- [ ] Use Case діаграма системи — побудувати на основі маршрутів `app.py:231-816`
- [ ] ER-діаграма бази даних — побудувати на основі `ddl/Users.sql`, `ddl/Comments.sql`, `ddl/EnrichedComments.sql`
- [ ] DFD або BPMN діаграма бізнес-процесу — побудувати на основі підрозділу 3.2
- [ ] Діаграма компонентів системи — побудувати на основі підрозділу 3.4
- [ ] Діаграма послідовності (sequence diagram) для основного сценарію — побудувати для сценарію з 5.3
- [ ] Блок-схема алгоритму sentiment analysis pipeline — побудувати на основі `static/backend/enrich_comments.py:300-568`
- [ ] Архітектурна діаграма веб-додатку — побудувати на основі `app.py`, `static/backend/*`, `templates/*`, `ddl/*`

---

## ДОДАТКОВІ ФАКТИ, ЯКІ ВАРТО ВИКОРИСТАТИ В ДИПЛОМІ

- У проекті наявно `145` test methods у каталозі `tests/`, що покривають auth routes, process flow, backend utilities, extraction, enrichment, analytics та scripts.
- `run_tests.py` збирає suite через `unittest.defaultTestLoader.discover("tests")` (`run_tests.py:6-36`).
- У route tests перевіряються сценарії успішного/неуспішного логіну, CSRF, rate limiting, process-data validation, background flow (`tests/routes/test_auth_routes.py`, `tests/routes/test_process_flow_routes.py`).
- У production UI графіки не залежать від сторонніх chart-бібліотек; система відмальовує їх сама через SVG-рендерери.