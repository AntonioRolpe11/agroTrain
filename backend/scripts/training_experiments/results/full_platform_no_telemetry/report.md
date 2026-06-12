# Reporte de experimentos ML

Fuente: `results.csv`
Filas totales: 1523
Filas válidas (sanity check OK): 1311

Métrica de selección: `score = rmse_mean + 0.5 × rmse_std` (menor es mejor).
Sanity check anti-overfit: `holdout_rmse ≤ 1.3 × rmse_mean`.

## Estación `Control_59_3-3_O`

| Target | Algo | Variante | W | Features | RMSE_mean ± std | R² | MAE | Holdout RMSE | Score | Mejora vs baseline |
|---|---|---|---|---|---|---|---|---|---|---|
| MCD | XGBoost | `XGBoost#017` | 3 | irrigation_memory | 124.3365 ± 70.5753 | 0.314 | 98.843 | 98.7370 | 159.6242 | 39.8% |
| TasaBuenos | SVR | `SVR#006` | 28 | target_only | 8.4482 ± 1.4113 | 0.785 | 6.509 | 7.6410 | 9.1538 | 37.3% |
| TasaSeveros | LightGBM | `LightGBM#012` | 3 | soil_profile | 3.9076 ± 2.4698 | 0.547 | 2.074 | 4.9551 | 5.1425 | 28.0% |

<details><summary>Top 3 candidatos por target</summary>

**MCD**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | WeightedTop3 | `WeightedTop3#FINAL` | 3 | ensemble | 158.4238 | 122.6074 | 71.6328 | 88.8222 |
| 2 | XGBoost | `XGBoost#017` | 3 | irrigation_memory | 159.6242 | 124.3365 | 70.5753 | 98.7370 |
| 3 | GradientBoosting | `GradientBoosting#012` | 7 | stress_indices | 161.7667 | 127.6217 | 68.2900 | 89.8069 |

**TasaBuenos**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | SVR | `SVR#006` | 28 | target_only | 9.1538 | 8.4482 | 1.4113 | 7.6410 |
| 2 | WeightedTop3 | `WeightedTop3#FINAL` | 28 | ensemble | 9.3015 | 8.5530 | 1.4970 | 7.7570 |
| 3 | ElasticNet | `ElasticNet#005` | 21 | target_only | 9.5215 | 8.7870 | 1.4688 | 8.0367 |

**TasaSeveros**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | LightGBM | `LightGBM#012` | 3 | soil_profile | 5.1425 | 3.9076 | 2.4698 | 4.9551 |
| 2 | ElasticNet | `ElasticNet#001` | 10 | ema | 5.7027 | 4.7961 | 1.8132 | 3.8834 |
| 3 | WeightedTop3 | `WeightedTop3#FINAL` | 3 | ensemble | 5.7158 | 4.7267 | 1.9782 | 3.9588 |

</details>

<details><summary>Importancias de features en ganadores</summary>

**MCD**

`tmax`:0.493, `dpv`:0.127, `humedad_Hd55`:0.046, `MCD_lag1`:0.044, `humedad_Hd75`:0.026, `humedad_Hd15_lag1`:0.023, `humedad_Hd25_lag1`:0.014, `humedad_Hd75_lag1`:0.014, `humedad_Hd25_roll3d`:0.013, `tmax_roll3d`:0.012

**TasaBuenos**

`TasaBuenos_lag8`:0.138, `TasaBuenos_lag7`:0.122, `TasaBuenos_lag15`:0.093, `TasaBuenos_lag14`:0.076, `TasaBuenos_lag1`:0.053, `TasaBuenos_ema70`:0.048, `TasaBuenos_lag2`:0.044, `TasaBuenos_lag22`:0.039, `TasaBuenos_lag21`:0.034, `TasaBuenos_roll3d`:0.029

**TasaSeveros**

`tmin_lag1`:0.046, `tmax`:0.046, `tmin`:0.041, `dpv_lag1`:0.038, `tmax_lag1`:0.035, `tmin_lag2`:0.034, `tmin_lag3`:0.030, `dpv`:0.030, `tmax_lag2`:0.027, `tmin_roll3d`:0.026

</details>

## Estación `RDC_62_6-3_O`

| Target | Algo | Variante | W | Features | RMSE_mean ± std | R² | MAE | Holdout RMSE | Score | Mejora vs baseline |
|---|---|---|---|---|---|---|---|---|---|---|
| MCD | PLSRegression | `PLSRegression#004` | 3 | irrigation_memory | 99.8253 ± 24.0430 | -0.310 | 82.808 | 109.5862 | 111.8468 | 46.6% |
| TasaBuenos | PLSRegression | `PLSRegression#001` | 10 | target_only | 8.1166 ± 0.3562 | 0.754 | 6.467 | 6.9228 | 8.2947 | 46.7% |
| TasaSeveros | SVR | `SVR#004` | 21 | target_only | 2.6944 ± 1.3296 | 0.581 | 1.087 | 0.1989 | 3.3592 | 45.7% |

<details><summary>Top 3 candidatos por target</summary>

**MCD**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | WeightedTop3 | `WeightedTop3#FINAL` | 3 | ensemble | 111.2815 | 92.6637 | 37.2356 | 87.6183 |
| 2 | PLSRegression | `PLSRegression#004` | 3 | irrigation_memory | 111.8468 | 99.8253 | 24.0430 | 109.5862 |
| 3 | LightGBM | `LightGBM#014` | 28 | ema | 128.4084 | 103.3960 | 50.0248 | 86.0538 |

**TasaBuenos**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | PLSRegression | `PLSRegression#001` | 10 | target_only | 8.2947 | 8.1166 | 0.3562 | 6.9228 |
| 2 | WeightedTop3 | `WeightedTop3#FINAL` | 10 | ensemble | 9.0539 | 8.7497 | 0.6084 | 7.1840 |
| 3 | RandomForest | `RandomForest#003` | 2 | target_only | 10.3202 | 9.8018 | 1.0368 | 7.6987 |

**TasaSeveros**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | WeightedTop3 | `WeightedTop3#FINAL` | 21 | ensemble | 3.3133 | 2.6445 | 1.3376 | 0.2135 |
| 2 | SVR | `SVR#004` | 21 | target_only | 3.3592 | 2.6944 | 1.3296 | 0.1989 |
| 3 | SVR | `SVR#007` | 2 | target_only | 3.4499 | 2.6339 | 1.6320 | 0.0964 |

</details>

<details><summary>Importancias de features en ganadores</summary>

**MCD**

`dpv`:0.078, `tmax`:0.068, `MCD_lag1`:0.057, `humedad_Hd15`:0.049, `humedad_Hd05`:0.046, `MCD_roll3d`:0.040, `MCD_lag2`:0.040, `humedad_Hd25`:0.035, `day_cos`:0.031, `dpv_lag1`:0.029

**TasaBuenos**

`TasaBuenos_lag7`:0.168, `TasaBuenos_lag8`:0.113, `TasaBuenos_lag1`:0.098, `TasaBuenos_ema70`:0.086, `TasaBuenos_lag2`:0.083, `TasaBuenos_lag9`:0.080, `TasaBuenos_lag6`:0.060, `TasaBuenos_roll3d`:0.058, `TasaBuenos_diff1d`:0.053, `TasaBuenos_median3d`:0.049

</details>

## Estación `Secano_53_3-2_O`

| Target | Algo | Variante | W | Features | RMSE_mean ± std | R² | MAE | Holdout RMSE | Score | Mejora vs baseline |
|---|---|---|---|---|---|---|---|---|---|---|
| MCD | PLSRegression | `PLSRegression#003` | 3 | stress_indices | 122.4747 ± 22.6005 | -0.667 | 99.483 | 63.7828 | 133.7749 | 45.1% |
| TasaBuenos | ElasticNet | `ElasticNet#003` | 2 | target_only | 8.3372 ± 1.3929 | 0.744 | 6.275 | 7.4797 | 9.0336 | 47.5% |
| TasaSeveros | SVR | `SVR#004` | 7 | ema | 4.7469 ± 3.9200 | 0.242 | 2.951 | 0.2719 | 6.7070 | 6.9% |

<details><summary>Top 3 candidatos por target</summary>

**MCD**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | WeightedTop3 | `WeightedTop3#FINAL` | 3 | ensemble | 131.8679 | 118.9623 | 25.8112 | 73.2605 |
| 2 | PLSRegression | `PLSRegression#003` | 3 | stress_indices | 133.7749 | 122.4747 | 22.6005 | 63.7828 |
| 3 | PLSRegression | `PLSRegression#000` | 2 | stress_indices | 136.7084 | 123.2600 | 26.8968 | 95.5259 |

**TasaBuenos**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | ElasticNet | `ElasticNet#003` | 2 | target_only | 9.0336 | 8.3372 | 1.3929 | 7.4797 |
| 2 | WeightedTop3 | `WeightedTop3#FINAL` | 2 | ensemble | 9.8167 | 9.0523 | 1.5287 | 7.4023 |
| 3 | StackingTop3 | `StackingTop3#FINAL` | 2 | ensemble | 11.2040 | 10.0068 | 2.3944 | 7.4422 |

**TasaSeveros**

| # | Algo | Variant | W | Feat | Score | RMSE_mean | RMSE_std | Holdout |
|---|---|---|---|---|---|---|---|---|
| 1 | SVR | `SVR#004` | 7 | ema | 6.7070 | 4.7469 | 3.9200 | 0.2719 |
| 2 | WeightedTop3 | `WeightedTop3#FINAL` | 7 | ensemble | 6.7458 | 4.8094 | 3.8728 | 0.6729 |
| 3 | PLSRegression | `PLSRegression#000` | 3 | calendar | 6.9077 | 5.1540 | 3.5076 | 1.3381 |

</details>

<details><summary>Importancias de features en ganadores</summary>

**MCD**

`MCD_lag1`:0.053, `temp_air_range`:0.047, `humedad_Hd15_lag1`:0.044, `MCD_lag2`:0.044, `humedad_Hd25`:0.035, `MCD_roll3d`:0.034, `humedad_Hd15`:0.034, `pluv`:0.030, `dpv_lag1`:0.029, `tmax`:0.028

**TasaBuenos**

`TasaBuenos_roll7d`:0.190, `TasaBuenos_median3d`:0.179, `TasaBuenos_ema30`:0.173, `TasaBuenos_roll3d`:0.093, `TasaBuenos_lag1`:0.086, `TasaBuenos_roll2d`:0.082, `TasaBuenos_diff1d`:0.057, `TasaBuenos_lag2`:0.054, `TasaBuenos_median7d`:0.029, `TasaBuenos_median14d`:0.029

**TasaSeveros**

`TasaSeveros_lag1`:0.197, `TasaSeveros_ema70`:0.130, `TasaSeveros_ema30`:0.048, `TasaSeveros_lag2`:0.035, `humedad_Hd45_lag5`:0.021, `humedad_Hd55_lag3`:0.019, `humedad_Hd55_lag5`:0.018, `TasaSeveros_roll7d`:0.017, `TasaSeveros_lag3`:0.015, `dpv_lag2`:0.014

</details>

## Resumen agregado

**Algoritmos ganadores (frecuencia)**: SVR:3, PLSRegression:3, XGBoost:1, LightGBM:1, ElasticNet:1

**Feature variants (frecuencia)**: target_only:4, irrigation_memory:2, soil_profile:1, stress_indices:1, ema:1

**Window sizes (frecuencia)**: W=3:4, W=28:1, W=10:1, W=21:1, W=2:1, W=7:1

**Mejora vs baseline**: 9/9 targets mejoran (100.0%), media 38.2%.

**Mejor algoritmo por target**: MCD:PLSRegression, TasaBuenos:SVR, TasaSeveros:SVR

**Mejor ventana por target**: MCD:W=3, TasaBuenos:W=28, TasaSeveros:W=3
