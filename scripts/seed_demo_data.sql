-- ============================================================================
-- VietCropDoctor — Demo seed data
-- Fills the DB with realistic farmer cases, expert replies, internal notes,
-- admin audit logs and notifications so the demo dashboards look populated.
--
-- IDEMPOTENT: all seeded rows are tagged (chat/feedback via session_id LIKE
-- 'seed-%', audit via user_agent='seed-script', notifications via created_by =
-- admin + known titles). Re-running deletes the previous seed first.
--
-- Run:  docker cp scripts/seed_demo_data.sql vcd-postgres:/tmp/seed.sql
--       docker exec vcd-postgres psql -U vcdauth -d vcd_auth -f /tmp/seed.sql
-- ============================================================================
SET client_encoding TO 'UTF8';

DO $$
DECLARE
    v_user2  uuid;  -- farmer
    v_user3  uuid;  -- farmer
    v_user1  uuid;  -- agronomist (expert)
    v_agro1  uuid;
    v_agro2  uuid;
    v_admin  uuid;  -- phongnguyen

    farmers  uuid[];
    experts  uuid[];

    imgs text[] := array[
        'http://localhost:9002/vcd-uploads/Lua_benh_dao_on_co_bong/2026-06-14/376a8169-2966-4060-aeac-7ea4b9b884e4.jpg',
        'http://localhost:9002/vcd-uploads/Mia_la_kho/2026-06-23/5f4b650d-fe5a-4182-9db5-2e11571181bb.jpg',
        'http://localhost:9002/vcd-uploads/Mia_benh_than_den/2026-06-21/b4e21e59-40ff-4d87-8f8f-b7adb1f3d5c3.jpg',
        'http://localhost:9002/vcd-uploads/Cafe_benh_sau_ve_bua/2026-06-21/9680e041-e7c8-40b7-a5e2-91677e553817.jpg',
        'http://localhost:9002/vcd-uploads/Cafe_benh_dom_rong/2026-06-21/26fb21b8-76e6-4aef-8261-db57976339b7.jpg',
        'http://localhost:9002/vcd-uploads/Ngo_benh_ri_sat/2026-06-13/97880a95-2984-4dbf-9d86-4913e2d57ff7.jpg',
        'http://localhost:9002/vcd-uploads/Cafe_benh_phan_trang/2026-06-14/90c1a74a-b365-464e-9e2b-0205794b38d1.jpg',
        'http://localhost:9002/vcd-uploads/Lua_benh_dao_on_co_bong/2026-06-14/1d4b3698-26b6-4203-b2aa-19a02762f307.jpg',
        'http://localhost:9002/vcd-uploads/Ngo_benh_ri_sat/2026-06-23/da30ad48-d5a2-4d5a-908c-40ca39630995.jpg',
        'http://localhost:9002/vcd-uploads/Cafe_khoe_manh/2026-06-14/e4dd59ce-58d2-4440-a0e3-f5299a21e001.jpg',
        'http://localhost:9002/vcd-uploads/Mia_benh_than_den/2026-06-21/5eeeba64-5d92-4d2d-9d57-004d0d084495.jpg',
        'http://localhost:9002/vcd-uploads/Ngo_benh_ri_sat/2026-06-21/99beed90-34ef-48dd-bb3b-cac1ea7ea0c4.jpg'
    ];

    statuses    text[] := array['answered','answered','answered','answered','in_progress','in_progress','pending','answered_irrelevant'];
    priorities  text[] := array['normal','normal','high','low','urgent','normal'];

    e_comments  text[] := array[
        'Tôi đã xem kỹ ảnh. Triệu chứng khá điển hình, anh/chị yên tâm xử lý theo hướng dẫn bên dưới.',
        'Đúng như AI dự đoán. Cần xử lý sớm để tránh lây lan sang các cây xung quanh.',
        'Vết bệnh đang ở giai đoạn đầu, nếu xử lý ngay thì khả năng phục hồi rất cao.',
        'Lưu ý kết hợp cải tạo đất và thoát nước tốt, không chỉ phun thuốc.',
        'Cây vẫn còn khỏe, chủ yếu là phòng ngừa. Theo dõi thêm 1 tuần.'
    ];
    e_treatments text[] := array[
        'Phun thuốc gốc đồng theo liều khuyến cáo, 7 ngày/lần, lặp lại 2-3 lần. Tỉa bỏ lá bệnh nặng và tiêu hủy xa vườn.',
        'Sử dụng thuốc đặc trị nấm, kết hợp bón cân đối NPK, tăng kali để cây cứng cáp. Tránh tưới đẫm vào chiều tối.',
        'Vệ sinh đồng ruộng, thu gom tàn dư cây bệnh. Luân canh với cây khác họ trong vụ tới để cắt nguồn bệnh.',
        'Bón vôi cải tạo đất, đảm bảo thoát nước. Phun phòng định kỳ vào đầu mùa mưa.'
    ];
    e_notes     text[] := array[
        'Hộ này đã hỏi 2 lần trong tháng, nên ưu tiên hỗ trợ.',
        'Cần xác minh lại vùng trồng — nghi ngờ sai vùng khí hậu.',
        'Ảnh hơi mờ nhưng đủ để kết luận. Đã ghi nhận.',
        'Chuyển ca này cho chuyên gia cà phê nếu tái phát.'
    ];

    n int := 22;
    i int;
    v_img text; v_disease text; v_conf real;
    v_farmer uuid; v_expert uuid;
    v_status text; v_priority text; v_confirmed text; v_corrected text;
    v_is_correct boolean; v_irrelevant boolean;
    v_session text; v_fb uuid;
    v_base timestamptz;
    v_expert_name text;
    v_answer_expert text;
BEGIN
    SELECT id INTO v_user2 FROM users WHERE username='user2';
    SELECT id INTO v_user3 FROM users WHERE username='user3';
    SELECT id INTO v_user1 FROM users WHERE username='user1';
    SELECT id INTO v_agro1 FROM users WHERE username='agro_25cff815';
    SELECT id INTO v_agro2 FROM users WHERE username='agro_a812873d';
    SELECT id INTO v_admin FROM users WHERE username='phongnguyen';

    farmers := array[v_user2, v_user3];
    experts := array[v_user1, v_agro1, v_agro2];

    -- Prettier display names for the demo (only fills blanks / ugly placeholders).
    UPDATE users SET full_name='Nguyễn Văn Phong'  WHERE username='phongnguyen'   AND (full_name IS NULL OR full_name='');
    UPDATE users SET full_name='Trần Thị Hoa'       WHERE username='user3'         AND (full_name IS NULL OR full_name='');
    UPDATE users SET full_name='KS. Lê Văn Tâm'     WHERE username='user1';
    UPDATE users SET full_name='KS. Phạm Thị Mai'   WHERE username='agro_25cff815' AND (full_name IS NULL OR full_name='');
    UPDATE users SET full_name='KS. Hoàng Văn Nam'  WHERE username='agro_a812873d' AND (full_name IS NULL OR full_name='');

    -- ---- Clean previous seed (cascade removes expert_responses + internal_notes) ----
    DELETE FROM chat_messages WHERE session_id LIKE 'seed-%';
    DELETE FROM feedback      WHERE session_id LIKE 'seed-%';
    DELETE FROM audit_logs    WHERE user_agent = 'seed-script';
    DELETE FROM notifications WHERE created_by = v_admin
        AND title IN ('Cập nhật hệ thống v1.2','Cảnh báo dịch đạo ôn cổ bông',
                      'Lịch bảo trì máy chủ', 'Tài liệu mới cho chuyên gia');

    -- ---- Cases ----------------------------------------------------------------
    FOR i IN 1..n LOOP
        v_img     := imgs[((i-1) % array_length(imgs,1)) + 1];
        v_disease := split_part(v_img, '/', 5);
        v_conf    := round((0.55 + random()*0.43)::numeric, 3)::real;
        v_farmer  := farmers[((i-1) % 2) + 1];
        v_expert  := experts[((i-1) % 3) + 1];
        v_status  := statuses[((i-1) % array_length(statuses,1)) + 1];
        v_priority:= priorities[((i-1) % array_length(priorities,1)) + 1];
        v_session := 'seed-' || gen_random_uuid();
        v_base    := now() - ((random()*20)::int) * interval '1 day' - ((random()*11)::int) * interval '1 hour';

        v_irrelevant := false;
        v_corrected  := NULL;
        v_confirmed  := v_disease;

        IF v_status = 'answered_irrelevant' THEN
            v_status := 'answered'; v_irrelevant := true;
        END IF;

        -- ~1 in 5 answered cases: expert corrects the label
        IF v_status = 'answered' AND NOT v_irrelevant AND (i % 5 = 0) THEN
            v_confirmed := imgs[((i) % array_length(imgs,1)) + 1];
            v_confirmed := split_part(v_confirmed, '/', 5);
            v_corrected := v_confirmed;
        END IF;
        v_is_correct := (v_confirmed = v_disease);

        SELECT full_name INTO v_expert_name FROM users WHERE id = v_expert;

        -- Diagnosis chat row (init) + a follow-up question, in the farmer's session
        INSERT INTO chat_messages (user_id, session_id, disease, question, answer, image_url, created_at)
        VALUES (v_farmer, v_session, v_disease,
                'Phân tích ảnh: ' || v_disease,
                'Ảnh của bạn cho thấy dấu hiệu của **' || v_disease || '** (độ tin cậy ' ||
                    round((v_conf*100)::numeric,1) || '%). Bạn muốn biết thêm về triệu chứng, nguyên nhân hay cách phòng trị?',
                v_img, v_base);

        IF NOT v_irrelevant THEN
            INSERT INTO chat_messages (user_id, session_id, disease, question, answer, image_url, created_at)
            VALUES (v_farmer, v_session, v_disease,
                    'Bệnh này nên xử lý như thế nào ạ?',
                    'Bạn nên cách ly cây bệnh, vệ sinh vườn và phun thuốc đặc trị theo liều khuyến cáo. ' ||
                    'Theo tài liệu, cần xử lý sớm trong 5-7 ngày đầu để đạt hiệu quả cao nhất.',
                    NULL, v_base + interval '3 minutes');
        END IF;

        -- Feedback / case row
        INSERT INTO feedback (user_id, session_id, image_url, predicted_disease, predicted_confidence,
                              is_correct, corrected_disease, confirmed_label, comment, status, priority,
                              assignee_id, sla_due_at, is_irrelevant, created_at, updated_at)
        VALUES (v_farmer, v_session, v_img, v_disease, v_conf,
                v_is_correct, v_corrected, v_confirmed,
                CASE WHEN v_irrelevant THEN 'Ảnh này không rõ là lá cây trồng.'
                     ELSE 'Nhờ chuyên gia xác nhận giúp em với ạ.' END,
                v_status, v_priority,
                CASE WHEN v_status IN ('answered','in_progress') THEN v_expert ELSE NULL END,
                v_base + interval '24 hours', v_irrelevant,
                v_base, v_base + ((random()*6)::int) * interval '1 hour')
        RETURNING id INTO v_fb;

        -- Expert response (answered/in_progress, not irrelevant)
        IF v_status IN ('answered','in_progress') AND NOT v_irrelevant THEN
            INSERT INTO expert_responses (feedback_id, expert_id, comment, diagnosis, treatment, created_at)
            VALUES (v_fb, v_expert,
                    e_comments[((i-1) % array_length(e_comments,1)) + 1],
                    v_confirmed,
                    e_treatments[((i-1) % array_length(e_treatments,1)) + 1],
                    v_base + ((2 + random()*8)::int) * interval '1 hour');

            -- Loop-back: push the expert reply into the farmer's chat (answered only)
            IF v_status = 'answered' THEN
                v_answer_expert :=
                    e_comments[((i-1) % array_length(e_comments,1)) + 1] || E'\n\n' ||
                    '**Chẩn đoán xác nhận:** ' || v_confirmed || E'\n\n' ||
                    '**Hướng xử lý đề xuất:** ' || e_treatments[((i-1) % array_length(e_treatments,1)) + 1] || E'\n\n' ||
                    '— ' || COALESCE(v_expert_name, 'Chuyên gia');
                INSERT INTO chat_messages (user_id, session_id, disease, question, answer, image_url, created_at)
                VALUES (v_farmer, v_session, v_confirmed, '__EXPERT_REPLY__', v_answer_expert, NULL,
                        v_base + ((3 + random()*8)::int) * interval '1 hour');
            END IF;
        END IF;

        -- Internal note on ~1 in 3 cases
        IF (i % 3 = 0) AND v_status <> 'pending' THEN
            INSERT INTO internal_notes (feedback_id, expert_id, note, created_at)
            VALUES (v_fb, v_expert, e_notes[((i-1) % array_length(e_notes,1)) + 1],
                    v_base + interval '1 hour');
        END IF;
    END LOOP;

    -- ---- Admin notifications --------------------------------------------------
    INSERT INTO notifications (title, body, audience, group_role, sent_count, created_by, created_at) VALUES
        ('Cập nhật hệ thống v1.2', 'Hệ thống đã bổ sung tính năng phản hồi chuyên gia ngay trong khung chat.', 'all', NULL, 154, v_admin, now() - interval '2 days'),
        ('Cảnh báo dịch đạo ôn cổ bông', 'Phát hiện nhiều ca bệnh đạo ôn cổ bông trên lúa tại khu vực ĐBSCL. Bà con lưu ý phun phòng.', 'group', 'farmer', 132, v_admin, now() - interval '5 days'),
        ('Lịch bảo trì máy chủ', 'Hệ thống bảo trì từ 23h-24h ngày Chủ nhật. Mong bà con thông cảm.', 'all', NULL, 154, v_admin, now() - interval '8 days'),
        ('Tài liệu mới cho chuyên gia', 'Đã cập nhật bộ tài liệu chẩn đoán bệnh cà phê. Mời các chuyên gia tham khảo.', 'group', 'agronomist', 3, v_admin, now() - interval '1 day');

    -- ---- Admin audit logs -----------------------------------------------------
    INSERT INTO audit_logs (actor_id, actor_name, action, target, ip, user_agent, created_at) VALUES
        (v_admin, 'phongnguyen', 'user.role_update',        'user2 → agronomist',      '10.0.0.21', 'seed-script', now() - interval '1 day'),
        (v_admin, 'phongnguyen', 'model.activate',          'EfficientNet-B0 v3',      '10.0.0.21', 'seed-script', now() - interval '2 days'),
        (v_admin, 'phongnguyen', 'model.retrain_trigger',   'ensemble retrain #12',    '10.0.0.21', 'seed-script', now() - interval '3 days'),
        (v_admin, 'phongnguyen', 'expert.assign',           'KS. Lê Văn Tâm → cà phê', '10.0.0.21', 'seed-script', now() - interval '3 days'),
        (v_admin, 'phongnguyen', 'notification.broadcast',  'Cảnh báo dịch đạo ôn',    '10.0.0.21', 'seed-script', now() - interval '5 days'),
        (v_admin, 'phongnguyen', 'user.deactivate',         'tok_249cf3d2',            '10.0.0.21', 'seed-script', now() - interval '6 days'),
        (v_admin, 'phongnguyen', 'report.export',           'báo cáo tháng 6',         '10.0.0.21', 'seed-script', now() - interval '7 days'),
        (v_admin, 'phongnguyen', 'kafka.inspect',           'topic disease.detected',  '10.0.0.21', 'seed-script', now() - interval '9 days');

    RAISE NOTICE 'Seed completed: % cases created for farmers user2/user3.', n;
END $$;

-- ---- Summary ----------------------------------------------------------------
SELECT 'feedback'        AS table, count(*) FROM feedback
UNION ALL SELECT 'feedback (seed)',      count(*) FROM feedback WHERE session_id LIKE 'seed-%'
UNION ALL SELECT 'chat_messages',        count(*) FROM chat_messages
UNION ALL SELECT 'expert_responses',     count(*) FROM expert_responses
UNION ALL SELECT 'internal_notes',       count(*) FROM internal_notes
UNION ALL SELECT 'notifications',        count(*) FROM notifications
UNION ALL SELECT 'audit_logs',           count(*) FROM audit_logs;
