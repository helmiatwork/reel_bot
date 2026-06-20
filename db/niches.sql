-- db/niches.sql
-- Master niche catalog for content_automation (short-form / faceless-first).
-- Apply:  docker exec -i postgres psql -U admin -d content_automation < db/niches.sql
-- Idempotent: CREATE IF NOT EXISTS + UPSERT on slug.

CREATE TABLE IF NOT EXISTS niches (
    slug         VARCHAR(64) PRIMARY KEY,
    name         VARCHAR(128) NOT NULL,
    description  TEXT,
    faceless     BOOLEAN     NOT NULL DEFAULT TRUE,  -- bisa tanpa tampil wajah?
    difficulty   VARCHAR(16) NOT NULL DEFAULT 'menengah', -- pemula | menengah | sulit
    rpm          VARCHAR(16) NOT NULL DEFAULT 'sedang',    -- potensi RPM/monetisasi: rendah | sedang | tinggi
    formats      TEXT,        -- format/produksi khas
    example_hook TEXT,        -- contoh hook 0-3 detik
    platforms    VARCHAR(64) DEFAULT 'shorts,tiktok,reels',
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_niches_faceless ON niches(faceless);
CREATE INDEX IF NOT EXISTS idx_niches_difficulty ON niches(difficulty);

INSERT INTO niches (slug, name, description, faceless, difficulty, rpm, formats, example_hook) VALUES
-- ── FACELESS · PEMULA (paling cocok mulai) ───────────────────────────────
('restoration',     'Restorasi Barang',        'Memperbaiki/membersihkan barang rusak jadi seperti baru. Sangat satisfying, retensi tinggi.', TRUE, 'pemula', 'sedang', 'POV tangan, time-lapse, before-after, voiceover/SFX', 'Barang karatan ini dibuang orang...'),
('fakta-unik',      'Fakta Unik',              'Fakta menarik/aneh + voiceover + stok visual. Mudah diproduksi massal.', TRUE, 'pemula', 'rendah', 'voiceover + stok footage + hard-sub', 'Kamu gak akan percaya ini nyata...'),
('kuliner-pov',     'Kuliner POV / Food',      'Masak atau makan POV tangan, ASMR suara, hard-sub resep.', TRUE, 'pemula', 'sedang', 'POV tangan, ASMR, hard-sub, voiceover', 'Resep viral Korea cuma 3 bahan...'),
('satisfying',      'Oddly Satisfying',        'Proses/visual yang memuaskan (potong, bersih, rapi). Retensi loop tinggi.', TRUE, 'pemula', 'rendah', 'close-up, SFX, loop, no-talk', 'Tonton sampai habis, dijamin lega...'),
('ai-story',        'AI Story / Reddit',       'Narasi cerita (Reddit/horror/drama) + AI voice + gameplay/relaxing bg.', TRUE, 'pemula', 'sedang', 'AI voiceover + gameplay bg + auto-caption', 'Mantanku kira aku gak tahu, sampai...'),
('motivation',      'Motivasi / Quotes',       'Kutipan motivasi + visual sinematik + musik. Cepat dibuat.', TRUE, 'pemula', 'rendah', 'teks kinetik, stok sinematik, musik', 'Kalau kamu lagi mau nyerah, dengerin ini...'),
('top-list',        'Top List / Ranking',      '"5 terbaik...", "3 hal...". Format listicle yang gampang ditiru.', TRUE, 'pemula', 'sedang', 'voiceover + ranking visual + hard-sub', '5 barang ini bikin hidup lebih mudah...'),
('life-hack',       'Life Hack / Tips',        'Trik/tips praktis singkat, tutorial cepat POV tangan.', TRUE, 'pemula', 'sedang', 'POV tangan, hard-sub, step-by-step', 'Selama ini kamu salah pakai ini...'),
('scary-story',     'Cerita Horor',            'Cerita seram + ambience + AI/voiceover. Engagement komentar tinggi.', TRUE, 'pemula', 'sedang', 'voiceover gelap, ambience, slow visual', 'Jam 3 pagi, aku dengar suara ini...'),
('text-story',      'Chat / Text Story',       'Cerita lewat screenshot chat / teks berurutan. Murah, viral.', TRUE, 'pemula', 'rendah', 'chat bubble animasi, SFX notif, musik', 'Dia kirim chat ini sebelum hilang...'),

-- ── FACELESS · MENENGAH ──────────────────────────────────────────────────
('manufacturing',   'How It''s Made',          'Proses produksi pabrik / cara barang dibuat. Footage + voiceover.', TRUE, 'menengah', 'sedang', 'footage proses + voiceover + hard-sub', 'Begini cara pensil dibuat massal...'),
('before-after',    'Transformasi',            'Sebelum-sesudah (kamar, kulit, skill, barang). Reveal di akhir.', TRUE, 'menengah', 'sedang', 'split before-after, reveal-ditunda', 'Kamar berantakan ini berubah total...'),
('history',         'Sejarah / Cerita',        'Kisah sejarah/peristiwa + footage arsip + narasi.', TRUE, 'menengah', 'sedang', 'voiceover + footage arsip + peta', 'Kerajaan ini hilang dalam semalam...'),
('finance-edu',     'Edukasi Keuangan',        'Tips uang, nabung, investasi dasar. RPM tinggi (niche duit).', TRUE, 'menengah', 'tinggi', 'teks + grafik + voiceover', 'Cara nabung Rp10jt setahun tanpa nyiksa...'),
('tech-news',       'Tech / Gadget News',      'Berita teknologi, bocoran gadget, tips aplikasi. RPM bagus.', TRUE, 'menengah', 'tinggi', 'screen-record + teks + voiceover', 'Fitur HP ini disembunyikan dari kamu...'),
('crypto-trading',  'Crypto / Trading Edu',    'Edukasi crypto/saham dasar. RPM tinggi, hati-hati klaim.', TRUE, 'menengah', 'tinggi', 'grafik + teks + voiceover', 'Rp1jt di koin ini 2020 jadi...'),
('gaming-clips',    'Gaming Clips',            'Highlight/klip momen game + reaksi teks. Audiens besar.', TRUE, 'menengah', 'sedang', 'gameplay capture + caption + SFX', 'Clutch 1v5 paling gila minggu ini...'),
('anime-edit',      'Anime Edit / AMV',        'Edit klip anime sinkron beat. Audiens loyal besar.', TRUE, 'menengah', 'rendah', 'beat-sync edit, transisi, overlay', 'Scene ini bikin merinding tiap nonton...'),
('car-auto',        'Otomotif / Detailing',    'Mobil, modif, detailing, review. RPM sedang-tinggi.', TRUE, 'menengah', 'sedang', 'footage + voiceover + before-after', 'Mobil bekas ini disulap jadi mewah...'),
('product-review',  'Review / Unboxing',       'Review/unboxing barang POV tangan. Bisa afiliasi.', TRUE, 'menengah', 'tinggi', 'POV tangan, close-up, hard-sub', 'Barang Rp50rb ini ngalahin yang mahal...'),
('pet-animals',     'Hewan / Pet',             'Footage hewan lucu + voiceover/cerita. Shareable tinggi.', TRUE, 'menengah', 'rendah', 'footage + caption lucu + musik', 'Kucing ini tiap hari nungguin majikannya...'),
('asmr',            'ASMR',                    'Suara memuaskan (makan, ketik, alam). Retensi tinggi.', TRUE, 'menengah', 'rendah', 'audio dominan, close-up, no-talk', 'Pakai headset, dengerin ini...'),
('nature-relax',    'Alam / Relaxing',         'Footage alam + lo-fi/ambience. Cocok loop & meditasi.', TRUE, 'menengah', 'rendah', 'footage sinematik + musik', 'Berhenti scroll, tarik napas sebentar...'),
('diy-craft',       'DIY / Kerajinan',         'Bikin barang dari bahan murah. Satisfying + tutorial.', TRUE, 'menengah', 'sedang', 'POV tangan, time-lapse, hard-sub', 'Dari kardus bekas jadi ini...'),
('data-viz',        'Data / Statistik',        'Visualisasi data/perbandingan (negara, harga, tinggi). Bar-race.', TRUE, 'menengah', 'sedang', 'bar-chart race, teks, voiceover', 'Negara terkaya dari 1900 ke 2025...'),
('luxury-bait',     'Luxury / Lifestyle',      'Visual mewah (rumah, mobil, jam). Bait aspiratif.', TRUE, 'menengah', 'sedang', 'footage mewah + teks + musik', 'Rumah Rp100M ini punya lift mobil...'),
('real-estate',     'Property Tour',           'Tur properti + voiceover harga/fitur. Reveal harga.', TRUE, 'menengah', 'tinggi', 'footage tur + voiceover + reveal-harga', 'Tebak harga rumah ini sebelum akhir...'),
('travel',          'Travel / Tempat',         'Footage destinasi + tips + voiceover. Bisa faceless.', TRUE, 'menengah', 'sedang', 'footage + teks + voiceover', 'Tempat di Indonesia ini kayak luar negeri...'),
('sports-clips',    'Sports Highlights',       'Klip olahraga + reaksi. Hati-hati hak cipta.', TRUE, 'sulit', 'rendah', 'klip + caption + SFX', 'Gol mustahil yang bikin stadion gila...'),

-- ── BUTUH WAJAH / ON-CAMERA (ditandai faceless=false) ────────────────────
('street-interview','Street Interview',        'Wawancara orang di jalan. Butuh talent/kamera.', FALSE, 'sulit', 'sedang', 'wawancara + caption + reveal jawaban', 'Aku tanya orang asing pertanyaan ini...'),
('comedy-skit',     'Komedi / Skit',           'Sketsa lucu. Biasanya butuh tampil/akting.', FALSE, 'menengah', 'rendah', 'skit, akting, punchline cepat', 'Pas kamu minta tolong istri...'),
('reaction',        'Reaction',                'Reaksi ke video/konten lain. Butuh wajah.', FALSE, 'pemula', 'rendah', 'split-screen + ekspresi + komentar', 'Pertama kali nonton ini dan...'),
('talking-head',    'Talking Head / Edukasi',  'Bicara langsung ke kamera (edukasi/opini). Otoritas.', FALSE, 'menengah', 'tinggi', 'bicara ke kamera + b-roll + caption', '3 hal yang aku harap tahu lebih awal...'),
('vlog',            'Vlog / Day-in-life',      'Dokumentasi keseharian. Butuh tampil.', FALSE, 'menengah', 'sedang', 'handheld, b-roll, voiceover personal', 'Hari di mana semuanya berubah...')
ON CONFLICT (slug) DO UPDATE SET
    name=EXCLUDED.name, description=EXCLUDED.description, faceless=EXCLUDED.faceless,
    difficulty=EXCLUDED.difficulty, rpm=EXCLUDED.rpm, formats=EXCLUDED.formats,
    example_hook=EXCLUDED.example_hook;
