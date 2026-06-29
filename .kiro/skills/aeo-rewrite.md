---
name: aeo-rewrite
description: >
  Gunakan skill ini untuk merewrite (paraphrase) artikel yang sudah ada dari sebuah URL
  menjadi artikel Markdown baru yang dioptimasi untuk AEO (Answer Engine Optimization),
  GEO (Generative Engine Optimization), dan E-E-A-T — mengikuti Non-Commodity Content Framework.

  Skill ini BERBEDA dari aeo-geo-content: input-nya adalah URL artikel yang sudah ada
  (bukan topik baru), dan outputnya adalah versi rewrite yang lebih expert-driven,
  lebih manusiawi, dan lebih layak dikutip AI.

  Gunakan skill ini kapanpun user menyebut: "rewrite artikel", "paraphrase artikel",
  "upgrade konten", "perbaiki artikel", "optimasi artikel lama", "convert artikel ke AEO",
  atau memberikan URL dan meminta dibuatkan ulang/diperbaiki.
---

# AEO Rewrite Skill

Skill ini mengubah artikel yang sudah ada (dari URL) menjadi versi rewrite berkualitas
tinggi yang lebih expert-driven, dioptimasi untuk AEO/GEO, memenuhi E-E-A-T, dan
memiliki struktur Non-Commodity yang sulit ditiru AI generik.

## Cara Pakai di Platform Ini

Jalankan via workflow:
```
python main.py run rewrite_article --keyword="<URL artikel sumber>"
```

Atau dengan data tambahan:
```
python main.py run rewrite_article --keyword="<URL>" --extra-context="<konteks tambahan>"
```

## Komponen Wajib Output

1. Strong Hook (beda dari sumber)
2. Context & Target Pembaca
3. Root Cause Analysis
4. Reframed Core Content (H2/H3 berbeda dari sumber)
5. Human Layer (atau placeholder)
6. Obstacles / Failure Story
7. Original Insight
8. Reusable Framework / Checklist
9. Actionable Recommendations
10. FAQ Section (min 3-5)
11. Strong Conclusion
12. SEO Metadata block
13. Internal Link recommendations
