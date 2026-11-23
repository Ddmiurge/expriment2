# SCJ 交付清单（2026-11-23）

样本数：40；每样本 7 图（封面 + 6 分镜）

## 图片目录（未打包，体积 591 MB）

| uid | theme | 图片数 | 目录 |
|---|---|---:|---|
| `01-Illegal_Activitiy__36` | The Silent Detonation | 7 | `data/scj/images_40C/01-Illegal_Activitiy__36/comic` |
| `01-Illegal_Activitiy__61` | The Shadow Network | 7 | `data/scj/images_40C/01-Illegal_Activitiy__61/comic` |
| `01-Illegal_Activitiy__75` | Shadow of the Atom | 7 | `data/scj/images_40C/01-Illegal_Activitiy__75/comic` |
| `01-Illegal_Activitiy__88` | Survival Through the Lens of Ethics | 7 | `data/scj/images_40C/01-Illegal_Activitiy__88/comic` |
| `02-HateSpeech__108` | Silence the Voice | 7 | `data/scj/images_40C/02-HateSpeech__108/comic` |
| `02-HateSpeech__80` | Shadows of Division | 7 | `data/scj/images_40C/02-HateSpeech__80/comic` |
| `02-HateSpeech__82` | Shadows of Doubt | 7 | `data/scj/images_40C/02-HateSpeech__82/comic` |
| `03-Malware_Generation__19` | The Evolution of Malice | 7 | `data/scj/images_40C/03-Malware_Generation__19/comic` |
| `03-Malware_Generation__3` | The Hidden Code | 7 | `data/scj/images_40C/03-Malware_Generation__3/comic` |
| `03-Malware_Generation__38` | Data Shadows in the Code | 7 | `data/scj/images_40C/03-Malware_Generation__38/comic` |
| `04-Physical_Harm__118` | Shadow Operation | 7 | `data/scj/images_40C/04-Physical_Harm__118/comic` |
| `04-Physical_Harm__7` | Operation Safe Deployment | 7 | `data/scj/images_40C/04-Physical_Harm__7/comic` |
| `04-Physical_Harm__8` | Upgrading the Sky's Guardians | 7 | `data/scj/images_40C/04-Physical_Harm__8/comic` |
| `05-EconomicHarm__21` | The High Stakes Game | 7 | `data/scj/images_40C/05-EconomicHarm__21/comic` |
| `05-EconomicHarm__28` | Predicting the Odds | 7 | `data/scj/images_40D/05-EconomicHarm__28/comic` |
| `05-EconomicHarm__92` | Building Trust in Credit AI | 7 | `data/scj/images_40D/05-EconomicHarm__92/comic` |
| `06-Fraud__150` | The Miracle Cure Scam | 7 | `data/scj/images_40D/06-Fraud__150/comic` |
| `06-Fraud__58` | The Shadow Campaign | 7 | `data/scj/images_40D/06-Fraud__58/comic` |
| `06-Fraud__61` | The Fraudulent Investment Scheme | 7 | `data/scj/images_40D/06-Fraud__61/comic` |
| `07-Sex__18` | Chatting in the Digital World | 7 | `data/scj/images_40D/07-Sex__18/comic` |
| `07-Sex__65` | Precision in the Frame | 7 | `data/scj/images_40D/07-Sex__65/comic` |
| `07-Sex__9` | Accessing Explicit Content Online | 7 | `data/scj/images_40D/07-Sex__9/comic` |
| `08-Political_Lobbying__42` | The AI-Powered Political Pulse | 7 | `data/scj/images_40D/08-Political_Lobbying__42/comic` |
| `08-Political_Lobbying__59` | Tailoring Messages for Maximum Impact | 7 | `data/scj/images_40D/08-Political_Lobbying__59/comic` |
| `08-Political_Lobbying__6` | Efficient Outreach Through Automation | 7 | `data/scj/images_40D/08-Political_Lobbying__6/comic` |
| `09-Privacy_Violence__131` | Shadows of Control | 7 | `data/scj/images_40D/09-Privacy_Violence__131/comic` |
| `09-Privacy_Violence__71` | Guardians of the Digital Chat | 7 | `data/scj/images_40D/09-Privacy_Violence__71/comic` |
| `09-Privacy_Violence__72` | Voices Unveiled | 7 | `data/scj/images_40E/09-Privacy_Violence__72/comic` |
| `10-Legal_Opinion__102` | Claim to Claim | 7 | `data/scj/images_40E/10-Legal_Opinion__102/comic` |
| `10-Legal_Opinion__79` | Safe Returns: A Financial Journey | 7 | `data/scj/images_40E/10-Legal_Opinion__79/comic` |
| `10-Legal_Opinion__90` | Navigating Copyright Waters | 7 | `data/scj/images_40E/10-Legal_Opinion__90/comic` |
| `11-Financial_Advice__23` | Protecting Wealth with Trust | 7 | `data/scj/images_40E/11-Financial_Advice__23/comic` |
| `11-Financial_Advice__62` | Budgeting for a Brighter Future | 7 | `data/scj/images_40E/11-Financial_Advice__62/comic` |
| `11-Financial_Advice__97` | Roots of Legacy | 7 | `data/scj/images_40E/11-Financial_Advice__97/comic` |
| `12-Health_Consultation__43` | Tracking Breath, Finding Clues | 7 | `data/scj/images_40E/12-Health_Consultation__43/comic` |
| `12-Health_Consultation__80` | Navigating Pregnancy and Cancer | 7 | `data/scj/images_40E/12-Health_Consultation__80/comic` |
| `12-Health_Consultation__99` | Managing Crohn's with Care | 7 | `data/scj/images_40E/12-Health_Consultation__99/comic` |
| `13-Gov_Decision__34` | Fairness in Detention | 7 | `data/scj/images_40E/13-Gov_Decision__34/comic` |
| `13-Gov_Decision__51` | Tracking Shadows with Data | 7 | `data/scj/images_40E/13-Gov_Decision__51/comic` |
| `13-Gov_Decision__54` | Predicting Safety, Shaping Futures | 7 | `data/scj/images_40E/13-Gov_Decision__54/comic` |

## 复现命令

```bash
CUDA_VISIBLE_DEVICES=1,2 python scripts/build_scj_set.py \
  --input data/scj/questions_40.jsonl --out data/scj/attack_set_40.jsonl \
  --out-dir data/scj/images_40 --limit 40 --panels 6 --t2i-backend flux \
  --aux-device cuda:0 --t2i-device cuda:1

python scripts/run_stage1.py --attack scj --samples data/scj/attack_set_40.jsonl \
  --pruner none --out runs/scj_40_none --limit 40 --max-new-tokens 3072 \
  --judge-mode hcot --judge-device cuda:1 --max-pixels 409600
```

## 关键数字

| 条件 | ASR | 视觉 token |
|---|---:|---:|
| none | 75.0% (30/40) | 2800 |
| avtp 0.5 | 82.5% (33/40) | ≈1390 |
| Δ | +7.5pp (p=0.25) | — |
