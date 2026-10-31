# Reelbot → Studio Kreator ATM (Amati · Tiru · Modifikasi)

Tanggal: 2026-10-31 · Status: draft, menunggu persetujuan

## 1. Intinya

Reelbot berubah dari "kumpulan alat analisa" menjadi **satu jalur kerja kreator**:

```
Amati → Blueprint (Tiru + Modifikasi) → Jadwal → Produksi → Evaluasi draft → Upload → Pantau → Belajar
   ^                                                                                      |
   └──────────────────────────── pelajaran masuk ke blueprint berikutnya ─────────────────┘
```

Target pengguna: **kreator awam**. Ia tidak perlu tahu teori konten. Setiap hari ia membuka
reelbot, melihat "Hari Ini: rekam konten X, edit konten Y, upload konten Z", dan setiap konten
sudah punya paket lengkap: referensi, naskah, shot list, audio, langkah CapCut, judul, deskripsi,
prompt thumbnail. Setelah video jadi, AI menilai dan memberi perbaikan konkret. Setelah upload,
AI memantau dan mengabari lewat Telegram kalau videonya kurang perform.

### Tujuan
- Dari pilih video referensi sampai "paket siap rekam" < 10 menit.
- Jadwal rutin yang konsisten (mis. 3 Shorts/minggu) dengan daftar konten yang selalu terisi.
- Setiap video dievaluasi minimal 1× sebelum upload; setiap evaluasi tersimpan (Evaluasi 1, 2, …).
- Setiap video dipantau setelah upload; yang di bawah target memicu notifikasi Telegram.
- Pelajaran dari evaluasi + performa otomatis dipakai blueprint berikutnya.

### Bukan tujuan (non-goals)
- Render / edit video di reelbot. Edit tetap di CapCut (keputusan scope 2026-07-05).
- Auto-upload ke YouTube. Upload tetap manual oleh manusia.
- Bot yang berinteraksi di platform (auto-comment, auto-like, auto-subscribe).

### Anti-goal (gagal walau secara teknis jalan)
- Video hasil "tiru" yang terkena kebijakan **reused content** YouTube (demonetisasi) karena terlalu mirip
  sumber. ATM = tiru *struktur dan format*, bukan menyalin footage.
- Channel utama kena flag karena scraping memakai cookie channel utama.
- Kreator tenggelam di 20 menu. Jalur utama harus bisa dijalankan tanpa membuka menu lain.

## 2. Yang sudah ada dan dipakai ulang

| Kebutuhan | Sudah ada | Dipakai sebagai |
|---|---|---|
| Cari referensi | Discover, SEO (`/seo/analyze`), Creators, `/youtube/trending` | tahap Amati |
| Bedah video | `/analyze/claude` (hook, struktur, retensi), tab Efek (`/analyze/gemini-effects`), Bikin Ide (`/analyze/gemini-ideas`, `/analyze/ideas/select`) | bahan Blueprint |
| Kanban konten | `content_items` + Studio (`/studio/*`, stage idea→script→prep→scheduled→posted) | tulang punggung daftar konten |
| Variasi pemenang | `/winners`, `/winners/clone`, `/generate/batch` | isi otomatis daftar konten |
| Jadwal + pengingat | `scheduled_posts`, `/schedule/*`, `/schedule/remind-due` | Kalender rutin |
| Pantau performa | `performance_snapshots`, `/performance/refresh` (yt-dlp), `/performance/check-targets`, `_telegram_notify` | tahap Pantau |
| Memori AI | `learnings` (`/learnings`, kind question/hook/pattern/insight, `hits`) | tahap Belajar |
| Aset | Songs + Potongan Audio (`kind`, `is_viral`), segments Pecah Kompilasi, Prep ZIP | Pustaka Aset |
| Analisa frame | claude-bridge (`claude -p` + frames), faster-whisper | Evaluasi draft |

Menu Studio, Jadwal, dan Performance yang disembunyikan pada 2026-10-31 **dihidupkan lagi** dalam bentuk baru
(lihat §4). Kodenya tetap; yang berubah alurnya.

## 3. Alur per tahap

### 3.1 Amati
- Kreator memilih niche (mis. "kucing lucu") → reelbot menampilkan video referensi: trending + top
  creators niche itu + keyword SEO dengan skor.
- Satu klik "Jadikan referensi" → jalankan analisa (hook/struktur/efek) bila belum ada (cache per URL sudah ada).
- Referensi disimpan di `sources` (sudah ada); tidak ada tabel baru.

### 3.2 Blueprint ATM (inti nilai)
Dari 1 referensi + niche + pelajaran (`learnings`) → AI membuat **Blueprint Konten**, disimpan di
`content_items.blueprint` (JSONB, berversi). Isi blueprint:

1. **ATM ringkas** — apa yang ditiru (struktur, pola hook, tempo, jenis shot), apa yang dimodifikasi
   (sudut cerita, twist niche, karakter), dan **checklist orisinalitas** (footage sendiri, narasi sendiri,
   tidak memakai klip referensi sebagai materi).
2. **Judul** — 5 opsi, dengan keyword utama dari SEO; panjang dan pola dicek (angka, emosi, rasa penasaran).
3. **Hook 3 detik** — kalimat + visual pembuka.
4. **Narasi / VO** — naskah lengkap bertimestamp, gaya bicara awam. Per konten dipilih `voice_mode`:
   - `self` (suara sendiri): tampilan teleprompter per beat, tanda jeda/penekanan, tips rekam (jarak mic,
     ruangan, rekam per beat supaya gampang dipotong).
   - `ai` (AI voice): reelbot membuat **MP3 per beat** lewat provider TTS, disimpan ke Pustaka
     (`songs.kind = 'voiceover'`, terhubung ke konten). Bisa preview dan "buat ulang beat ini". Biaya
     (jumlah karakter) ditampilkan sebelum generate.
   - Provider di balik satu antarmuka: **ElevenLabs** (sudah ada di `voiceover/voiceover.py`), slot untuk provider
     lain (mis. OpenAI TTS, Google Cloud TTS) ditambah hanya bila dibutuhkan. gTTS hanya untuk preview gratis.
   - Reelbot **tidak** menggabung suara ke video (`merge_with_video` tetap tidak dipakai); MP3 dimasukkan di CapCut.
5. **Shot list** — tiap shot: durasi, apa yang direkam ("close-up kucing mengejar laser, kamera setinggi lantai"),
   framing, gerak kamera, teks di layar, transisi/efek CapCut (dari data Efek).
6. **Audio** — BGM dipilih dari Songs/Potongan Audio berdasarkan mood, BPM, dan flag viral; SFX per momen.
7. **Daftar aset** — "sudah punya" (link ke pustaka) vs "harus direkam/dicari".
8. **Langkah CapCut untuk pemula** — urutan langkah edit bernomor.
9. **Thumbnail** — 3 prompt siap tempel untuk AI gambar (konsep berbeda: wajah/emosi, before-after, objek
   besar + teks), teks overlay ≤ 4 kata, aturan komposisi (kontras, 1 fokus, terbaca di layar HP), alasan
   kenapa konsep itu menaikkan CTR.
10. **Paket upload** — deskripsi (2 baris pertama berisi keyword), tags, hashtag, komentar tersemat,
    playlist, end screen, checklist upload YouTube.

Kreator bisa menyunting tiap bagian; tombol "buat ulang bagian ini" hanya meregenerasi satu bagian.

### 3.3 Jadwal rutin
- Pengaturan ritme: mis. 3 konten/minggu, Senin/Rabu/Jumat 19:00 WIB, per akun.
- Kalender otomatis diisi dari daftar blueprint siap; slot kosong memicu saran "ambil dari pemenang"
  (`/winners/clone`) atau "buat dari referensi baru".
- Status konten: `ide → blueprint → rekam → edit → review → siap → terjadwal → tayang → dipantau`.
- Halaman **Hari Ini**: tugas hari ini (rekam/edit/upload), alert performa, evaluasi yang menunggu.
- Telegram: pengingat H-1 dan hari-H (memakai mekanisme `remind-due` yang sudah ada).

### 3.4 Evaluasi draft (sebelum upload)
- Kreator upload hasil edit (mp4) ke konten itu.
- AI menilai **terhadap blueprint dan referensinya**: frame sampling + transkrip (whisper) + audio level.
- Output terstruktur: skor per aspek (hook, tempo, kejelasan cerita, audio, teks/caption, thumbnail-fit,
  kepatuhan blueprint, orisinalitas), **temuan bertimestamp** ("00:04–00:07 terlalu lambat, potong 1,5 detik"),
  dan **instruksi perbaikan** bernomor yang bisa langsung dikerjakan di CapCut.
- Tiap upload ulang = putaran baru: **Evaluasi 1, Evaluasi 2, …**, disimpan permanen. Putaran berikutnya
  membandingkan dengan sebelumnya ("3 dari 5 perbaikan sudah dikerjakan").
- Kreator bisa menandai tiap temuan setuju/tidak + catatan; catatan ini ikut jadi bahan belajar.

### 3.5 Pantau (setelah upload)
- Kreator menempel URL YouTube setelah upload (seperti sekarang di Jadwal).
- Checkpoint pantau: 1 jam, 6 jam, 24 jam, 48 jam, 7 hari. Data publik via **yt-dlp tanpa login**:
  views, likes, jumlah komentar.
- Dibandingkan dengan **baseline channel sendiri** (median video sebelumnya di umur yang sama) dan target.
- Di bawah ambang → **Telegram**: "Video 'X' 24 jam: 120 views, 70% di bawah median channel. Dugaan: judul/
  thumbnail kurang memancing klik. Saran: ganti thumbnail ke konsep B (prompt terlampir)."
- Hari ke-7 → **Evaluasi pasca-tayang** otomatis (putaran `post`), disimpan seperti evaluasi draft.

Catatan jujur: tanpa YouTube Analytics OAuth, **CTR dan retensi tidak terlihat**. Diagnosis tahap ini berbasis
views/likes/komentar vs baseline. OAuth (jalur `/youtube-callback` sudah ada) adalah upgrade opsional §6-P6.

### 3.6 Belajar
- Setelah evaluasi draft dan evaluasi pasca-tayang, AI menyuling pelajaran ke `learnings`
  (per niche, kind hook/pattern/insight), dengan `source_ids` sebagai jejak asal.
- Pelajaran yang terbukti berulang (`hits` naik) diprioritaskan saat membuat blueprint baru.
- Halaman **Belajar**: riwayat evaluasi per konten + daftar pelajaran yang bisa disunting/dihapus manusia.

## 4. Navigasi baru

| Menu | Isi | Dari menu lama |
|---|---|---|
| Hari Ini | tugas hari ini, alert, evaluasi tertunda | Dashboard |
| Rencana | kalender + daftar konten (kanban status) | Studio + Jadwal |
| Amati | cari referensi, keyword, kreator, hasil analisa | Discover, SEO, Creators, Analysis |
| Produksi | halaman konten: tab Blueprint · Shot list · Narasi · Audio · Thumbnail · Upload · Evaluasi | Prep, Bikin Ide, Efek |
| Pantau | performa per video + alert | Performance |
| Pustaka | Songs, Potongan Audio, klip/segmen, sources | Songs, Potongan Audio, Sources |
| Belajar | pelajaran + riwayat evaluasi | (baru, pakai `learnings`) |
| Pengaturan | akun, ritme jadwal, Telegram, cookies | Scrape Accounts |

Alat lanjutan (Pecah Kompilasi, Clipper) menjadi tombol di Amati/Pustaka, bukan menu sendiri.

## 5. Data

- `content_items` (sudah ada) — tambah kolom: `reference_source_id`, `blueprint JSONB`, `blueprint_version INT`,
  `account_id`, `scheduled_at`, `published_url`, `draft_video_path`; `stage` memakai status baru §3.3
  (migrasi memetakan stage lama: script→blueprint, prep→rekam, scheduled→terjadwal, posted→tayang).
- `content_evaluations` (baru) — `id, content_item_id, kind ('draft'|'post'), round INT, video_ref, scores JSONB,
  findings JSONB, fixes JSONB, summary TEXT, compared_to_round INT, human_notes JSONB, model, created_at`;
  unik `(content_item_id, kind, round)`.
- `monitor_snapshots` (baru) — `content_item_id, url, checkpoint_h, views, likes, comments, alerted`, unik per
  (konten, checkpoint). Tabel terpisah karena `performance_snapshots` punya indeks unik per hari yang bentrok
  dengan checkpoint 1 jam dan 6 jam di hari yang sama.
- `routine_settings` (baru, kecil) — per akun: hari, jam, jumlah per minggu, ambang alert.
- `learnings` — tetap; tambah `kind` = `fix` untuk pelajaran dari evaluasi.

Semua migrasi aditif (`ADD COLUMN IF NOT EXISTS`), mengikuti pola init-db yang sudah ada. PostgreSQL saja.

## 6. Tahapan (tiap tahap = 1 PR yang bisa dipakai sendiri)

| # | Tahap | Hasil yang bisa dipakai | Perkiraan |
|---|---|---|---|
| P0 | Fondasi | kolom baru, status baru, navigasi baru, scheduler tick (pengganti n8n), cek Telegram | 2–3 hari |
| P1 | Blueprint ATM | dari 1 referensi → paket lengkap §3.2 termasuk prompt thumbnail + langkah CapCut | 4–5 hari |
| P2 | Rencana + Hari Ini | ritme jadwal, kalender terisi otomatis, pengingat Telegram | 3 hari |
| P3 | Evaluasi draft | upload mp4 → Evaluasi N tersimpan, perbandingan antar putaran | 4 hari |
| P4 | Pantau + alert | checkpoint yt-dlp, baseline channel, alert Telegram, evaluasi pasca-tayang | 3–4 hari |
| P5 | Belajar | suling pelajaran, dipakai blueprint, halaman Belajar | 2–3 hari |
| P6 (opsional) | YouTube Analytics OAuth | CTR + retensi nyata dalam diagnosis | 2 hari |

Urutan dipilih supaya nilai terbesar (P1) datang paling awal; P3–P5 butuh konten nyata untuk diuji.

## 7. Keamanan

- **Pantau tanpa login.** yt-dlp membaca metadata publik video sendiri; tanpa cookie. Batas laju: 1 request per
  video per checkpoint, jeda acak, maksimal N video per tick. Playwright hanya cadangan (headless, tanpa login)
  bila yt-dlp gagal.
- **Pisah akun.** Cookie akun `scrape` (burner) dipakai untuk download referensi; cookie channel utama **tidak pernah**
  dipakai scraping (aturan role yang sudah ada).
- **Tanpa aksi di platform.** Tidak ada auto-upload, auto-komentar, auto-like. Risiko banned dari reelbot ≈ nol.
- **Orisinalitas.** Blueprint wajib berisi checklist modifikasi; Evaluasi menilai "orisinalitas" dan memberi peringatan
  bila draft memuat footage referensi. Tujuannya lolos kebijakan reused content dan aman monetisasi.
- **Label konten AI.** Bila narasi/visual dibuat AI secara realistis, upload kit mengingatkan centang label
  "altered or synthetic content" di YouTube Studio.
- **Rahasia.** Token Telegram, API key di `.env` (tidak di-commit). claude-bridge hanya bind 127.0.0.1. Dashboard
  hanya localhost; bila dibuka lewat ngrok, `PIPELINE_API_KEY` wajib aktif.
- **Suara AI.** API key TTS hanya di `.env`. Clone suara hanya untuk suara kreator sendiri; tidak ada fitur meniru
  suara orang lain. Konten dengan suara AI realistis mendapat pengingat label "altered or synthetic content".
- **Upload draft.** Hanya ekstensi video yang diizinkan, batas ukuran (pola `/songs/import` yang sudah ada), nama file
  UUID, disimpan di luar web root.

## 8. Model AI (keputusan saya, bisa diubah)

| Tugas | Model | Alasan |
|---|---|---|
| Blueprint, Evaluasi draft/pasca-tayang | `claude-sonnet-5-5` via claude-bridge | butuh penilaian kreatif; lebih murah dari Sonnet 4.6 yang dipakai sekarang |
| Klasifikasi ringan, suling pelajaran, ringkasan alert | `claude-haiku-5-5` | murah, cukup untuk tugas terstruktur |
| Tag audio | Gemini via cliproxy (sudah jalan) | tetap |
| Suara narasi (`voice_mode = ai`) | ElevenLabs (sudah ada), provider lain opsional | kualitas Bahasa Indonesia terbaik saat ini; diputuskan pemilik 2026-10-31 |

## 9. Keputusan yang saya ambil sendiri

- Scheduler: satu job launchd memanggil `/cron/tick` tiap 15 menit (pola `com.reelbot.performance-collector.plist`
  yang sudah ada), menggantikan n8n. Alasan: n8n sedang mati dan berat untuk dirawat.
- Notifikasi hanya Telegram (sudah ada `_telegram_notify`).
- Bahasa UI default Indonesia, toggle EN tetap.
- Thumbnail: reelbot membuat **prompt**, bukan gambar. Kreator menempel ke AI gambar pilihannya.

## 10. Yang perlu dijawab pemilik produk

1. Niche dan channel mana yang jadi fokus pertama (1 channel dulu atau langsung beberapa akun)?
2. Format: YouTube Shorts saja, video panjang, atau keduanya?
3. Ritme awal: berapa konten per minggu, hari dan jam tayang?
4. ~~Narasi~~ — dijawab 2026-10-31: keduanya, dipilih per konten (suara sendiri atau AI voice seperti ElevenLabs).
5. Mau mengaktifkan YouTube Analytics OAuth (P6) supaya CTR/retensi terlihat?
