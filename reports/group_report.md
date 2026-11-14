# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G03 |
| Challenge | T06 · Dataset Semantic Integrity & Provenance Gate |
| Thành viên (1) + vai trò | Vi Thanh Đức (Core algorithm, Human review, Report) |
| Git URL | https://github.com/viduc2811/K5-L2-Day6-ViThanhDuc-2A202603051-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | ____ |
| Tag `final-24h` (commit) | ____ |
| Deadline (giờ VN) | ____ |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Nhóm huấn luyện/đánh giá mô hình dùng dataset release này và người dùng cuối của mô hình; một release lỗi im lặng làm mô hình học sai nhãn hoặc sai vị trí mà không có cảnh báo.
- Điểm nghẽn cụ thể: Release dataset vẫn là JSON hợp lệ nên các kiểm tra schema thông thường cho qua, nhưng nội dung đã sai: đảo class map, lệch bbox, trùng id, rơi frame, label map cũ.
- Đầu vào → đầu ra: Đầu vào: 20 release ứng viên (annotations.json + release_meta.json) cùng parent v1.0. Đầu ra: release_decisions.csv (release_id, decision PASS/HOLD, root_cause) và decision.json.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): Release có ít nhất một vi phạm trong 5 phép kiểm thì HOLD (trả lại để sửa, REWORK); không vi phạm thì PASS. Cả đợt: có release bị chặn thì HOLD (SILENT_DEFECTS_FOUND), không có thì GO. Chốt BBOX_SHIFT_PX = 1.0 trước khi chạy eval.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): Dữ liệu là synthetic (CC0), không chứa người hay biển số thật. Ngưỡng 1.0 px dựa trên các release dev; cần chủ dataset xác nhận khi dùng dữ liệu thật.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev |10 release (r01–r10) |synthetic: tools/make_fixtures.py (seed 42) |CC0-1.0 |có |
| eval / heldout |10 release (r11–r20) |synthetic: tools/make_fixtures.py (seed 42) |CC0-1.0 |có |

- Schema & class mapping: COCO annotations; parent v1.0 dùng label map lm-3 (1 car, 2 pedestrian, 3 motorbike, 4 sign, 5 truck); lm-2 là bản cũ chỉ 4 class.
- Seed: 42 · Cách chia split (theo scene/group/segment?): Seed 42 · chia theo release (dev r01–r10, eval r11–r20), theo cột split trong releases.csv.
- `manifest.csv` verified (sha256): có / không — lệnh: `python -m tools.verify_manifests` kết quả: 14 manifests, 0 failing.
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: không dùng dữ liệu thật; chỉ fixtures synthetic.

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: Great Expectations 1.x (ValidationDefinition, Checkpoint) 
https://docs.greatexpectations.io/docs/reference/api/ValidationDefinition_class 
.../Checkpoint_class: mượn ý tưởng cổng kiểm theo invariant, gom nhiều kiểm tra rồi ra quyết định. 
DVC https://doc.dvc.org/user-guide: theo dõi dữ liệu bằng hash cùng Git, nên nhóm kiểm provenance bằng parent_sha256. Croissant 1.1
https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html: metadata dataset có provenance
Ngày xem: 14/11/2025
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): load (releases.csv, label_maps.json, parent v1.0) → process (5 phép kiểm cho từng release, sinh decision và root_cause) → rank (hàng đợi review theo score = số vi phạm) → review (người duyệt approve/edit/reject, ghi audit log) → decide (GO/HOLD + reason_code + owner) → out/poc/release_decisions.csv, decision.json.
- Thành phần offline (model/weights + checksum + license nếu có): Không dùng model hay weights; chỉ thư viện Python chuẩn và pandas, chạy hoàn toàn offline (--offline).
- Trade-offs đã cân nhắc: Ngưỡng bbox 1.0 px: thấp hơn thì chặn nhầm release sạch có nhiễu lành tính, cao hơn thì lọt lỗi lệch nhỏ. Ghép bbox "gần nhất" đơn giản và nhanh nhưng có thể sai khi nhiều bbox sát nhau.

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): src/baseline_t06.py: chỉ parse annotations.json và release_meta.json, kiểm 3 khóa bắt buộc và file ảnh tồn tại; không so semantic invariants, không so với parent. Parse được thì PASS. Config hash 2596bf6561fc.
- PoC (mô tả, version/config, commit): src/pipeline.py: 5 phép kiểm (id trùng, ít ảnh hơn parent, lệch bbox trung bình > 1.0 px, parent_sha256 sai, categories khác label map), hàng đợi review, override có audit, quyết định có reason_code và owner. Config hash f58166a1361c.
- Cùng budget / cùng heldout / cùng seed: xác nhận: cùng dữ liệu (fixtures/t06_release_gate), seed 42, offline, B = 20.

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Silent-defect Detection F1 (release, eval) | chưa có GT | chưa có GT | giảng viên chấm bằng GT; higher |
| Hard-slice: class_swap (release bị chặn) | 0/2 | 2/2  | tự kiểm; N= 2 |
| Review@B / miss / FP | không có review | 20 duyệt, 20 approve | tự kiểm: PoC chặn 10/20; B=20 |
| Runtime / 100 items | 0.91 s| 1.93 s | 0.1817 s và 0.3852 s cho 20 release; CPU Windows 10, Python 3.11.9 |

## 05 · Evaluation protocol/metric_contrac

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: Silent-defect Detection F1 = 2·P·R / (P + R) trên release thuộc split eval; positive = release lỗi bị chặn; TP = release lỗi bị HOLD; FP = release sạch bị chặn; FN = release lỗi bị PASS; đơn vị = release (xem `reportst.md`)
- Threshold / budget B / K và lúc chốt: BBOX_SHIFT_PX = 1.0, B = 20; chốt 14/11/2026 16:16
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: N = 10 release mỗi split, rất nhỏ; kết quả chỉ mang tính chỉ báo; khoảng tin cậy Wilson do evaluator của giảng viên in ra.
- Lệnh evaluate chính xác: `python -m src.evaluate --track t06 --pred out/poc/release_decisions.csv --run-name poc --out reports/metrics_poc.json`

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
|root cause: class_swap |2 |chặn 0 |chặn 2 |tự kiểm, chưa có GT |
|root cause: bbox_shift |2 |chặn 0 |chặn 2 |tự kiểm, chưa có GT |
|root cause: id_collision |2 |chặn 0 |chặn 2 |tự kiểm, chưa có GT |
|root cause: dropped_frames |2 |chặn 0 |chặn 2 |tự kiểm, chưa có GT |
|root cause: stale_map |2 |chặn 0 |chặn 2 |tự kiểm, chưa có GT |

- Failure case 1 (ảnh/metadata + root cause): Release r07, file fixtures/t06_release_gate/releases/candidates/r07/annotations.json. Parent v1.0 có 1 = car, 2 = pedestrian; r07 có 1 = pedestrian, 2 = car. JSON vẫn hợp lệ nên baseline cho PASS; PoC so categories với label map và gán class_swap.
- Failure case 2: Release r05, bbox lệch trung bình 8.18 px so với parent; ví dụ annotation 671 (image 97) x từ 164.51 thành 193.59, y từ 116.84 thành 130.21. Baseline cho PASS; PoC gán bbox_shift.
- Latency / compute (máy, CPU, ms/item): PoC 0.3852 s cho 20 release (≈ 1.93 s / 100 release), baseline 0.1817 s; Windows 10, Python 3.11.9

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): out/poc/review_queue.csv, B = 20, xếp theo score = số vi phạm giảm dần nên release bị cờ nằm trên cùng.
- Cách override + audit log (`out/audit_log.jsonl`): Reviewer điền reviewer, reviewer_decision (approve/reject/edit/escalate/skip), review_note (và override_value nếu edit/reject) vào out/poc/review_queue_reviewed.csv; review() đọc file này; edit/reject kèm giá trị mới được áp qua apply_overrides và ghi vào audit log (ai, khi nào, trước/sau, lý do). Lần review thực tế: duyệt cả 20 release, đều approve, nên không có override đổi quyết định; review() ghi thêm 20 dòng review:approve vào out/poc/audit_log.jsonl làm dấu vết.
- Decision policy + `reason_code` + owner: Có ít nhất một release bị chặn thì HOLD với reason_code SILENT_DEFECTS_FOUND; không có thì GO với ALL_RELEASES_CLEAN; owner = "Vi Thanh Duc - reviewer" (từ configs/lab.yaml); bằng chứng trong decision.json.
- Khi nào HOLD/REWORK thay vì tự động release: Khi bất kỳ phép kiểm nào trong 5 phép báo vi phạm; release bị chặn trả lại đội tạo release để sửa (REWORK) rồi xem xét lại; người review đối chiếu annotations.json với parent trước khi xác nhận.

## 08 · Reproduce & tests

```bash
.\.venv\Scripts\python.exe -m src.main --track t06 --pipeline src.baseline_t06 --output out/baseline --run-name baseline --offline --seed 42
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t06 --output out/poc --run-name poc --offline --seed 42
.\.venv\Scripts\python.exe -m src.evaluate --track t06 --pred out/poc/release_decisions.csv --run-name poc --out reports/metrics_poc.json   # giảng viên chạy (cần gt/)
.\.venv\Scripts\python.exe -m pytest -q
```

- Output của `pytest -q`: 1 failed, các test còn lại pass hoặc skip (test cần gt/ bị skip). Test fail là tests/test_cli.py::test_template_pipeline_fails_clearly_not_silently: nó kiểm bản pipeline.py mẫu chưa implement phải thoát mã 3, chạy với track t02. Sau khi nhóm implement T06, pipeline thoát mã 2 vì không thấy releases.csv của t02. Không ảnh hưởng PoC T06 (status=0) và 5 test T06 của nhóm (pass).
- Máy / CPU / OS / Python: Windows 10 (10.0.19045) · Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz · Python 3.11.9 · git sha:

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: Dữ liệu là synthetic (CC0-1.0), không chứa người hay biển số thật, nên rủi ro PII thấp trong lab này. Với dữ liệu thật cần kiểm quyền sử dụng và PII trước khi đưa vào gate.
- Điều chưa biết; false alarms; nếu scale 10× thì sao: Chưa có GT trên máy nhóm nên không biết tỉ lệ chặn nhầm thật. Khi scale 10×, ghép bbox "gần nhất" cho mỗi annotation chậm theo số bbox mỗi ảnh; ngưỡng 1 px dựa trên dữ liệu synthetic có thể không hợp với dữ liệu thật. N = 10 release mỗi split nên kết quả chỉ mang tính chỉ báo.
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: Đây chỉ là cổng kiểm tính toàn vẹn dataset, không phải đánh giá tuân thủ pháp luật; giả định về PII và license cần chủ dữ liệu hoặc DPO/legal xác nhận.
- Kế hoạch cải tiến: Xuất metadata Croissant 1.1 kèm provenance; thêm kiểm bbox nằm trong ảnh và frame_index liên tục; thêm round-trip COCO↔YOLO và test rollback theo hash.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Vi Thanh Đức | viduc28112002@gmail.com | Core algorithm (src/pipeline.py), baseline (src/baseline_t06.py), test (tests/test_t06_gate.py), human review, báo cáo | |có |


## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
|https://docs.greatexpectations.io/docs/reference/api/ValidationDefinition_class | 14/11/2026 |Gắn một batch dữ liệu với bộ kiểm tra để chạy validation, nhóm mượn ý tưởng cổng kiểm theo invariant. |
|https://doc.dvc.org/user-guide|14/11/2026|nhóm mượn ý tưởng kiểm provenance bằng sha256 của parent.|


**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
