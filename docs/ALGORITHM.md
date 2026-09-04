# Соответствие ТЗ и кода

Таблица прослеживаемости: каждый пункт ТЗ (`TZ_ZONES.md`) → модуль → тест.
Она нужна, чтобы при доработках было видно, какое требование можно сломать.

| §ТЗ | Требование | Реализация | Тест |
|---|---|---|---|
| 1 | Искать области, а не уровни | `clustering.py`, `boundaries.py` | `test_near_prices_merge_into_one_cluster` |
| 2 | H4 основной, H1 уточняющий, M5 только после зоны | `engine._collect_evidence`, `m5_confirm.py` | `test_m5_does_not_create_zones` |
| 3 | Анализ только закрытых свечей | `data_feed.load_mt5` (срез последней), `engine` | — |
| 4 | Определение фитиля | `models.Candle.upper_wick/lower_wick` | `test_candle_wick_geometry_matches_spec` |
| 5 | Не каждый фитиль — зона | `wicks._wick_significance` | `test_small_wick_is_not_a_zone` |
| 6 | Три характеристики значимости | `wicks._wick_significance` | `test_small_wick_is_not_a_zone` |
| 7, 8 | Важно, что было после фитиля | `wicks.measure_reaction` | `test_reaction_after_wick_is_measured` |
| 9 | Тип реакции ≠ торговое направление | `models.Direction` | `test_zone_itself_carries_no_trade_direction` |
| 10, 11 | Кандидат хранит область фитиля | `wicks.find_wick_events` | `test_significant_wick_is_detected_with_area` |
| 12 | Длинный фитиль не берётся целиком | `boundaries._core_range` | `test_zone_width_is_bounded_by_volatility` |
| 13, 14 | Поиск повторных реакций, кластеризация | `clustering.cluster_evidence` | `test_near_prices_merge_into_one_cluster` |
| 15 | Далёкие цены не объединяются | `clustering.cluster_evidence` | `test_distant_prices_do_not_merge` |
| 16 | Расстояние зависит от волатильности | `config.cluster_merge_atr` + ATR | `test_merge_distance_scales_with_volatility` |
| 17 | H4 — главный источник зоны | `clustering` (кластер без H4 отбрасывается) | `test_cluster_without_h4_is_not_a_zone_source` |
| 18, 19 | H1 как подтверждение и структура зоны | `engine._collect_evidence`, `boundaries.compute_bounds` | `test_h4_plus_h1_plus_sr_is_strong` |
| 20 | Пять этапов определения границ | `boundaries.compute_bounds` | `test_zone_has_minimum_width` |
| 21, 22 | S/R — независимый источник, тоже область | `sr.find_sr_areas` | `test_h4_plus_h1_plus_sr_is_strong` |
| 23, 24 | Сила растёт от конфлюенса | `scoring.score_cluster` | `test_more_confirmations_score_higher` |
| 25 | Один факт не считается дважды | `scoring._drop_dependent`, `_dedup_events` | `test_same_event_is_not_counted_twice` |
| 26 | Повторные независимые реакции ценнее | `scoring` (repeat_rejection) | `test_same_event_is_not_counted_twice` |
| 27, 28 | Размер реакции относительно ATR | `wicks.measure_reaction` | `test_reaction_after_wick_is_measured` |
| 29 | Нужно минимум одно подтверждение | `config.min_independent_groups` | `test_h4_alone_is_only_a_candidate` |
| 30 | Несколько H4 рядом = одна зона | `clustering` | `test_near_prices_merge_into_one_cluster` |
| 31 | Совпадение цены не обязано быть точным | `cluster_merge_atr` | `test_merge_distance_scales_with_volatility` |
| 32 | Пересчёт на закрытии H4 | `engine.on_h4_close` | `test_zone_is_not_recreated_within_one_h4` |
| 33 | Внутри H4 зона не пересоздаётся | `engine._last_h4_close` | `test_zone_is_not_recreated_within_one_h4` |
| 34, 35 | Новый H4 не обязан давать зону | `engine.on_h4_close` | `test_quiet_market_creates_no_zones` |
| 36, 37 | Защита от дублирования | `engine._find_existing` | `test_no_duplicate_zones_for_same_area` |
| 38, 39 | Ограниченное расширение зоны | `engine._update_zone`, `boundaries` | `test_zone_width_is_bounded_by_volatility` |
| 40 | Старая зона не становится новой | `engine._find_existing` | `test_repeated_detection_updates_statistics` |
| 41, 42 | Тесты зоны и глубина входа | `lifecycle.ZoneLifecycle` | `test_first_arrival_is_recorded_as_test`, `test_penetration_depth_is_measured` |
| 43, 44 | Прокол ≠ пробой, нужен close | `lifecycle` | `test_wick_pierce_is_not_a_breakout` |
| 45, 46, 47 | Никакого look-ahead bias | `engine._index_upto`, `runner.walk_forward` | `test_zone_creation_uses_only_past_data`, `test_zone_created_before_price_returns` |
| 48, 49 | Score с разными весами | `scoring` | `test_ten_small_wicks_do_not_beat_real_confluence` |
| 50, 51 | Strong / Very Strong по порогам-параметрам | `config.score_strong/score_very_strong` | `test_h4_plus_h1_plus_sr_is_strong` |
| 52 | Структурированный вывод зоны | `models.Zone.to_dict` | `test_export_payload_has_stable_contract` |
| 53 | Reference Price | `boundaries.compute_reference` | `test_reference_price_is_inside_zone` |
| 54 | Хранить происхождение зоны | `models.ScoreBreakdown`, `Zone.evidence` | `test_export_payload_has_stable_contract` |
| 55 | Только H4 → кандидат | `scoring.grade_for` | `test_h4_alone_is_only_a_candidate` |
| 56, 57 | H4+H1 сильнее, H4+H1+S/R — эталон | `scoring` | `test_h4_plus_h1_plus_sr_is_strong` |
| 58 | Только S/R → не зона | `clustering`, `scoring.grade_for` | `test_sr_alone_never_produces_zone` |
| 59 | Никаких LONG/SHORT в зоне | `models`, `exporter` | `test_export_contains_no_trade_instructions` |
| 60, 61 | M5 включается после прихода цены | `m5_confirm.DirectionConfirmer` | `test_m5_does_not_create_zones` |
| 62 | Закрытие M5 за границей | `m5_confirm.on_m5_close` | `test_m5_close_beyond_zone_gives_signal` |
| 63 | Строгий режим с H1 | `DirectionConfirmer(require_h1=True)` | `test_strict_mode_requires_h1_confirmation` |
| 64 | Зона — объект с состоянием | `models.ZoneState` | `test_first_arrival_is_recorded_as_test` |
| 65 | Условия потери силы | `lifecycle` (закрепление за противоположной границей) | `test_single_close_beyond_does_not_kill_zone`, `test_confirmed_breakout_invalidates_zone` |
| 66 | Role reversal не автоматический | `lifecycle` (только BROKEN) | `test_broken_zone_is_not_auto_reversed` |
| 67 | Главное правило вывода новых зон | `engine.on_h4_close` | `test_no_duplicate_zones_for_same_area` |
| 68 | Эталонный пример 4786 | весь конвейер | `test_reference_example_from_spec` |
| 69 | История зоны не переписывается | `engine`, `lifecycle` | `test_zone_created_before_price_returns` |
| 70 | Разделение FIND ZONE / CONFIRM DIRECTION | `engine.py` vs `m5_confirm.py` | `test_m5_does_not_create_zones` |
| 71 | Финальная схема конвейера | `engine._collect_evidence` порядок H4→H1→S/R | весь набор |

## Осознанные решения v1

* **Role reversal не реализован** (ТЗ §66 прямо разрешает отложить): пробитая
  зона получает состояние `broken` и убирается из вывода. Автоматически
  превращать её в противоположную область в первой версии нельзя — это
  исказит честность исторической проверки.
* **Конкретные веса Score подобраны как стартовые** (ТЗ §24: «числа подобрать
  на историческом тестировании»). Все они — параметры в `config.py`
  и переопределяются переменными окружения `GZP_*` без пересборки.
* **Пробой считается только по противоположной границе.** Закрытие свечи над
  областью-поддержкой — это нормальное положение цены, а не пробой; иначе
  каждая зона умирала бы сразу после создания.
