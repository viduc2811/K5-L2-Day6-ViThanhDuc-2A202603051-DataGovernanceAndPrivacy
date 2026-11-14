# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T06 · Dataset Semantic Integrity & Provenance Gate |
| Primary metric (tên đúng như evaluator in ra) | Silent-defect Detection F1|
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | release |
| Công thức + numerator / denominator |F1 = 2·P·R / (P + R) trên các release split eval. Positive = release lỗi bị chặn. TP = release lỗi bị HOLD/REWORK; FP = release sạch bị chặn; FN = release lỗi bị PASS. P = TP/(TP+FP), R = TP/(TP+FN) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) |Theo release_id (khớp chính xác, mỗi release_id xuất hiện đúng 1 lần trong release_decisions.csv) |
| Candidate pool cố định |20 release ứng viên (releases.csv): 10 dev (r01–r10) + 10 eval (r11–r20); parent releases/v1.0 |
| Review budget B / K |B = 20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | BBOX_SHIFT_PX = 1.0 (px): release bị cờ bbox_shift khi lệch bbox trung bình so với parent lớn hơn 1.0 px. Chọn khi quan sát release dev (r01–r10), không dùng eval. Các quy tắc còn lại không có ngưỡng: trùng id, ít ảnh hơn parent, categories khác label map, parent_sha256 sai|
| Eval split (không dùng để tune) | eval (r11–r20), không dùng để chọn ngưỡng hay sửa quy tắc|
| Chỉ số lỗi xấu (miss / false alarm / false reject) |Miss = release lỗi bị lọt (recall thấp); false alarm = release sạch bị chặn nhầm (false-block rate) |
| Slices sẽ báo cáo (≥2) |(1) theo root cause: class_swap, bbox_shift, id_collision, dropped_frames, stale_map; (2) dev so với eval |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) |N = 10 release mỗi split, rất nhỏ: báo kèm khoảng tin cậy Wilson do evaluator của giảng viên in ra, và nêu rõ kết luận chỉ mang tính chỉ báo |
| Ngày giờ chốt + người chốt | 14/11/2026 + Vi Thanh Đức | 

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
