# 期末報告 — 簡報骨架（Slide Deck Draft）

> 對應文件：[`presentation-requirements.md`](./presentation-requirements.md)。
> 本檔案是 **骨架**，不是成品簡報：一個區塊代表一頁投影片，
> 內容包含對應的評分項度、所需視覺素材、口頭重點、時間預算。
> 實際簡報請在 Keynote / Google Slides / Slidev 上依此大綱製作。

## 簡報設計原則

1. **一頁只講一件事。** 一頁有兩個重點就拆成兩頁。
2. **圖優於字。** 預設每頁一張截圖或圖表，最多搭配 3–5 條簡短條列，
   絕對不貼整段文字。
3. **每頁頁尾打上對應評分項度的標籤**（例如 `30% 需求轉換`），方便
   評審一眼對應到評分欄位，也方便我們繳交前自我檢查有沒有漏。
4. **不要 raw AI 輸出。** 每條 bullet 改成自己的話，刪掉 AI 套版裝
   飾，icons 也要重新挑過。
5. **內文不使用 em dash。** 用逗號、冒號或括號代替。
6. **講稿（speaker note）要短。** Speaker note 是「講者開口要說的
   話」，不是「螢幕上顯示的字」，每頁 1–2 句即可。

## 簡報時間預算（目標：簡報 + Demo 約 10 分鐘）

| 段落 | 投影片 | 目標時間 |
|------|--------|----------|
| A. 開場 + 分工 | 2 頁 | 0.75 min |
| B. 需求轉換與實作（30%） | 3 頁 | 1.5 min |
| C. 架構設計（25%） | 3 頁 | 1.75 min |
| D. Live Demo（預錄影片） | 1 頁 + 影片 | 2.0 min |
| E. 測試與驗證（25%） | 3 頁 | 1.75 min |
| F. 程式碼品質（10%） | 2 頁 | 0.75 min |
| G. 運維與可靠性（10%） | 3 頁 | 1.25 min |
| H. 收尾與 Q&A | 1 頁 | 0.25 min |
| **總計** | **18 頁** | **約 10.0 min** |

響鈴會在第 8 / 12 / 17 / 20 分鐘響起。若第 8 分鐘響鈴時還沒走到 F
段，請優先砍 F 與 G 的深度，**不要砍 D 段 Demo 或 C 段的必要圖面**。

---

## A 段 — 開場 + 分工（0.75 min）

### Slide 1 — 標題頁
- **評分項度：** —
- **視覺：** 專案 Logo / 管理員儀錶板的 Hero Shot（含 KPI 卡片）。
  右上角放組名、課程、日期 2026-06-02。
- **條列：**
  - 資產管理系統 / Asset Management System
  - 雲端計算與軟體工程，期末專題
  - 組員名單一行帶過(細節留到下一頁)
- **講稿：**「我們做的是企業級資產管理系統，覆蓋從持有者送修到管理
  員結案的完整維修流程，現在已經部署到 AWS 上跑了。」

### Slide 2 — 組員與分工
- **評分項度：** —（建立可信度背書）
- **視覺：** 左半部一張 5×5 熱力圖（成員 × 領域，每格用 ● 顯示投入
  程度）；右半部每人一行 headline 條列。簡報上用 icons 代替「●●●」
  也可以，但保持每格的相對強度。
- **熱力圖（簡報上請畫成視覺化色塊，不要貼這張 ASCII 表）：**

  | 成員 | BE | FE | QA | Infra | PM/Docs |
  |------|:--:|:--:|:--:|:-----:|:-------:|
  | 劉仲楷 | ●● |  |  | ●● | ●● |
  | 古庭榮 | ●●● | ● |  |  |  |
  | 鄭怡文 |  | ●● | ●●● |  |  |
  | 陳亮諭 |  | ●●● |  |  | ●● |
  | 闕中豪 |  | ●● |  | ●●● |  |

- **條列（每人一行 headline)：**
  - **劉仲楷** — Backend FSM + Audit log；CI/CD + 安全 Gate；
    Grafana Cloud 可觀測性遷移；Roadmap 維護。
  - **古庭榮** — Monorepo + FastAPI 骨架；Auth / Asset / Repair
    API；Manager Dashboard 聚合端點；Antd 設計 Token 對接。
  - **鄭怡文** — i18n 框架；前端角色資料夾重構；
    Backend 484 / Frontend 184 單元測試 + Playwright E2E 套件。
  - **陳亮諭 (Ryan)** — Asset List 角色感知化；Manager 完整工
    作流；多維篩選 + 分類列舉；簡報製作。
  - **闕中豪** — Antd Layout + 主題切換；Holder 全頁面；
    AWS Production 基礎設施；ALB HTTPS + 域名。
- **講稿：**「五位組員，每人都有清楚的主領域，BE、FE、QA、Infra、
  PM 都有人扛，接下來簡報每一塊都對應得到負責人，Q&A 也可分區回
  答。」

---

## B 段 — 需求轉換與實作，30%（1.5 min）

### Slide 3 — 我們在為哪兩種使用者解決問題
- **評分項度：** 30% 需求
- **視覺：** 並排放兩個 Persona 的 Empathy Map（持有者佳慧 / 管理員
  大偉）。四象限版型：Say / Do / Think / Feel。每象限挑一句訪談原話
  放上去，避免內容變空泛。
- **條列（圖下方說明字串）：**
  - 持有者痛點：無法查維修進度、只能用文字描述故障難以講清楚、不知
    道何時可以拿回設備、業務安排被打亂。
  - 管理員痛點：一天 50 張單、同一張單兩人搶處理、「維修中」狀態太
    粗糙、無法給準確完修時間。
- **講稿：**「這兩個痛點是我們訪談來的，不是空想。系統要做的事就是
  把這兩個痛點消掉。」

### Slide 4 — User Story 與 Acceptance Criteria
- **評分項度：** 30% 需求
- **視覺：** 上半部小卡網格列出所有主要 User Story 標題，下半部 zoom
  in **一則** 完整 AC。建議放「持有者上傳照片並送出維修申請」這一則，
  因為它一次涵蓋圖片上傳 + FSM 狀態轉移 + 重複申請阻擋三條規則。
- **條列：**
  - 共 12 條 User Story，分布於資產基礎資訊管理與維修流程兩個模組。
  - AC 格式：Given / When / Then 加上負向案例。
  - 展示故事：「身為持有者，我可以為手上的資產送出維修申請，附上一
    張故障照片，並查詢申請狀態」。
- **講稿：**「這則 Story 對應到後來的三個生產功能：圖片上傳、
  pending_repair 的 FSM 轉移、重複申請阻擋。」

### Slide 5 — 我們交付的範圍
- **評分項度：** 30% 需求
- **視覺：** 模組地圖。上層兩根柱子（資產基礎資訊 / 維修流程），下層
  基礎設施列（RBAC、i18n zh-TW + en、可觀測性、CI/CD），每塊上面打勾
  代表已完成。右下角放一張小截圖，秀出語言切換器，證明 i18n 真的
  上線。
- **條列：**
  - 資產 CRUD、多維度查詢、由 FSM 驅動的狀態欄。
  - 持有者送出 → 管理員審核 → 維修中 → 完工，含圖片上傳與審計軌跡。
  - RBAC（持有者 vs 管理員）、雙語介面、可抽換的圖片儲存層。
- **講稿：**「需求文件裡寫的全部上線了。進階項目（i18n、並發控制、
  圖片上傳）也都上線了。」

---

## C 段 — 架構設計與可擴展性，25%（1.75 min）

### Slide 6 — 技術選型與架構模式
- **評分項度：** 25% 架構
- **視覺：** 三層 Logo 圖。上層：React 18 + Vite + TypeScript + Ant
  Design v6；中層：FastAPI + SQLAlchemy + Alembic + MySQL 8；下層：
  AWS ECS + ALB + RDS Multi-AZ + S3 + Grafana Cloud。
- **條列：**
  - Modular Monolith。Peak 約 4 QPS，沒有微服務化的壓力，HA 從平台
    層取得，不從拓樸層取得。
  - Optimistic Locking（`version` 欄位），不用 `SELECT ... FOR
    UPDATE`，因為寫入競爭低、讀取要快。
  - `ImageStorage` Protocol：同一個 DB key 在 Dev（本機磁碟）和
    Prod（S3）兩種後端都通用，切換不需要資料遷移。
- **講稿：**「我們刻意挑了無聊的技術棧。有趣的決策不是『選了什
  麼』，而是『怎麼部署』。」

### Slide 7 — Production AWS 架構 + 可擴展性（必要圖面）
- **評分項度：** 25% 架構（含可擴展性）
- **視覺：** 整頁的 AWS 架構圖。Browser → Route53 → ALB（HTTPS、ACM
  憑證、HTTP→HTTPS 301）→ ECS Fargate Service（backend + frontend，
  滾動部署）→ RDS MySQL Multi-AZ。S3 bucket 用於維修照片，透過 ECS
  Task Role 授權。側邊流向：OTLP/HTTP 出口到 Grafana Cloud（Metrics
  + Loki + Tempo + Pyroscope）。GitHub Actions OIDC → ECR + ECS。
  **在 backend 與 frontend service 各畫一個 Auto Scaling 虛線框**，
  箭頭顯示 desired count 可以 1 → N 動態擴展。
- **條列：**
  - **高可用：** ALB 跨 AZ、ECS desired-count ≥ 2、RDS Multi-AZ。
  - **零停機部署：** ECS Rolling 配合 `wait-for-service-stability`、
    部署前先以 one-off task 跑 `alembic upgrade head`；Liveness
    `/health` 與 Readiness `/ready` 分離，讓 RDS 失效切換時 ALB
    drain 目標而非殺容器。
  - **水平擴展：** Frontend / Backend 都是無狀態 ECS 服務，流量上升
    只要把 desired count 拉高，ALB 會自動把流量分到新加進來的 task;
    DB 走 RDS Multi-AZ，垂直擴 instance 規格即可;圖片走 S3，本身
    就是水平擴展服務，不用我們煩惱容量。
- **講稿：**「這頁同時答兩個問題:一個 AZ 掛掉怎麼辦(平台層 HA)，
  以及流量翻倍怎麼辦(無狀態 ECS 水平擴展)。」
- **Q&A 防守備案（不放在簡報、留給講者口頭回答)：** 若評審問「再
  下一步呢?」，回答:(1)讀寫分離:加 RDS Read Replica，把高頻查
  詢路由到 replica，配合既有 query metrics 判斷觸發點;(2)CDN /
  Edge Cache:S3 前掛 CloudFront，讓圖片不再經過 ALB;(3)Cache
  層:Redis 處理熱門資產的基本資訊查詢。這些都已寫進
  `docs/system-design/06-phase3-architecture.md`，現在沒做是因為實
  測指標還沒踩到觸發條件。

### Slide 8 — 維修流程 Sequence + Data Model（必要圖面，合併）
- **評分項度：** 25% 架構
- **視覺：** 左右分割版面。**左半**：Sequence Diagram（Holder →
  Frontend → Backend → MySQL、圖片走 S3）。標出三個轉移
  Pending_Repair → Under_Repair → In_Use，並在「管理員審核同意」這
  一步強調 `version` 檢查（傳入舊版本回 409）。**右半**：ER 圖
  （`users`、`assets`、`repair_requests`、`repair_images`），標出
  `version` 欄位、外鍵以及搜尋用的複合索引
  `(status， category)`、`(department， location)`。
- **條列（圖下方一行串起兩半)：**
  - 同一個 transaction 內同時更新 asset 與 repair request，配合
    `version` 檢查防止管理員競態。
  - Schema 刻意維持四張表的狹窄結構，索引依真實查詢形狀設計。
  - `repair_images.image_url` 存的是 storage key 而非 URL，所以同一
    筆資料在本機磁碟與 S3 兩種後端都通用。
- **講稿：**「左邊看的是『一次審核怎麼跑』，右邊看的是『資料怎麼
  存』，重點都是中間的 `version` 欄位:它讓 Sequence 上的競態被擋
  下，也是 ER 上唯一非 PK 的關鍵欄位。」

---

## D 段 — Live Demo（2.0 min）

### Slide 9 — Demo 影片（預錄，由 Playwright 產生）
- **評分項度：** 30% 需求（佐證）+ 25% 架構（佐證）
- **視覺：** 整頁嵌入預錄的 Demo 影片，由 Playwright `demo` 專案
  （`holder-journey` + `manager-journey`，headed 模式、500 ms
  slow-mo）匯出的 WebM/MP4。播放時段內角落顯示流程編號 1 → 4 對應
  腳本步驟，方便講者旁白指認。
- **影片內容（約 2 min，預先剪好）：**
  1. **持有者登入 → 上傳一張照片並送出維修申請。** 看到資產狀態從
     `In_Use` 轉成 `Pending_Repair`，順手秀一次 i18n 切換。
  2. **管理員儀錶板。** KPI 卡片、資產分類長條圖、維修工作量、最近
     待審清單與點進去的深層連結。
  3. **管理員審核同意。** 背景跑 optimistic lock，資產進入
     `Under_Repair`，填寫維修方案與金額後按下完工，資產回到
     `In_Use`。
  4. **切到 Grafana 分頁。** 剛剛這一筆請求出現在延遲面板，並能從
     面板點到對應的 Trace。
- **講稿：**「為了在 8 分鐘響鈴前精準守住節奏，我們把 Demo 預先用
  Playwright 跑過並錄下來，這也代表這四個流程已經是 E2E 測試的一
  部分，每次 push 都會在 CI 上跑一遍。」

---

## E 段 — 測試與驗證，25%（1.75 min）

### Slide 10 — 測試金字塔（真的三層）
- **評分項度：** 25% 測試
- **視覺：** 真實三層的測試金字塔，由下到上：
  - **底層 Unit Tests：** Backend 約 400+ 個（純函式 / 業務邏輯 /
    FSM 規則 / 表單驗證）。Frontend 約 150+ 個元件與 hook 測試。
  - **中層 Integration Tests：** Backend 約 80+ 個（FastAPI
    TestClient 打真實 API，配合資料庫 fixture），覆蓋每條路由與
    RBAC、生命週期串接。
  - **頂層 E2E Tests：** Playwright 25 個測試、16 個 spec 檔，覆蓋
    6 條關鍵流程（登入、持有者上傳照片送出維修、管理員審核、結案、
    登錄資產、多維度搜尋）。
- **條列：**
  - **Backend** 總覆蓋率 97%（pytest --cov，上傳至 SonarCloud）。
  - **Frontend** 總覆蓋率（vitest）也在 CI 每次 push 上傳。
  - 三層都在 CI 跑，並做 path-filter，動到哪邊就跑哪邊。
- **講稿：**「我們用數字說話，不用形容詞。下層數量多、跑得快;上層
  數量少、抓真實互動，這是真的三層金字塔。」

### Slide 11 — 我們證明的難測案例
- **評分項度：** 25% 測試
- **視覺：** 三宮格矩陣，每一格寫一個風險與對應測試。
- **條列：**
  - **FSM 不變式：** 20 個參數化案例，覆蓋所有合法與不合法的狀態
    轉移。任何違反 FSM 的呼叫會在 API 層被擋下。
  - **RBAC 矩陣：** 持有者 vs 管理員 × 每一個 endpoint，連負向案例
    都驗證。
  - **同時審核競態：** 兩位管理員同時審核同一張單，輸的那一邊收到
    409，不是被靜悄悄覆寫。
- **講稿：**「這些是會在 Production 咬人的案例，每一個都有先紅後綠
  的測試把它釘住。」

### Slide 12 — 壓力測試
- **評分項度：** 25% 測試
- **視覺：** 並排放 k6 結果摘要 + Grafana Cloud Prometheus 同時段
  面板。標註：p50、p95、p99 延遲、錯誤率、Throughput。
- **條列：**
  - `load/` 下有 6 種 k6 情境：smoke、load、stress、spike、soak、
    consistent（持續流量）。
  - 持續壓測直接打線上 ALB，端到端;指標透過
    `K6_PROMETHEUS_RW_*` 送到 Grafana Cloud Prom，可與其他面板對
    照。
  - 標題數字：<待回填，例如 在 Y RPS 持續壓力下 p95 < X ms、錯誤
    率 0>。
- **講稿：**「跑的是線上系統，不是 localhost，看的是和正式維運一樣
  的儀錶板。」

---

## F 段 — 程式碼品質，10%（0.75 min）

### Slide 13 — CI 上有哪些 Gate
- **評分項度：** 10% 程式碼品質
- **視覺：** 由左到右的管線圖，每一格代表一道 Gate，用 icon + 一行
  說明標出「擋什麼」。
- **條列（這些就是我們的把關閘）：**
  - **Lint Gate：** 程式碼風格與常見錯誤;Backend ruff、Frontend
    ESLint 9。
  - **Type Gate：** 型別正確性;Backend mypy `--strict`、Frontend
    `tsc` strict。
  - **Unit + Integration Test Gate：** 紅燈就不能 merge，覆蓋率也
    在這裡計算。
  - **E2E Test Gate：** Playwright 跑 6 條關鍵流程。
  - **Secret Gate：** gitleaks 在本機 pre-commit 與 CI 各擋一次。
  - **SAST Gate：** Semgrep 跑 OWASP Top 10。
  - **SCA Gate：** pip-audit、npm-audit、Trivy 抓相依套件的 CVE。
  - **Quality Gate：** SonarCloud 統合覆蓋率、Bug、Code Smell、
    Security Hotspot，未過就不能 merge。
- **講稿：**「品質不是看心情，是看 Gate。任何一道紅燈，PR 都不會被
  merge。」

### Slide 14 — SonarCloud 截圖
- **評分項度：** 10% 程式碼品質
- **視覺：** SonarCloud 專案頁的整頁截圖：Quality Gate **Passed**，
  含 New Issues / Coverage / Duplications / Security Hotspots。
- **條列：**
  - Quality Gate 在每個 PR 都是綠燈。
  - 覆蓋率同時涵蓋 Backend（pytest）與 Frontend（vitest），兩邊都
    在 CI 每次 push 上傳。
  - 報告連結就在 Repo README，評審可直接點進去驗證。
- **講稿：**「這頁在 Repo 的每個 PR 上都看得到，評審可以從我們的
  Repo 連結點進去驗證。」

---

## G 段 — 運維與可靠性，10%（1.25 min）

### Slide 15 — CI/CD Pipeline（執行中截圖）
- **評分項度：** 10% 運維
- **視覺：** GitHub Actions 矩陣畫面：backend-lint / backend-typecheck
  / backend-test 三個平行 jobs、frontend、security 列、再到
  sonarqube、最後 deploy-backend / deploy-frontend。
- **條列：**
  - Path-filtered：只動 frontend 的 commit **不會** rollout backend
    的 ECS service，反之亦然。
  - 部署透過 GitHub OIDC 取得 AWS Role，Repo 內沒有長效 AWS Key。
  - ECS 滾動部署配合 `wait-for-service-stability`，部署前以 one-off
    task 跑 Alembic migration，環境權限分離。
- **講稿：**「Push 到 main，只有對的那一側會 rollout。錯側部署不是
  靠紀律，是設計上就不可能。」

### Slide 16 — 可觀測性：Grafana Cloud 儀錶板
- **評分項度：** 10% 運維
- **視覺：** Grafana Cloud 四宮格拼貼：
  - 左上：每個 endpoint 的 RED 指標（Rate / Errors / Duration）。
  - 右上：Loki 日誌，篩選到同一個 Trace ID。
  - 左下：Tempo 對同一筆請求的 Trace 時間軸。
  - 右下：同一時間窗的 Pyroscope CPU Flamegraph。
- **條列：**
  - OTLP/HTTP 從 backend 出口到 Grafana Cloud（Metrics + Logs +
    Traces + Profiles 同一個面板可串）。
  - 指標是刻意挑的，每一條都有它要抓的失效模式：
    - **每條路由的 p95 延遲** → 使用者可感知的慢的告警。
    - **5xx 比率** → 正確性告警。
    - **DB 連線池飽和度** → 容量告警。
    - **圖片上傳錯誤率** → S3 / IAM 退化告警。
  - 端到端關聯走查已實測：儀錶板面板 → 同窗口 Loki 日誌 → Tempo
    Trace → Pyroscope Flamegraph 可互通。
- **講稿：**「這頁上的每個指標都對應到一個我們會擔心的失效情境，
  不是為了讓儀錶板看起來不空才放。」

### Slide 17 — 可靠性機制
- **評分項度：** 10% 運維
- **視覺：** 三欄「若 X 失效，會發生什麼」對照表。
- **條列：**
  - **AZ 失效** → ALB 切到存活 AZ、RDS Multi-AZ 自動 failover、ECS
    重新調度。
  - **DB 短暫斷線** → `/ready` 回 503、ALB drain 目標、不會出現大
    量 5xx。
  - **管理員競態** → optimistic lock 回 409，重試是安全的。
  - **不良 Migration** → 部署前的 Alembic upgrade one-off task 失敗
    時直接中止 rollout。
  - **部署退化** → ECS 滾動部署在新版健康前不會殺舊版。
- **講稿：**「我們不喊『高可用』口號，而是把每個失效模式列出來，
  每一個都標出對應的處理機制。」

---

## H 段 — 收尾與 Q&A（0.25 min）

### Slide 18 — Thank You / Q&A
- **評分項度：** —
- **視覺：** 簡潔收尾頁:專案名稱、線上 Demo URL、Repo URL、開啟
  Repo 的 QR Code、四位組員、一句 tagline。為了首尾呼應，再放一次
  標題頁的 KPI Hero Shot。
- **講稿：**「Q&A 開放，分工依 Slide 2 熱力圖:Joshua 接架構與運
  維、jnes0824 接 Backend API、Emma 接測試、Ryan 接 FE 業務頁、
  Chung Hao 接 AWS 基礎設施。」

---

## 對照表：評分項度涵蓋自我檢查

繳交前用這張表逐項勾掉：

| 權重 | 項目 | 對應投影片 | 狀態 |
|------|------|------------|------|
| 30% | 需求 | 3、4、5（+ Demo 為佐證） | [ ] |
| 25% | 架構 | 6、7、8 | [ ] |
| 25% | 測試 | 10、11、12 | [ ] |
| 10% | 程式碼品質 | 13、14 | [ ] |
| 10% | 運維 | 15、16、17 | [ ] |

繳交時任何一列沒勾掉，就不算定稿。

## 簡報定稿前的待辦清單

- [ ] 決定最終配色（以 `docs/designs/DESIGN.md` 的 TSMC 色票為基礎，
      簡報上收斂到兩個重點色)。
- [ ] 在 Slide 2 上畫出視覺化的分工熱力圖（用色塊或 icons，不要直接
      貼 markdown 表格)。
- [ ] 渲染並匯出三張必要圖面為 PNG（AWS 架構含 Auto Scaling 標註、
      Sequence、ER；後兩張會合在 Slide 8 同一頁呈現，AWS 架構在
      Slide 7 單獨呈現)。
- [ ] 用 Playwright `demo` 專案錄製 Demo 影片，剪成約 2 分鐘的成
      品，嵌入 Slide 9。
- [ ] 截 SonarCloud 通過 Quality Gate 的畫面。
- [ ] 截 CI 平行 Jobs 進行中的矩陣畫面。
- [ ] 截 Grafana 四宮格拼貼（在 Demo 時段)。
- [ ] 把真實的 Load Test 數字填回 Slide 12。
- [ ] 每段投影片指定講者，配合 8 分鐘響鈴做一次完整彩排。
- [ ] 匯出為 PDF，內嵌字型，確認 < 25 MB，於 2026-06-03 00:00 前繳
      交。
