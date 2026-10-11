# Local translation layer for Mia (fi and fil to and from English)

Research date: 2026-10-05, for decision D26. Target hardware: Mac mini with 24 GB unified memory
running the main model (about 7 to 8 GB) alongside. Items marked [unverified] are estimates or
claims not confirmed from a primary source.

## 1. Corrections to the brief
- Gemma 4 12B exists: released 2026-06-03, Apache 2.0, on Ollama (`gemma4:12b`), llama.cpp and
  MLX. The first Gemma 4 release (2026-04-02) was E2B, E4B, 26B-A4B (MoE) and 31B.
- TranslateGemma is built on Gemma 3, not Gemma 4. Released 2026-01-15 in 4B, 12B and 27B under
  the Gemma Terms of Use (commercial use allowed, terms passed on, Prohibited Use Policy applies).
- Qwen-MT appears API-only with no open weights [unverified]. The local Qwen option is Qwen3.5
  (Apache 2.0, 201 languages).

## 2. Comparison
Quality: FLORES-200 devtest chrF (0 to 1, higher is better) from the OPUS-MT dashboard; WMT24++
MetricX (lower is better, en to xx only) from the TranslateGemma report; Tatoeba from model cards.

| Model | Licence | Size / memory | Mac runtime | fi to en | en to fi | tl to en | en to tl | Notes |
|---|---|---|---|---|---|---|---|---|
| OPUS-MT tc-big fi-en / en-fi (Marian) | CC-BY 4.0 (ok) | about 235M each, under 1 GB | CTranslate2 (CPU), transformers | chrF 0.626 (best on dashboard) | chrF 0.613 (best on dashboard) | n/a | n/a | Best published Finnish scores of any local model |
| OPUS-MT poz-eng / map-eng 2024 | CC-BY 4.0 (ok) [per-model licence not re-checked] | about 238M | CTranslate2 | n/a | n/a | chrF 0.690, COMET 0.859 | n/a | Strong inbound Filipino; old opus-mt-tl-en (2020) chrF 0.600 |
| OPUS-MT en-tl / multi-target 2024 | Apache 2.0 / CC-BY | 73M / 240M | CTranslate2 | n/a | n/a | n/a | chrF 0.593 / COMET 0.799 | en to tl is OPUS-MT's weakest direction |
| TranslateGemma 4B / 12B / 27B | Gemma ToU (commercial ok, use policy) | Q4: 3.3 / 8.1 / 17 GB | llama.cpp, Ollama, MLX | not published | MetricX 5.68 / 3.77 / 3.19 | not published | MetricX 4.20 / 3.17 / 2.98 | fi and fil among 55 evaluated languages; report notes a regression from mistranslated named entities |
| Gemma 4 12B as its own translator | Apache 2.0 (ok) | 0 extra if it is the main model | llama.cpp, Ollama, MLX | no MT numbers | no MT numbers | no MT numbers | no MT numbers | Predecessor Gemma 3 12B: en to fi 5.11, en to fil 4.03 |
| Qwen3.5 9B / 4B | Apache 2.0 (ok) | about 5.5 / 2.5 GB Q4 [unverified] | llama.cpp, MLX | not published | not published | not published | not published | General model, no MT evaluation found |
| MADLAD-400 3B / 7B / 10B | Apache 2.0 (ok) | 3B about 3 GB int8 | CTranslate2 | not on dashboard | not on dashboard | not on dashboard | not on dashboard | Filipino code not confirmed [unverified]; not tuned for domain text |
| NLLB-200 | CC-BY-NC 4.0 (excluded: non-commercial) | 0.6 to 3.3B | CTranslate2 | chrF 0.576 to 0.610 | 0.505 to 0.537 | 0.645 to 0.680 | n/a | OPUS-MT beats it for Finnish anyway |
| SeamlessM4T v2 | CC-BY-NC 4.0 (excluded) | 2.3B | transformers | n/a | n/a | n/a | n/a | |
| Aya Expanse 8B / 32B | CC-BY-NC (excluded) | 8B | Ollama | n/a | n/a | n/a | n/a | Covers neither fi nor tl |
| Tower+ 2B / 9B | CC-BY-NC-SA 4.0 (excluded) | 2.6B / 9B | llama.cpp | n/a | n/a | n/a | n/a | |
| Hunyuan-MT-7B / HY-MT1.5 | Tencent licence, not valid in the EU (excluded for Finland) | 7B / 1.8B | llama.cpp | n/a | n/a | n/a | n/a | Filipino yes, Finnish no |
| Firefox Translations (Bergamot) | MPL-2.0 (ok) | 17M to 30M | bergamot-translator [Mac packaging unverified] | chrF 0.592 | 0.600 | no Tagalog | no Tagalog | Tiny and fast, Finnish only |
| EuroLLM-9B-Instruct | Apache 2.0 (ok) | 9B | llama.cpp | not checked | not checked | no | no | Finnish-only option |
| SalamandraTA 2B / 7B | Apache 2.0 (ok) | 2B / 7B | llama.cpp | not checked | not checked | no | no | Finnish assumed [unverified] |
| Poro 2 8B | Llama 3.1 licence (use policy) | 8B | llama.cpp | no MT numbers | no MT numbers | no | no | Strong Finnish model, not MT |
| Gemma-SEA-LION v4 | Gemma licence (use policy) | 4B VL / 27B | llama.cpp | n/a | n/a | strong Filipino on SEA benchmarks | strong Filipino on SEA benchmarks | 27B too large next to the main model |

Informal text: no published benchmark covers WhatsApp-style Finnish puhekieli or Taglish. LLM
translators probably cope better with slang and code-switching than Marian models [unverified];
measure it on our own test set (section 5).

Latency for a 20-word message (about 35 to 50 tokens) on a base M4 Mac mini [estimates]:
TranslateGemma 4B Q4 about 0.8 to 1.5 s per direction; TranslateGemma 12B or Gemma 4 12B about
2.5 to 4 s per direction (5 to 8 s per round trip); OPUS-MT on CTranslate2 about 0.1 to 0.3 s.

Memory: main model plus TranslateGemma 4B plus caches is about 12 GB and fits; a separate 12B
translator (about 16 GB total) is tight. Use a 12B translator only if it is the main model.

## 3. Recommendation (to be confirmed by the measurements in section 5)
| | Primary | Fallback |
|---|---|---|
| fi | TranslateGemma 4B (own llama-server or Ollama) | OPUS-MT tc-big fi-en / en-fi on CTranslate2; candidate primary for en to fi, since outbound text is clean English |
| fil | TranslateGemma 4B (en to fil MetricX 4.20) | OPUS-MT poz-eng 2024 inbound, 2024 multi-target outbound (the 2020 en-tl model is weak) |
| No extra memory | Gemma 4 12B as translator with the TranslateGemma prompt, if Gemma 4 12B is the main model | same fallbacks |

Excluded by licence: NLLB, Seamless, Aya, Tower (non-commercial), Hunyuan (not valid in the EU),
CometKiwi (non-commercial, for evaluation only). Gemma ToU and the Llama licence carry use
policies; record the choice in an ADR.

## 4. Proposed layer design
```
inbound:  text -> lang = detect(text, person.language)
          -> if lang == "en": pass through
          -> extract facts from the ORIGINAL text (dates, times, numbers, known names)
          -> mask (dates, times, numbers, phones, IDs only) -> translate(lang -> en)
          -> unmask -> verify -> English text + extracted facts -> English model
outbound: English reply text -> mask -> translate(en -> lang) -> unmask -> verify
          -> quick-reply labels from i18n in lang (never translated)
```
1. Language detection: person.language as the prior, the existing hint-word detector as the
   override (add a Filipino word list); Taglish counts as fil. Add Lingua or GlotLID (Apache 2.0)
   only if the test set shows misdetections; fastText lid.176 is share-alike, CLD3 is weak on
   short text. One-word replies ("ok", "sige", "joo") fall back to person.language.
2. Extract before translating (rule 7): deterministic date, time and number parsing and the name
   and site matcher run on the source text, so a translation error cannot change a date or name.
3. Placeholders for dates, times, numbers, phones, IDs and URLs; each must appear exactly once
   after translation, otherwise retry without masking, then the fallback engine, then flag.
   Finnish inflects names ("Annalle", "Töölössä"), so names are not masked into Finnish; the
   name's stem is verified instead.
4. Quick-reply labels and i18n strings are rendered in the user's language and never
   translated; button payloads are ids.
5. Cheap checks on every message: placeholders and numbers match, output language equals target,
   length ratio within bounds, no added commentary. Back-translation only offline or for replies
   that approve, pay or change a schedule.
6. Cache only outbound text, in process (LRU on languages, model id and normalised text); no
   persistent cache of personal messages.
7. Rule 8: the translator wraps user text as data; output that answers instead of translating is
   discarded (caught by the language and length checks).
8. Rule 6: the translator is a local server on the node, on the same local-model path.

## 5. Measuring the layer on its own
- Parallel test set written by native speakers (not machine translated): every scenario in en, fi
  and fil, each with a formal variant, an informal one (puhekieli, typos, Taglish) and one with
  names, sites, dates and times.
- Metrics: chrF++ and COMET-22 against the English reference [COMET licence to verify]; exact
  preservation of names, dates, times and numbers; end-to-end intent accuracy for en (baseline),
  fi to en and fil to en (the gap is the cost of translation and D26's revisit trigger, compared
  with a multilingual model on the raw text); native-rater adequacy and fluency for about 50
  replies per language; added latency at p50 and p95.
- Engines: TranslateGemma 4B and 12B, Gemma 4 12B (self-translate), OPUS-MT. Choose primary and
  fallback per language and direction from the results.
- CI uses a stub translator (MIA_MODEL=test); real engines run in the evals suite.

## 6. Risks
- No published informal-text or xx to en numbers for TranslateGemma on fi or fil.
- Named entities (TranslateGemma's own report); mitigated by masking and source-side extraction.
- Finnish inflection against masking (section 4).
- Latency: 5 to 8 s per round trip with a 12B translator, about 2 s with 4B, under 0.5 s with
  OPUS-MT. Two models on 24 GB share memory bandwidth.
- Licences: Gemma ToU and Llama obligations; non-commercial models stay out of the repository
  and the image.
- OPUS-MT en to tl is weak; never the only Filipino engine.

## 7. Sources
- TranslateGemma: https://blog.google/innovation-and-ai/technology/developers-tools/translategemma/ ,
  report https://arxiv.org/pdf/2601.09012 , card https://huggingface.co/google/translategemma-4b-it ,
  Ollama https://ollama.com/library/translategemma ,
  licence https://the-decoder.com/googles-new-open-translategemma-models-bring-translation-for-55-languages-to-laptops-and-phones/
- Gemma 4: https://the-decoder.com/googles-gemma-4-is-now-available-with-apache-2-0-licensing-for-the-first-time/ ,
  https://en.wikipedia.org/wiki/Gemma_(language_model) , https://ai.google.dev/gemma/docs/releases?hl=en ,
  https://vpsranking.com/news/ai/ai-2026-06-03-google-gemma-4-12b/ , https://arxiv.org/pdf/2607.02770
- Qwen3.5: https://huggingface.co/Qwen/Qwen3.5-9B
- OPUS-MT: https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-fi-en , https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-fi ,
  https://huggingface.co/Helsinki-NLP/opus-mt-tl-en , https://huggingface.co/Helsinki-NLP/opus-mt-en-tl ,
  dashboard https://opus.nlpl.eu/dashboard/ , paper https://arxiv.org/pdf/2212.01936
- NLLB licence: https://huggingface.co/facebook/nllb-200-distilled-600M/blob/main/README.md
- MADLAD-400: https://huggingface.co/google/madlad400-3b-mt , https://huggingface.co/Heng666/madlad400-3b-mt-ct2-int8
- SeamlessM4T v2: https://www.promptlayer.com/models/seamless-m4t-v2-large
- Aya Expanse: https://registry.ollama.ai/library/aya-expanse
- Tower+: https://featherless.ai/models/Unbabel/Tower-Plus-9B
- Hunyuan-MT: https://huggingface.co/tencent/Hunyuan-MT-7B , https://canirun.ai/license/tencent-hunyuan-community/
- Firefox Translations: https://github.com/mozilla/translations , https://www.mozilla.org/firefox/features/translate/
- EuroLLM: https://huggingface.co/utter-project/EuroLLM-9B-Instruct
- SalamandraTA: https://arxiv.org/abs/2508.12774v1
- Poro 2: https://www.amd.com/en/blogs/2026/extending-context-and-exploring-multilingual-reasoning-with-poro.html
- SEA-LION v4: https://www.marktechpost.com/2025/08/25/sea-lion-v4-multimodal-language-modeling-for-southeast-asia/
- Batayan (Filipino and Taglish benchmark): https://arxiv.org/abs/2502.14911v1
- Language ID: https://huggingface.co/cis-lmu/glotlid , https://github.com/pemistahl/lingua-py ,
  https://fasttext.cc/docs/en/language-identification.html
- CTranslate2: https://pypi.python.org/pypi/ctranslate2 , macOS int8 note https://forum.opennmt.net/t/quantized-models-not-supported-on-macos/5584
- M4 Mac mini decode speed: https://willitrunai.com/zh/can-run/llama-3.1-8b-on-m4-mini-32gb
