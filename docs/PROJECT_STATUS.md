# EchoRole — trạng thái dự án và hướng dẫn bàn giao

**Cập nhật:** 2026-11-14

**Mục đích:** Tóm tắt khả năng hiện có, ranh giới kiến trúc, trạng thái kiểm thử và việc cần tiếp tục. Đây là ảnh chụp trạng thái tại ngày cập nhật, không thay thế hợp đồng API hoặc tài liệu kiến trúc chuẩn.

## 1. Tóm tắt nhanh

EchoRole là ứng dụng luyện phỏng vấn và giao tiếp theo kịch bản. Người dùng chọn tình huống, đối thoại bằng giọng nói hoặc gõ văn bản với một hội đồng gồm hai AI, rồi nhận đánh giá định lượng và phản hồi của Coach.

| Hạng mục | Trạng thái |
|---|---|
| Backend | FastAPI, SQLite/SQLAlchemy/Alembic; API phiên luyện tập, speech, evaluation |
| Frontend | React + TypeScript + Vite; gọi backend thật mặc định, MSW bật theo `VITE_USE_MOCKS=true` |
| Đối thoại | Hai persona AI trong mỗi kịch bản; có TTS trên trình duyệt |
| LLM | Ollama hoặc OpenAI-compatible theo `LLM_PROVIDER` |
| Speech-to-text | faster-whisper chạy cục bộ; tiếng Anh; audio được xử lý trong bộ nhớ |
| Đánh giá | Coach riêng, rubric 6 tiêu chí; metrics tính riêng; backend tính điểm tổng |
| Release | Tag `v0.1.0-mvp` đã tồn tại; benchmark ghi rõ vẫn còn tiêu chí chưa đạt/chưa đo |
| Groq hiện tại | Đã cấu hình cục bộ nhưng **chưa xác nhận E2E live** sau các sửa đổi mới nhất |

## 2. Trạng thái Git và thay đổi gần nhất

Tại lúc lập tài liệu:

- Nhánh hiện tại: `main`; commit đầu nhánh là `14b8071` (`fix: distinguish cloud LLM model and endpoint errors`).
- Nhánh local báo ahead 19 commit so với `origin/main`.
- Worktree có thay đổi chưa commit ở client LLM, test adapter, error mapping, test frontend và các tài liệu vừa đồng bộ. `.env` bị Git ignore; không đưa API key vào tài liệu hoặc commit.
- Những thay đổi chưa commit liên quan tới lần xử lý `LLM_BAD_OUTPUT`:
  - OpenAI-compatible client gửi `max_completion_tokens` theo API Groq hiện hành.
  - Giao diện dùng thông báo an toàn do backend trả cho lỗi LLM thay vì luôn thay bằng câu chung.
  - `.env` local hiện chọn `openai/gpt-oss-20b`, đặt `ROLEPLAY_MAX_TOKENS=1024`; cần restart backend để nạp cấu hình.
- Lần chạy gần nhất trước các thay đổi này, người dùng gặp `LLM_BAD_OUTPUT`. Chưa có lần gọi Groq live xác nhận sau khi đổi tham số/token budget.

Trước khi phát hành tiếp theo, rà soát `git status`, chạy CI đầy đủ, rồi commit có chủ đích. Không stage `.env`.

## 3. Công nghệ và cấu trúc

- **Backend:** Python 3.11+, FastAPI, Pydantic, HTTPX; SQLAlchemy 2 và SQLite; Alembic.
- **Frontend:** React 19, TypeScript, Vite, Vitest, ESLint; MSW cho phát triển UI với mocks.
- **Cấu trúc backend:** `core` (config/errors/db), `llm`, `roleplay`, `simulation`, `speech`, `evaluation`, `schemas`, `models`.
- **Cấu trúc frontend:** `api`, `features/scenarios`, `features/session`, `features/feedback`, `mocks`, `utils`.
- **Hợp đồng API:** phiên bản `0.4.0`; định nghĩa chuẩn ở [API_CONTRACTS.md](api-contracts/API_CONTRACTS.md).
- **Version ứng dụng:** `0.1.0`; tag `v0.1.0-mvp` có trong repository.
- **Kiến trúc:** monolith FastAPI theo module; giao tiếp frontend/backend qua REST; LLM nhận lịch sử tường minh từ DB, không giữ state phiên ứng dụng.
- **Xác thực:** chưa có user login/authentication trong MVP.

Tài liệu nền:

- [README.md](../README.md) — cài đặt/chạy/CI.
- [system-architecture.md](architecture/system-architecture.md) — ranh giới module và luồng hệ thống.
- [database-schema.md](architecture/database-schema.md) — schema và bất biến dữ liệu.
- [LLM_BENCHMARK.md](architecture/LLM_BENCHMARK.md) — số đo và giới hạn benchmark hiện có.

## 4. Chức năng đang có

### 4.1 Kịch bản và phiên luyện tập

Ba kịch bản được seed từ JSON khi backend khởi động:

| Slug | Tình huống | Độ khó | Số lượt ứng viên tối đa | Panel |
|---|---|---:|---:|---|
| `behavioral-interview` | Behavioral Job Interview | 2 | 8 | Alex — Engineering Manager; Sarah — People Partner |
| `customer-escalation` | Customer Escalation | 3 | 8 | Morgan — Customer Operations Director; Priya — Customer Success Partner |
| `project-pitch` | Project Pitch | 2 | 6 | Alex — Chief Operating Officer; Nina — Finance Partner |

Mỗi persona có chức danh, focus area, voice gender và prompt riêng. Khi bắt đầu, persona thứ nhất giới thiệu bối cảnh; persona thứ hai đặt câu hỏi mở đầu. Các lượt tiếp theo luân phiên hoặc tung hứng tùy lượt hội thoại.

### 4.2 Panel Agents và transcript

- RoleplayAgent tạo một hoặc hai câu trả lời AI trong mỗi nhịp; lịch sử gắn nhãn tên/chức danh để tránh lặp.
- Transcript lưu `speaker_id`/`speaker_name` nullable để tương thích dữ liệu cũ.
- Response mới có `interviewer_turns[]`; `interviewer_turn` vẫn giữ để tương thích client cũ.
- Giao diện phân biệt AI #1/AI #2 bằng nhãn/màu và xếp hàng TTS từng lượt; ưu tiên hai giọng tiếng Anh khác nhau nếu trình duyệt có sẵn.

### 4.3 Giọng nói và văn bản

- Push-to-talk dùng `MediaRecorder`; có thể xem/sửa transcript trước khi gửi, không tự động gửi sau khi nhận dạng.
- Có typed fallback khi không dùng được microphone; giới hạn thời lượng và dung lượng cấu hình được.
- Audio gửi tới backend dạng bytes, giải mã/nhận dạng trong bộ nhớ; **không lưu file audio xuống ổ đĩa**.
- faster-whisper chạy cục bộ, cấu hình model/device/compute type qua `.env`; hiện mô hình benchmark là `tiny.en`, CPU/int8.
- TTS chạy bằng Web Speech API của trình duyệt; không có TTS server-side.

### 4.4 Đánh giá sau phiên

- Phiên phải kết thúc và có ít nhất một lượt ứng viên mới được đánh giá.
- Evaluation chạy bất đồng bộ; frontend poll trạng thái và hỗ trợ retry khi thất bại.
- Coach nhận transcript, nhiệm vụ kịch bản và rubric; transcript ghi rõ danh tính panel.
- DeliveryMetrics được tính riêng bằng code, **không truyền cho EvaluationCoach**.
- Rubric có sáu tiêu chí: relevance 25%, structure 20%, clarity 20%, composure 15%, conciseness 10%, language accuracy 10%.
- Backend tính điểm tổng: `(sum(weight_percent * score) + 5) // 10`; không tin điểm tổng do model tạo.
- UI hiển thị hai phần riêng: phản hồi Coach và Delivery Metrics.

## 5. API hiện có

Base URL: `http://localhost:8000/api/v1`.

| Nhóm | Endpoint chính |
|---|---|
| Health | `GET /health` |
| Kịch bản | `GET /scenarios`, `GET /scenarios/{scenario_id}` |
| Phiên | `POST /sessions`, `GET /sessions`, `GET /sessions/{session_id}` |
| Đối thoại | `POST /sessions/{session_id}/start`, `POST /sessions/{session_id}/turns`, `GET /sessions/{session_id}/turns`, `POST /sessions/{session_id}/end` |
| Speech | `GET /speech/status`, `POST /speech/transcribe` |
| Evaluation | `POST /sessions/{session_id}/evaluation`, `GET /sessions/{session_id}/evaluation` |

Response lỗi theo envelope `{error: {code, message, details, request_id}}`; mọi response có `X-Request-ID`. `GET /health` luôn trả HTTP 200 và báo tình trạng SQLite, LLM provider, STT trong các component riêng.

## 6. LLM và cấu hình

### Providers

- `LLM_PROVIDER=ollama`: `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, optional profile overrides.
- `LLM_PROVIDER=openai_compatible`: `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`.
- Provider chọn lúc backend khởi động; sửa `.env` cần restart backend.
- Client cloud gọi `/chat/completions`, health gọi `/models`; hiện request token limit dùng `max_completion_tokens`.
- Model được chọn qua profile `roleplay`/`evaluation`, không hardcode trong agent/frontend.

### Cấu hình đang thấy trên máy phát triển

Trong cấu hình local, `OPENAI_BASE_URL` là Groq API endpoint, `OPENAI_MODEL=openai/gpt-oss-20b`, và `ROLEPLAY_MAX_TOKENS=1024`; API key được cấu hình trong `.env`. Giá trị khóa không được lưu ở tài liệu này. Cấu hình local khác với sample trong `.env.example`; model vẫn cần được xác nhận quyền truy cập theo tài khoản Groq.

`.env.example` hiện chọn Groq, để trống `OPENAI_API_KEY`, và có model mẫu `llama-3.3-70b-versatile`; đây không phải xác nhận model đó được phép trên mọi tài khoản. Chỉ điền khóa trong `.env` bị ignore; không gửi khóa vào chat, log, issue hoặc file được theo dõi bởi Git.

## 7. Lưu trữ và bất biến quan trọng

- DB mặc định: `data/echorole.db`; SQLite WAL, foreign keys, busy timeout; migration mới nhất `0002_panel_speaker_metadata`.
- `turns` là transcript sản phẩm; `messages` là lịch sử riêng của từng agent.
- Một session có một conversation `roleplay`; mỗi evaluation attempt có conversation `evaluation` riêng.
- System prompt và history của RoleplayAgent/Coach không dùng chung; Coach không đọc nội bộ roleplay.
- Audio không được lưu; transcript, metrics và evaluation được lưu trong SQLite.
- Nếu chọn cloud LLM, nội dung prompt và transcript gửi cho LLM sẽ được chuyển tới provider đó; cân nhắc dữ liệu đưa vào phiên.
- `metrics_json` chỉ chứa số liệu deterministic; `result_json` chỉ chứa phản hồi định tính. Có sáu score row cho evaluation hoàn tất.
- DB schema và các quy tắc scoring chi tiết: [database-schema.md](architecture/database-schema.md).

## 8. Benchmark và mức độ sẵn sàng

[LLM_BENCHMARK.md](architecture/LLM_BENCHMARK.md) ghi một đợt benchmark chẩn đoán trên CPU với Ollama `qwen2.5:3b`:

- Roleplay warm p95: 6.923 giây; 9/9 output đúng format.
- Evaluation p95: 79.591 giây, vượt mục tiêu 60 giây.
- Chỉ có một lần chạy, chưa đủ 20 lượt để khóa model; chưa có audio fixture gán nhãn để đo WER.
- Có một E2E local được ghi nhận với Qwen/Ollama, không phải Groq.

Vì vậy báo cáo benchmark không chứng nhận model Groq hiện tại và không coi các số đo mẫu là thống kê đủ điều kiện phát hành. Tag `v0.1.0-mvp` tồn tại, nhưng các khoảng trống benchmark ở trên vẫn cần được giải quyết hoặc chấp thuận rõ ràng.

## 9. Kiểm thử gần nhất

| Phạm vi | Kết quả gần nhất | Ghi chú |
|---|---|---|
| Full backend suite | 89 pytest; Ruff và mypy pass | Chạy trước các thay đổi worktree mới nhất |
| Full frontend suite | 58 test; typecheck, lint, build pass | Chạy trước các thay đổi worktree mới nhất |
| Backend hiện tại | 11 test OpenAI-compatible; Ruff, mypy pass | Sau thay đổi `max_completion_tokens` |
| Frontend hiện tại | 30 test API errors; typecheck, lint pass | Build/full suite chưa chạy lại sau thay đổi mới |
| Migration | `alembic upgrade head`; hiện ở `0002_panel_speaker_metadata` | Đã xác minh trên DB local |
| Groq live/E2E | Chưa xác minh sau cấu hình mới | Không dùng API key trong kiểm thử tự động/session này |

Các lệnh CI chuẩn:

```powershell
# backend
python -m ruff check .
python -m mypy app
python -m pytest

# frontend
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

## 10. Cách chạy và việc cần làm tiếp

1. Tạo `.env` từ `.env.example`, điền API key cục bộ và chọn model được tài khoản provider cho phép; không commit `.env`.
2. Chạy `python -m alembic upgrade head`, sau đó backend bằng `uvicorn app.main:app --reload --port 8000`.
3. Chạy frontend bằng `npm run dev`; mocks mặc định tắt. Chỉ bật MSW khi `VITE_USE_MOCKS=true`.
4. Kiểm tra `http://localhost:8000/api/v1/health`; đảm bảo `components.llm.status` là `ok`, rồi chạy session start/turn/end/evaluation.
5. Hoàn tất xác minh live Groq. Lỗi gần nhất là `LLM_BAD_OUTPUT`; các sửa đổi mới nhất về token parameter, budget và hiển thị lỗi cần được xác nhận bằng lần chạy backend mới.
6. Chạy lại full CI, cập nhật kết quả benchmark (đặc biệt Coach p95 và WER), rà soát worktree rồi mới commit/release tiếp.

Để cập nhật tài liệu này, sửa ngày và các mục Git/runtime/test/known issues sau mỗi lần nghiệm thu; không ghi secret hoặc tuyên bố provider hoạt động nếu chưa có kết quả live.
