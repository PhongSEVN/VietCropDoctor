-- VietCropDoctor — ClickHouse demo seed (analytics + Grafana business dashboard)
--
-- Fills all 4 OLAP tables with realistic-looking data over the last 30 days
-- (including today) so every chart is populated:
--   predictions      ~480 rows — recent-biased trend, 25 canonical disease classes,
--                                daytime hours, confidence ~ N(0.87, 0.06)
--   chat_events      ~160 rows — real Vietnamese questions, RAG latency 2-15s
--   feedback_events   ~90 rows — ~88% is_correct
--   alerts             12 rows — severe cases in the last 14 days
--
-- IDEMPOTENT: seeded rows are tagged 'seed-%' (session_id / feedback_id) and are
-- deleted before re-inserting. `alerts` has no tag column and is fully truncated
-- (it holds no organic data in dev).
--
-- Run:
--   docker exec -i vcd-clickhouse clickhouse-client --user admin --password secret \
--     --database vietcropdoctor --multiquery < scripts/seed_clickhouse.sql

DELETE FROM predictions     WHERE session_id  LIKE 'seed-%';
DELETE FROM chat_events     WHERE session_id  LIKE 'seed-%';
DELETE FROM feedback_events WHERE feedback_id LIKE 'seed-%';
TRUNCATE TABLE alerts;

-- ---------------------------------------------------------------------------
-- predictions: 480 rows, day offset biased toward today (pow 1.4), hours 7-18.
-- Disease weights per 100: Cà phê 37, Lúa 30, Mía 19, Ngô 14; healthy ~16.
-- ---------------------------------------------------------------------------
INSERT INTO predictions
SELECT
  generateUUIDv4()                                                          AS event_id,
  least(
    now() - toIntervalMinute(5 + rand(1) % 60),
    toDateTime(today() - toUInt16(floor(30 * pow(randUniform(0, 1), 1.4))))
      + toIntervalHour([7,8,8,9,9,10,10,11,13,14,15,15,16,16,17,18][(rand(2) % 16) + 1])
      + toIntervalMinute(rand(3) % 60)
      + toIntervalSecond(rand(4) % 60)
  )                                                                         AS timestamp,
  ['Cafe_benh_dom_rong','Cafe_benh_nam_ri_sat','Cafe_benh_phan_trang',
   'Cafe_benh_phoma','Cafe_benh_sau_ve_bua','Cafe_khoe_manh',
   'Lua_benh_dao_on_co_bong','Lua_benh_dao_on_la','Lua_benh_dom_nau',
   'Lua_benh_sau_gai_hispa','Lua_benh_vang_la_tungro','Lua_khoe_manh',
   'Mia_benh_choi_co','Mia_benh_dom_nau','Mia_benh_kham_la',
   'Mia_benh_ri_sat_nau','Mia_benh_than_den','Mia_benh_thoi_hom',
   'Mia_benh_vang_la','Mia_khoe_manh','Mia_la_kho',
   'Ngo_benh_chay_la_lon','Ngo_benh_dom_la_xam','Ngo_benh_ri_sat',
   'Ngo_khoe_manh']
  [multiIf(
     rand(5) % 100 < 10, 1,  rand(5) % 100 < 15, 2,  rand(5) % 100 < 21, 3,
     rand(5) % 100 < 24, 4,  rand(5) % 100 < 31, 5,  rand(5) % 100 < 37, 6,
     rand(5) % 100 < 43, 7,  rand(5) % 100 < 52, 8,  rand(5) % 100 < 56, 9,
     rand(5) % 100 < 59, 10, rand(5) % 100 < 62, 11, rand(5) % 100 < 67, 12,
     rand(5) % 100 < 68, 13, rand(5) % 100 < 70, 14, rand(5) % 100 < 71, 15,
     rand(5) % 100 < 73, 16, rand(5) % 100 < 78, 17, rand(5) % 100 < 79, 18,
     rand(5) % 100 < 81, 19, rand(5) % 100 < 83, 20, rand(5) % 100 < 86, 21,
     rand(5) % 100 < 90, 22, rand(5) % 100 < 92, 23, rand(5) % 100 < 97, 24,
     25)]                                                                   AS disease,
  round(toFloat32(least(0.99, greatest(0.55, randNormal(0.87, 0.06)))), 4) AS confidence,
  multiIf(
    disease LIKE '%khoe_manh%', 'healthy',
    rand(6) % 100 < 50, 'mild',
    rand(6) % 100 < 85, 'moderate',
    'severe')                                                               AS severity,
  multiIf(
    startsWith(disease, 'Cafe_'), 'Cà phê',
    startsWith(disease, 'Lua_'),  'Lúa',
    startsWith(disease, 'Mia_'),  'Mía',
    'Ngô')                                                                  AS crop,
  concat('seed-', toString(number))                                         AS session_id,
  round(toFloat32(least(2500, greatest(250, randNormal(650, 220)))), 1)    AS latency_ms,
  toUInt8(rand(7) % 100 < 85)                                               AS ensemble_used,
  round(toFloat32(least(0.99, greatest(0.6, randNormal(0.85, 0.08)))), 4)  AS agreement_score,
  concat('seed-user-', toString(1 + rand(8) % 12))                          AS user_id
FROM numbers(480);

-- ---------------------------------------------------------------------------
-- chat_events: 160 rows, realistic Vietnamese follow-up questions.
-- ---------------------------------------------------------------------------
INSERT INTO chat_events
SELECT
  generateUUIDv4()                                                          AS event_id,
  least(
    now() - toIntervalMinute(5 + rand(1) % 60),
    toDateTime(today() - toUInt16(floor(30 * pow(randUniform(0, 1), 1.4))))
      + toIntervalHour([7,8,9,9,10,11,13,14,15,16,17,18][(rand(2) % 12) + 1])
      + toIntervalMinute(rand(3) % 60)
  )                                                                         AS timestamp,
  concat('seed-chat-', toString(number))                                    AS session_id,
  ['Lua_benh_dao_on_la','Lua_benh_dao_on_co_bong','Cafe_benh_dom_rong',
   'Cafe_benh_sau_ve_bua','Cafe_benh_phan_trang','Ngo_benh_ri_sat',
   'Ngo_benh_chay_la_lon','Mia_benh_than_den','Mia_la_kho',
   'Lua_benh_dom_nau'][(rand(4) % 10) + 1]                                  AS disease,
  ['Bệnh này có lây sang ruộng bên cạnh không?',
   'Tôi nên phun thuốc gì để trị bệnh này?',
   'Liều lượng phun thuốc như thế nào cho 1 sào?',
   'Bao lâu sau khi phun thì thấy hiệu quả?',
   'Có cách nào phòng bệnh này cho vụ sau không?',
   'Bệnh này có ảnh hưởng đến năng suất nhiều không?',
   'Thời tiết mưa nhiều có làm bệnh nặng hơn không?',
   'Tôi có nên cắt bỏ lá bị bệnh không?',
   'Giống nào kháng được bệnh này?',
   'Phun thuốc vào lúc nào trong ngày là tốt nhất?',
   'Bệnh này khác gì với bệnh đốm nâu?',
   'Có thuốc sinh học nào thay thế thuốc hóa học không?']
  [(rand(5) % 12) + 1]                                                      AS question,
  toUInt32(380 + rand(6) % 1400)                                            AS answer_len,
  toUInt8(3 + rand(7) % 3)                                                  AS retrieved_chunks,
  round(toFloat32(least(20000, greatest(1800, randNormal(6500, 3200)))), 0) AS latency_ms
FROM numbers(160);

-- ---------------------------------------------------------------------------
-- feedback_events: 90 rows, ~88% confirmed correct.
-- ---------------------------------------------------------------------------
INSERT INTO feedback_events
SELECT
  generateUUIDv4()                                                          AS event_id,
  least(
    now() - toIntervalMinute(5 + rand(1) % 120),
    toDateTime(today() - toUInt16(floor(30 * pow(randUniform(0, 1), 1.3))))
      + toIntervalHour(8 + rand(2) % 11)
      + toIntervalMinute(rand(3) % 60)
  )                                                                         AS timestamp,
  concat('seed-fb-', toString(number))                                      AS feedback_id,
  concat('seed-user-', toString(1 + rand(4) % 12))                          AS user_id,
  ['Lua_benh_dao_on_la','Cafe_benh_dom_rong','Cafe_benh_sau_ve_bua',
   'Ngo_benh_ri_sat','Mia_benh_than_den','Lua_benh_dao_on_co_bong',
   'Cafe_benh_nam_ri_sat','Ngo_benh_chay_la_lon','Mia_la_kho',
   'Lua_benh_dom_nau'][(rand(5) % 10) + 1]                                  AS predicted_disease,
  toUInt8(rand(6) % 100 < 88)                                               AS is_correct,
  if(is_correct = 1, '',
     ['Lua_benh_dom_nau','Cafe_benh_phan_trang','Ngo_benh_dom_la_xam',
      'Mia_benh_vang_la','Lua_benh_vang_la_tungro'][(rand(7) % 5) + 1])     AS corrected_disease,
  if(is_correct = 1, predicted_disease, corrected_disease)                  AS confirmed_label,
  multiIf(
    startsWith(confirmed_label, 'Cafe_'), 'Cà phê',
    startsWith(confirmed_label, 'Lua_'),  'Lúa',
    startsWith(confirmed_label, 'Mia_'),  'Mía',
    'Ngô')                                                                  AS crop
FROM numbers(90);

-- ---------------------------------------------------------------------------
-- alerts: 12 severe cases in the last 14 days.
-- ---------------------------------------------------------------------------
INSERT INTO alerts
SELECT
  generateUUIDv4()                                                          AS alert_id,
  now() - toIntervalHour(rand(1) % 336) - toIntervalMinute(rand(2) % 60)   AS timestamp,
  ['Lua_benh_dao_on_la','Cafe_benh_dom_rong','Mia_benh_than_den',
   'Ngo_benh_ri_sat','Lua_benh_vang_la_tungro','Cafe_benh_sau_ve_bua']
  [(rand(3) % 6) + 1]                                                       AS disease,
  'severe'                                                                  AS severity,
  round(toFloat32(0.75 + (rand(4) % 24) / 100.0), 4)                        AS confidence,
  multiIf(
    startsWith(disease, 'Cafe_'), 'Cà phê',
    startsWith(disease, 'Lua_'),  'Lúa',
    startsWith(disease, 'Mia_'),  'Mía',
    'Ngô')                                                                  AS crop
FROM numbers(12);

-- Summary
SELECT 'predictions (total)'  AS metric, count() AS value FROM predictions
UNION ALL SELECT 'predictions (seed)',   count() FROM predictions WHERE session_id LIKE 'seed-%'
UNION ALL SELECT 'chat_events (total)',  count() FROM chat_events
UNION ALL SELECT 'feedback_events',      count() FROM feedback_events
UNION ALL SELECT 'alerts',               count() FROM alerts;
