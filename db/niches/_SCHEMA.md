# Niche guide schema — db/niches/

Katalog niche 3-tier untuk automation content reelbot. **1 file = 1 vertikal.**
Tiap node (vertikal → niche → micro) punya blok `guide` terstruktur yang jadi **pagar AI**
saat generate ide video / script — biar output konsisten & on-niche, gak ngaco.

## Cara pipeline pakai ini (cascade)

Saat generate konten untuk sebuah micro-niche, AI menerima gabungan guide:
`guide vertikal` (aturan umum) + `guide niche` (aturan kategori) + `guide micro` (aturan channel).
Yang lebih spesifik (micro) menang kalau bentrok. Field `hindari` di semua level **digabung** (akumulatif).

## Struktur file (per vertikal)

```yaml
# db/niches/<vertikal>.yml
version: 1
vertical:
  slug: v-satisfying          # slug vertikal (prefix v-)
  name: Satisfying
  description: <1 baris ringkas vertikal>
  guide:                      # GUIDE LEVEL 1 — aturan paling umum
    audience: "<penonton umum vertikal ini, demografi + minat>"
    tone: "<mood/gaya bahasa khas vertikal>"
    format: "<pola produksi umum: durasi, struktur, jenis visual/audio>"
    boleh:                    # hal yang mendorong performa (list)
      - "<...>"
    hindari:                  # LARANGAN eksplisit — kunci anti-ngaco (list)
      - "<...>"
    pola_hook: "<rumus buka 0-3 detik khas vertikal>"
    contoh_judul:             # 3 contoh judul level vertikal (few-shot)
      - "<...>"
  niches:
    - slug: restoration       # = slug asli dari niches.yml, JANGAN diubah
      name: Restorasi Barang
      description: <copy dari niches.yml>
      faceless: true
      difficulty: pemula      # pemula | menengah | sulit
      rpm: rendah             # rendah | sedang | tinggi
      formats: <copy dari niches.yml>
      example_hook: <copy dari niches.yml>
      guide:                  # GUIDE LEVEL 2 — aturan kategori (lebih sempit dari vertikal)
        audience: "<...>"
        tone: "<...>"
        format: "<...>"
        boleh: [ ... ]
        hindari: [ ... ]
        pola_hook: "<...>"
        contoh_judul: [ "<...>", "<...>", "<...>" ]
      micro:
        - slug: restoration-besi-karat   # = slug asli dari niches.yml
          name: Restorasi Besi Karatan
          description: <copy dari niches.yml>
          guide:              # GUIDE LEVEL 3 — aturan 1 channel, PALING spesifik
            audience: "<penonton spesifik channel ini, niat tonton>"
            tone: "<...>"
            format: "<struktur video wajib, durasi target>"
            boleh: [ ... ]
            hindari: [ ... ]   # larangan spesifik channel (mis. 'jangan tampil wajah')
            pola_hook: "<rumus hook khusus channel>"
            contoh_judul:      # 5 judul KONKRET siap-shoot, niru pola channel
              - "<...>"
            content_runway: "<estimasi: kenapa micro ini bisa >50-100 video>"
```

## Aturan isi (WAJIB)

1. **Jangan ubah** slug/name/description/faceless/difficulty/rpm/formats/example_hook yang sudah ada di `db/niches.yml` — copy verbatim. `faceless: t`→true, `f`→false (di niches.yml sudah boolean).
2. Semua node dari vertikal tsb di `db/niches.yml` **harus muncul lengkap** — jumlah niche & micro sama persis.
3. `guide` di SETIAP node (vertikal, niche, micro). Tiga level penuh.
4. Field `guide` semua wajib ada: `audience, tone, format, boleh, hindari, pola_hook, contoh_judul`. Tambahan di micro: `content_runway`.
5. **`hindari` harus konkret & actionable** (bukan "jangan jelek"). Contoh bagus: "jangan pakai musik ber-hak-cipta", "jangan klaim medis tanpa sumber", "hook jangan lebih 5 detik", "jangan tampilkan wajah".
6. `contoh_judul` micro = **5 judul konkret, spesifik, gaya scroll-stopping Indonesia** — jadi few-shot biar AI niru. Bukan template kosong.
7. `content_runway` micro = 1 kalimat alasan micro ini punya stok ide video banyak (lolos uji 50-100 video).
8. Bahasa Indonesia kasual-natural. YAML valid: indent 2 spasi, string ber-`:`/`'` pakai double-quote.

## Contoh TERISI PENUH (rujuk persis gaya ini)

```yaml
        - slug: restoration-besi-karat
          name: Restorasi Besi Karatan
          description: Memulihkan benda besi berkarat parah jadi mengkilap seperti baru.
          guide:
            audience: "Pria 18-40, suka konten 'puas', penonton sebelum tidur, fans before-after."
            tone: "Tenang, no-talking, fokus suara proses (ASMR). Membiarkan hasil bicara."
            format: "30-60 detik. Urutan: kondisi terburuk (hook) → proses cepat (time-lapse) → reveal kilap. Vertikal 9:16, close-up tangan."
            boleh:
              - "Mulai dari kondisi paling parah/ekstrem buat hook kuat"
              - "Pakai SFX gosok/amplas asli, naikkan gain dikit"
              - "Reveal akhir slow-mo 2-3 detik"
            hindari:
              - "Jangan banyak ngomong/voiceover — bunuh vibe ASMR"
              - "Jangan musik ber-hak-cipta; pakai royalty-free tenang"
              - "Jangan skip proses sampai hasil gak kelihatan 'kerja keras'-nya"
              - "Jangan tampilkan wajah — ini channel faceless"
            pola_hook: "Detik 0: close-up bagian terkarat + teks 'dibuang orang'. Langsung mulai gosok di detik 2."
            contoh_judul:
              - "Pisau karatan 50 tahun ini aku bikin kayak baru"
              - "Gembok berkarat dari rumah nenek, hasilnya bikin merinding"
              - "Restorasi kapak tua yang udah dianggap rongsok"
              - "Koin besi karatan ini ternyata masih bisa mengkilap"
              - "Gunting karatan parah → tajam lagi dalam 60 detik"
            content_runway: "Tiap benda besi (pisau, kapak, gembok, engsel, perkakas, sepeda) = 1+ video; pasokan barang rongsok tak terbatas."
```
