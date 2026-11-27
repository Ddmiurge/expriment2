## MIDAS

| 条件 | ASR | 截断 | 字数中位 | 目录 |
|---|---:|---:|---:|---|
| none | 24/40 = 60.0% | 12 | 5626 | `runs/stage1_base_3072` |
| AVTP keep25% | 19/40 = 47.5% | 23 | 6648 | `runs/midas_fixed_avtp25` |
| AVTP keep50% | 11/40 = 27.5% | 17 | 5735 | `runs/stage1_avtp50` |
| RI keep25% | 10/40 = 25.0% | 28 | 9524 | `runs/riprune25_midas_40` |
| RI keep50% | 11/40 = 27.5% | 26 | 10702 | `runs/midas_fixed_rip50` |

## DMN

| 条件 | ASR | 截断 | 字数中位 | 目录 |
|---|---:|---:|---:|---|
| none | 37/40 = 92.5% | 0 | 3075 | `runs/dmn_fixed_none_binary` |
| AVTP keep25% | 33/40 = 82.5% | 3 | 3839 | `runs/dmn_fixed_avtp25_binary` |
| AVTP keep50% | 36/40 = 90.0% | 1 | 3258 | `runs/dmn_fixed_avtp50_binary` |
| RI keep25% | 35/40 = 87.5% | 1 | 2821 | `runs/dmn_fixed_rip25_binary` |
| RI keep50% | 35/40 = 87.5% | 2 | 2497 | `runs/dmn_fixed_rip50_binary` |

## SCJ

| 条件 | ASR | 截断 | 字数中位 | 目录 |
|---|---:|---:|---:|---|
| none | 32/40 = 80.0% | 0 | 2386 | `runs/scj_fixed_none_a5` |
| AVTP keep25% | 35/40 = 87.5% | 0 | 2483 | `runs/scj_fixed_avtp25_a5` |
| AVTP keep50% | 34/40 = 85.0% | 0 | 2592 | `runs/scj_fixed_avtp50_a5` |
| RI keep25% | 36/40 = 90.0% | 0 | 2471 | `runs/scj_fixed_rip25_a5` |
| RI keep50% | 35/40 = 87.5% | 0 | 2541 | `runs/scj_fixed_rip50_a5` |

## SIVA-MMSB

| 条件 | ASR | 截断 | 字数中位 | 目录 |
|---|---:|---:|---:|---|
| none | 12/40 = 30.0% | 0 | 1684 | `runs/siva_fixed_none_binary` |
| AVTP keep25% | 12/40 = 30.0% | 0 | 1803 | `runs/siva_mmsb_fixed_avtp25_binary` |
| AVTP keep50% | 14/40 = 35.0% | 0 | 1978 | `runs/siva_fixed_avtp_binary` |
| RI keep25% | 0/40 = 0.0% | 4 | 1283 | `runs/siva_mmsb_fixed_rip25_binary` |
| RI keep50% | 3/40 = 7.5% | 1 | 1712 | `runs/siva_fixed_riprune_binary` |

## SIVA-FR

| 条件 | ASR | 截断 | 字数中位 | 目录 |
|---|---:|---:|---:|---|
| none | 24/75 = 32.0% | 0 | 1412 | `runs/siva_fr_none_binary` |
| AVTP keep25% | 15/75 = 20.0% | 1 | 1598 | `runs/siva_fr_avtp25_binary` |
| AVTP keep50% | 18/75 = 24.0% | 1 | 1462 | `runs/siva_fr_avtp_binary` |
| RI keep25% | 11/75 = 14.7% | 0 | 1514 | `runs/siva_fr_rip25_binary` |
| RI keep50% | 12/75 = 16.0% | 1 | 1468 | `runs/siva_fr_riprune_binary` |

## MIR-180

| 条件 | ASR | 截断 | 字数中位 | 目录 |
|---|---:|---:|---:|---|
| none | 97/180 = 53.9% | 17 | 2891 | `runs/mir180_none` |
| AVTP keep25% | 94/180 = 52.2% | 21 | 3016 | `runs/mir180_avtp25` |
| AVTP keep50% | 93/180 = 51.7% | 18 | 2857 | `runs/mir180_avtp50` |
| RI keep25% | 70/180 = 38.9% | 21 | 2458 | `runs/mir180_rip25` |
| RI keep50% | 88/180 = 48.9% | 24 | 2894 | `runs/mir180_rip50` |

